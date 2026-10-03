import json
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.models import Collection, Item, Job, Layer, Provider
from app.publishers.protocol import TilePublisher


def recover_interrupted(session: Session) -> int:
    rows = list(session.scalars(select(Job).where(Job.status == "running")))
    now = datetime.now(UTC)
    for row in rows:
        row.status = "failed"
        row.error = "interrupted by process restart"
        row.updated_at = now
    session.commit()
    return len(rows)


def run_once(session: Session, converter, publishers: dict[str, TilePublisher], settings: Settings) -> Job | None:
    job = session.scalars(select(Job).where(Job.status == "queued").order_by(Job.created_at)).first()
    if job is None:
        return None
    now = datetime.now(UTC)
    job.status = "running"
    job.updated_at = now
    session.commit()
    payload = json.loads(job.payload_json)
    try:
        source = Path(payload["source_path"])
        dest = settings.data_dir / "cog" / f"{job.id}.tif"
        result = converter.to_cog(source, dest)
        _store_item(session, job, payload, result, publishers, settings.default_publisher)
        job.status = "success"
        job.progress = 1
        job.error = None
        payload["item_id"] = job.id
        job.payload_json = json.dumps(payload)
    except Exception as exc:  # noqa: BLE001 — job row must record the failure
        session.rollback()
        failed = session.get(Job, job.id)
        if failed is not None:
            failed.status = "failed"
            failed.error = str(exc)
            failed.updated_at = datetime.now(UTC)
            session.commit()
        return failed
    job.updated_at = datetime.now(UTC)
    session.commit()
    return job


def _store_item(session, job, payload, result, publishers, publisher_id) -> None:
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

