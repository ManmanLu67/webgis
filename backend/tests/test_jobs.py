from datetime import UTC, datetime

from app.ingest.converter import CopyConverter
from app.ingest.worker import recover_interrupted, run_once
from app.models import Item, Job
from fastapi.testclient import TestClient


def _app(build_app):
    app = build_app(worker_enabled=False)
    app.state.converter = CopyConverter()
    return app


def _upload(client: TestClient, name: str, when: str, body: bytes = b"not-really-tiff"):
    return client.post(
        "/jobs/uploads",
        files={"file": (name, body, "application/octet-stream")},
        data={"acquired_at": when},
    )


def test_upload_queues_then_succeeds_with_layer(build_app):
    app = _app(build_app)
    client = TestClient(app)
    created = _upload(client, "scene.tif", "2020-06-01T00:00:00Z")
    assert created.status_code == 202
    assert created.json()["status"] == "queued"
    session = app.state.session_factory()
    try:
        finished = run_once(session, app.state.converter, app.state.publishers, app.state.settings)
        assert finished is not None
        assert finished.status == "success"
        item = session.get(Item, finished.id)
        assert item is not None
        layer = client.get(f"/items/{finished.id}/layer")
        assert layer.status_code == 200
        assert layer.json()["url"]
    finally:
        session.close()


def test_second_run_does_not_claim_the_same_job(build_app):
    app = _app(build_app)
    client = TestClient(app)
    _upload(client, "scene.tif", "2020-06-01T00:00:00Z")
    session = app.state.session_factory()
    try:
        first = run_once(session, app.state.converter, app.state.publishers, app.state.settings)
        second = run_once(session, app.state.converter, app.state.publishers, app.state.settings)
        assert first is not None and first.status == "success"
        assert second is None
    finally:
        session.close()


def test_interrupted_job_fails_without_an_item(build_app):
    app = _app(build_app)
    session = app.state.session_factory()
    now = datetime.now(UTC)
    session.add(
        Job(
            id="stuck",
            type="ingest",
            status="running",
            progress=0.2,
            error=None,
            payload_json="{}",
            created_at=now,
            updated_at=now,
        )
    )
    session.commit()
    recover_interrupted(session)
    job = session.get(Job, "stuck")
    assert job.status == "failed"
    assert "restart" in job.error
    assert session.get(Item, "stuck") is None
    session.close()


def test_non_image_is_refused_at_the_door(build_app):
    """非 GeoTIFF 在上传时就拒掉。

    原来它会先排队、worker 转完再失败——用户要等一分钟才看到一句"不是图片"，
    而答案在上传那一刻就已经知道了。
    """
    app = _app(build_app)
    client = TestClient(app)
    created = _upload(client, "notes.txt", "2020-06-01T00:00:00Z", b"hello")
    assert created.status_code == 400
    assert ".tif" in created.json()["detail"]

    session = app.state.session_factory()
    try:
        assert session.query(Job).count() == 0, "被拒的上传不该留下任务记录"
    finally:
        session.close()


def test_upload_rejects_an_unparseable_timestamp(build_app):
    app = _app(build_app)
    client = TestClient(app)
    created = _upload(client, "a.tif", "not-a-timestamp")
    assert created.status_code == 400
    assert "timezone-aware" in created.json()["detail"]


def test_upload_enforces_the_size_cap(build_app, tmp_path):
    """超限的上传要返回 413，并且不留半截文件与任务记录。"""
    app = _app(build_app)
    client = TestClient(app)
    app.state.settings.max_upload_bytes = 64
    created = _upload(client, "big.tif", "2020-06-01T00:00:00Z", b"x" * 4096)
    assert created.status_code == 413
    session = app.state.session_factory()
    try:
        assert session.query(Job).count() == 0
    finally:
        session.close()
    assert list((tmp_path / "data" / "incoming").glob("*")) == [], "半截文件应当清掉"


def test_upload_records_the_byte_count(build_app):
    app = _app(build_app)
    client = TestClient(app)
    body = b"not-really-tiff" * 10
    created = _upload(client, "a.tif", "2020-06-01T00:00:00Z", body)
    assert created.status_code == 202
    assert created.json()["payload"]["bytes"] == len(body)


def test_times_stay_distinct(build_app):
    app = _app(build_app)
    client = TestClient(app)
    _upload(client, "a.tif", "2020-01-01T00:00:00Z")
    _upload(client, "b.tif", "2021-01-01T00:00:00Z")
    session = app.state.session_factory()
    try:
        run_once(session, app.state.converter, app.state.publishers, app.state.settings)
        run_once(session, app.state.converter, app.state.publishers, app.state.settings)
    finally:
        session.close()
    response = client.get(
        "/items",
        params={"bbox": "-10,-10,10,10", "datetime": "2020-01-01T00:00:00Z/2020-12-31T00:00:00Z"},
    )
    assert response.status_code == 200
    assert len(response.json()["features"]) == 1


def test_tile_timing_does_not_claim_a_cache_hit(build_app):
    app = _app(build_app)
    client = TestClient(app)
    body = client.get("/tiles/timing").json()
    assert "duration_ms" in body
    assert body["cache"] == "none"
    assert "hit" not in body
