import json
import logging
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import Settings
from app.models import Collection, Item, Job, Layer, Provider
from app.publishers.protocol import TilePublisher
from app.spatial import populate_item_geometry

logger = logging.getLogger(__name__)

QUEUED = "queued"
RUNNING = "running"
SUCCESS = "success"
FAILED = "failed"
CANCELLED = "cancelled"
TERMINAL = (SUCCESS, FAILED, CANCELLED)


def recover_interrupted(session: Session) -> int:
    """把上次进程退出时卡在 running 的任务标成失败。

    COG 转换是分钟级的，进程重启会丢。这里不静默丢弃，而是明确标失败并在
    `error` 里写清原因，用户能看见发生了什么、可以重新上传。
    """
    rows = list(session.scalars(select(Job).where(Job.status == RUNNING)))
    now = datetime.now(UTC)
    for row in rows:
        row.status = FAILED
        row.error = "interrupted by process restart"
        row.updated_at = now
    session.commit()
    return len(rows)


def claim_next(session: Session) -> Job | None:
    """原子地领取一个排队中的任务。

    原来是「SELECT 一条 queued，然后 UPDATE 成 running」两句话分两次提交，
    两个 worker 同时跑就会领到同一条。现在改成条件更新：`WHERE status='queued'`
    落在 UPDATE 上，谁先改成功谁拿到任务；`rowcount` 为 0 说明被别人抢走了。

    这条保证现在是必需的而不是锦上添花——以前单进程单线程轮询，碰巧不出问题；
    一旦开两个副本，同一景就会被转两次、写坏同一个 COG 路径。
    """
    candidate = session.scalars(
        select(Job.id).where(Job.status == QUEUED).order_by(Job.created_at).limit(1)
    ).first()
    if candidate is None:
        return None
    now = datetime.now(UTC)
    result = session.execute(
        update(Job)
        .where(Job.id == candidate, Job.status == QUEUED)
        .values(status=RUNNING, updated_at=now)
    )
    if result.rowcount != 1:
        session.rollback()
        return None
    session.commit()
    job = session.get(Job, candidate)
    session.refresh(job)
    return job


def cancel(session: Session, job_id: str) -> bool:
    """取消还在排队的任务。已经在跑的不给取消——半途掐断只会留下不一致。"""
    result = session.execute(
        update(Job)
        .where(Job.id == job_id, Job.status == QUEUED)
        .values(status=CANCELLED, error="cancelled by user", updated_at=datetime.now(UTC))
    )
    session.commit()
    return result.rowcount == 1


def run_once(
    session: Session,
    converter,
    publishers: dict[str, TilePublisher],
    settings: Settings,
) -> Job | None:
    job = claim_next(session)
    if job is None:
        return None
    payload = json.loads(job.payload_json)
    try:
        source = Path(payload["source_path"])
        dest = settings.data_dir / "cog" / f"{job.id}.tif"
        result = converter.to_cog(source, dest)
        _store_item(session, job, payload, result, publishers, settings.default_publisher)
        job.status = SUCCESS
        job.progress = 1
        job.error = None
        payload["item_id"] = job.id
        job.payload_json = json.dumps(payload)
    except Exception as exc:  # noqa: BLE001 — job row must record the failure
        session.rollback()
        failed = session.get(Job, job.id)
        if failed is not None:
            failed.status = FAILED
            failed.error = str(exc)
            failed.updated_at = datetime.now(UTC)
            session.commit()
        return failed
    try:
        session.commit()
    except IntegrityError as exc:
        # COG 落在 data_dir/cog/{job.id}.tif，job id 唯一，所以这条只在
        # 同一个 job 被并发处理时才会出现——而那正是领取逻辑要防的事。
        session.rollback()
        logger.warning("job %s 提交时冲突，可能被并发处理：%s", job.id, exc)
        return None
    return job


def _store_item(session, job, payload, result, publishers, publisher_id) -> None:
    """把转好的 COG 登记成 item 与图层。

    幂等：provider / collection 已存在就复用，item 的主键就是 job id，
    所以重跑一次不会产生第二条目录记录。
    """
    if session.get(Provider, "local_file") is None:
        session.add(
            Provider(
                id="local_file",
                name="本地文件",
                mode="ingest",
                status="implemented",
                config_json="{}",
                enabled=True,
                license_note="管理员上传的文件",
                cache_allowed=True,
            )
        )
    if session.get(Collection, "uploads") is None:
        session.add(Collection(id="uploads", provider_id="local_file", title="上传", description=""))
        session.flush()
    acquired = datetime.fromisoformat(payload["acquired_at"])
    item = Item(
        id=job.id,
        collection_id="uploads",
        minx=result.minx,
        miny=result.miny,
        maxx=result.maxx,
        maxy=result.maxy,
        acquired_at=acquired,
        cloud_cover=0,
        asset_href=result.cog_path,
        access_mode="ingest",
    )
    populate_item_geometry(session.get_bind(), item)
    session.add(item)
    session.flush()
    publisher = publishers[publisher_id]
    # 入库后端原生支持的变体优先；只支持 WMTS 的后端就存 WMTS，不硬套 XYZ。
    variant = "xyz" if "xyz" in getattr(publisher, "variants", ()) else publisher.variants[0]
    spec = publisher.publish(item, variant=variant)
    session.add(
        Layer(
            id=spec.id,
            item_id=item.id,
            collection_id=None,
            type=spec.type,
            url=spec.url,
            style_json=json.dumps(spec.style),
            time_dimension=spec.time_dimension,
            publisher_id=spec.publisher_id,
        )
    )