"""入库任务的领取与取消。

领取的原子性是这里唯一真正要紧的东西：原来是「SELECT 一条 queued，再 UPDATE 成
running」两次提交，两个 worker 同时跑就会领到同一条，同一景被转两次、写坏同一个
COG 路径。以前不出问题只是因为默认部署恰好是单进程单线程轮询。
"""

import threading

import pytest
from app.db import make_session_factory
from app.ingest.converter import CopyConverter
from app.ingest.worker import (
    CANCELLED,
    FAILED,
    QUEUED,
    RUNNING,
    SUCCESS,
    cancel,
    claim_next,
    recover_interrupted,
    run_once,
)
from app.models import Item, Job
from fastapi.testclient import TestClient
from sqlalchemy import select

ACQUIRED_AT = "2020-06-01T00:00:00Z"


def _upload(client: TestClient, name: str = "a.tif", when: str = ACQUIRED_AT, body: bytes = b"x" * 32):
    return client.post(
        "/jobs/uploads",
        files={"file": (name, body, "image/tiff")},
        data={"acquired_at": when},
    )


@pytest.fixture
def app(build_app):
    app = build_app(worker_enabled=False)
    app.state.converter = CopyConverter()
    return app


@pytest.fixture
def client(app):
    return TestClient(app)


# --- 领取的原子性 ---


def test_a_queued_job_is_claimed_exactly_once(app, client):
    _upload(client)
    session = app.state.session_factory()
    try:
        first = claim_next(session)
        assert first is not None and first.status == RUNNING
        # 队列空了，再领一次拿不到——不能把同一条再发出去
        assert claim_next(session) is None
    finally:
        session.close()


def test_claiming_happens_in_order(app, client):
    _upload(client, "first.tif")
    _upload(client, "second.tif")
    session = app.state.session_factory()
    try:
        assert claim_next(session).id != claim_next(session).id
    finally:
        session.close()


def test_two_workers_cannot_claim_the_same_job(app, client):
    """真并发：几个线程各开一个 session 同时领。

    SQLite 的写锁会把一部分线程挡掉，所以断言不是"全都领到"，而是两条：
    领到的一定互不相同；剩下的都还在排队。原先的「先 SELECT 后 UPDATE」在这种
    时序下会两边都拿到同一条。
    """
    total = 8
    for index in range(total):
        _upload(client, f"scene-{index}.tif")
    factory = make_session_factory(app.state.engine)
    barrier = threading.Barrier(4)
    claimed: list[str | None] = []
    lock = threading.Lock()

    def worker() -> None:
        session = factory()
        try:
            barrier.wait(timeout=5)
            job = claim_next(session)
            with lock:
                claimed.append(job.id if job else None)
        finally:
            session.close()

    threads = [threading.Thread(target=worker) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)

    got = [item for item in claimed if item is not None]
    assert len(got) == len(set(got)), f"同一条任务被领了多次：{got}"

    session = app.state.session_factory()
    try:
        still_queued = session.query(Job).filter(Job.status == QUEUED).count()
    finally:
        session.close()
    assert still_queued == total - len(got)


def test_claim_returns_none_on_an_empty_queue(app):
    session = app.state.session_factory()
    try:
        assert claim_next(session) is None
    finally:
        session.close()


# --- 取消 ---


def test_a_queued_job_can_be_cancelled(app, client):
    job_id = _upload(client).json()["id"]
    session = app.state.session_factory()
    try:
        assert cancel(session, job_id) is True
    finally:
        session.close()
    assert _status(client, job_id) == CANCELLED


def test_cancelling_a_running_job_is_refused(app, client):
    """半途掐断只会留下状态与文件不一致，不给取消。"""
    job_id = _upload(client).json()["id"]
    session = app.state.session_factory()
    try:
        claim_next(session)
        assert cancel(session, job_id) is False
    finally:
        session.close()
    assert _status(client, job_id) == RUNNING


def test_cancelling_twice_is_refused(app, client):
    job_id = _upload(client).json()["id"]
    session = app.state.session_factory()
    try:
        assert cancel(session, job_id) is True
        assert cancel(session, job_id) is False
    finally:
        session.close()


def test_cancel_endpoint_reports_conflicts(client):
    job_id = _upload(client).json()["id"]
    assert client.delete(f"/jobs/{job_id}").status_code == 200
    # 已是终态，再取消应当 409 而不是悄悄改写
    assert client.delete(f"/jobs/{job_id}").status_code == 409


def test_cancel_endpoint_404s_on_an_unknown_job(client):
    assert client.delete("/jobs/does-not-exist").status_code == 404


# --- 任务列表 ---


def test_job_list_is_newest_first(app, client):
    first = _upload(client, "first.tif").json()["id"]
    second = _upload(client, "second.tif").json()["id"]
    ids = [row["id"] for row in client.get("/jobs").json()]
    assert ids[0] == second
    assert set(ids) == {first, second}


def test_job_list_can_filter_by_status(client):
    keep = _upload(client, "a.tif").json()["id"]
    drop = _upload(client, "b.tif").json()["id"]
    assert client.delete(f"/jobs/{drop}").status_code == 200
    assert [row["id"] for row in client.get("/jobs", params={"status": QUEUED}).json()] == [keep]
    assert [row["id"] for row in client.get("/jobs", params={"status": CANCELLED}).json()] == [drop]
    assert client.get("/jobs", params={"status": SUCCESS}).json() == []


def test_job_list_rejects_an_unknown_status(client):
    assert client.get("/jobs", params={"status": "pending-ish"}).status_code == 400


def test_job_list_is_bounded(client):
    for index in range(5):
        _upload(client, f"s-{index}.tif")
    assert len(client.get("/jobs", params={"limit": 2}).json()) == 2
    assert len(client.get("/jobs", params={"limit": 100000}).json()) == 5


# --- 重启恢复与终态 ---


def test_interrupted_jobs_are_failed_not_silently_dropped(app, client):
    job_id = _upload(client).json()["id"]
    session = app.state.session_factory()
    try:
        assert claim_next(session) is not None
    finally:
        session.close()
    session = app.state.session_factory()
    try:
        assert recover_interrupted(session) == 1
    finally:
        session.close()
    row = _status_row(client, job_id)
    assert row["status"] == FAILED
    assert "restart" in row["error"]


def test_terminal_jobs_are_left_alone(app, client):
    _upload(client)
    session = app.state.session_factory()
    try:
        run_once(session, app.state.converter, app.state.publishers, app.state.settings)
        assert recover_interrupted(session) == 0
    finally:
        session.close()
    assert client.get("/jobs").json()[0]["status"] == SUCCESS


def test_run_once_stops_after_the_queue_drains(app, client):
    _upload(client)
    session = app.state.session_factory()
    try:
        assert run_once(session, app.state.converter, app.state.publishers, app.state.settings) is not None
        assert run_once(session, app.state.converter, app.state.publishers, app.state.settings) is None
    finally:
        session.close()


# --- 辅助 ---


def _status_row(client: TestClient, job_id: str) -> dict:
    return client.get(f"/jobs/{job_id}").json()


def _status(client: TestClient, job_id: str) -> str:
    return _status_row(client, job_id)["status"]


def test_items_only_exist_for_successful_jobs(app, client):
    """失败或取消的任务不该在目录里留下条目。"""
    queued = _upload(client, "a.tif").json()["id"]
    session = app.state.session_factory()
    try:
        cancel(session, queued)
        assert session.get(Item, queued) is None
        assert list(session.scalars(select(Item))) == []
    finally:
        session.close()