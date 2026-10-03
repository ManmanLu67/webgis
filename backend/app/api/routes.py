import json
import time
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import fsspec
from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile

from app.catalog.search import SearchError, parse_bbox, parse_datetime, search_items
from app.catalog.stac import items_to_feature_collection
from app.catalog.sync import upsert_found
from app.models import Item, Job, Layer, Provider

router = APIRouter()


@router.get("/providers")
def list_providers(request: Request, include_disabled: bool = False) -> list[dict]:
    session = request.app.state.session_factory()
    try:
        rows = session.query(Provider).order_by(Provider.id).all()
        if not include_disabled:
            rows = [row for row in rows if row.enabled]
        plugins = getattr(request.app.state, "plugins", {})
        return [_provider_document(row, plugins.get(row.id)) for row in rows]
    finally:
        session.close()


@router.post("/providers/{provider_id}/search")
def search_provider(provider_id: str, body: dict, request: Request) -> dict:
    plugin = getattr(request.app.state, "plugins", {}).get(provider_id)
    if plugin is None:
        raise HTTPException(status_code=404, detail="未知数据源")
    availability = getattr(plugin.provider, "availability", "ready")
    if plugin.manifest["status"] == "skeleton" or availability == "skeleton":
        raise HTTPException(status_code=501, detail="未实现")
    if availability == "needs_config" and not body.get("key"):
        raise HTTPException(status_code=409, detail="需配置")
    bbox = body.get("bbox")
    if bbox is not None and len(bbox) != 4:
        raise HTTPException(status_code=400, detail="范围需要四个数")
    try:
        found = plugin.provider.search(
            tuple(bbox) if bbox else None,
            _search_datetime(body),
            {
                "fetch": True,
                "limit": body.get("limit") or 1,
                "template": body.get("template"),
                "key": body.get("key"),
            },
        )
    except NotImplementedError as exc:
        raise HTTPException(status_code=501, detail=str(exc)) from exc
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    session = request.app.state.session_factory()
    try:
        results = []
        for item in found:
            upsert_found(session, provider_id, item)
            layer = _layer_document(plugin, item)
            results.append(
                {
                    "id": item.id,
                    "title": item.collection_title,
                    "bbox": [item.minx, item.miny, item.maxx, item.maxy],
                    "time": item.acquired_at.date().isoformat(),
                    "layer": layer,
                }
            )
        session.commit()
        return {"items": results}
    finally:
        session.close()


@router.get("/providers/errors")
def provider_errors(request: Request) -> list[str]:
    return list(request.app.state.load_errors)


@router.get("/items")
def list_items(
    request: Request,
    bbox: str | None = None,
    datetime: str | None = None,
    cloud_cover_lt: float | None = None,
) -> dict:
    try:
        parsed_bbox = parse_bbox(bbox) if bbox else None
        parsed_datetime = parse_datetime(datetime) if datetime else None
    except SearchError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    session = request.app.state.session_factory()
    try:
        items = search_items(
            session,
            bbox=parsed_bbox,
            datetime_range=parsed_datetime,
            cloud_cover_lt=cloud_cover_lt,
        )
        return items_to_feature_collection(items)
    finally:
        session.close()


@router.get("/items/{item_id}/layer")
def item_layer(item_id: str, request: Request, publisher: str | None = None) -> dict:
    registry = request.app.state.publishers
    publisher_id = publisher or request.app.state.settings.default_publisher
    if publisher_id not in registry:
        raise HTTPException(status_code=400, detail=f"unknown publisher {publisher_id}")
    session = request.app.state.session_factory()
    try:
        item = session.get(Item, item_id)
        if item is None:
            raise HTTPException(status_code=404, detail="unknown item")
        spec = registry[publisher_id].publish(item)
        row = session.get(Layer, spec.id)
        if row is None:
            row = Layer(
                id=spec.id,
                item_id=item.id,
                collection_id=None,
                type=spec.type,
                url=spec.url,
                style_json=json.dumps(spec.style),
                time_dimension=spec.time_dimension,
                publisher_id=spec.publisher_id,
            )
            session.add(row)
        else:
            row.url = spec.url
            row.type = spec.type
            row.publisher_id = spec.publisher_id
            row.time_dimension = spec.time_dimension
        session.commit()
        return {
            "id": spec.id,
            "type": spec.type,
            "url": spec.url,
            "style": spec.style,
            "time_dimension": spec.time_dimension,
            "publisher_id": spec.publisher_id,
        }
    finally:
        session.close()


@router.post("/jobs/uploads", status_code=202)
async def upload_job(
    request: Request,
    file: UploadFile = File(...),  # noqa: B008
    acquired_at: str = Form(...),
) -> dict:
    try:
        datetime.fromisoformat(acquired_at)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="acquired_at must be a timezone-aware timestamp") from exc
    job_id = uuid.uuid4().hex
    incoming = request.app.state.settings.data_dir / "incoming"
    incoming.mkdir(parents=True, exist_ok=True)
    suffix = Path(file.filename or "upload.bin").suffix or ".bin"
    source = incoming / f"{job_id}{suffix}"
    payload = await file.read()
    with fsspec.open(source.as_posix(), "wb") as handle:
        handle.write(payload)
    now = datetime.now(UTC)
    job = Job(
        id=job_id,
        type="ingest",
        status="queued",
        progress=0,
        error=None,
        payload_json=json.dumps(
            {"source_path": str(source), "acquired_at": acquired_at, "filename": file.filename}
        ),
        created_at=now,
        updated_at=now,
    )
    session = request.app.state.session_factory()
    try:
        session.add(job)
        session.commit()
        session.refresh(job)
        return _job_document(job)
    finally:
        session.close()


@router.get("/jobs/{job_id}")
def read_job(job_id: str, request: Request) -> dict:
    session = request.app.state.session_factory()
    try:
        job = session.get(Job, job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="unknown job")
        return _job_document(job)
    finally:
        session.close()


@router.get("/tiles/timing")
def tile_timing() -> dict:
    started = time.perf_counter()
    duration_ms = (time.perf_counter() - started) * 1000
    return {"duration_ms": duration_ms, "cache": "none"}


def _job_document(job: Job) -> dict:
    return {
        "id": job.id,
        "type": job.type,
        "status": job.status,
        "progress": job.progress,
        "error": job.error,
        "payload": json.loads(job.payload_json),
        "created_at": job.created_at.isoformat(),
        "updated_at": job.updated_at.isoformat(),
    }


def _layer_document(plugin, item) -> dict:
    note = plugin.manifest["license_note"]
    try:
        spec = plugin.provider.get_layer_spec(item.id)
    except (NotImplementedError, KeyError):
        return {
            "type": "xyz" if "{z}" in item.asset_href else "cog",
            "url": item.asset_href,
            "attribution": note,
            "tiling_scheme": "WebMercator",
            "max_zoom": None,
            "layer_kind": "imagery",
            "url_template": None,
            "crs": "EPSG:4326",
            "attribution": note,
        }
    return {
        "type": spec.type,
        "url": spec.url,
        "attribution": note,
        "url_template": spec.url_template,
        "tiling_scheme": spec.tiling_scheme,
        "max_zoom": spec.max_zoom,
        "layer_kind": spec.layer_kind,
        "crs": spec.crs,
        "attribution": spec.attribution,
    }


def _availability(row: Provider) -> str:
    if row.status == "skeleton":
        return "skeleton"
    try:
        config = json.loads(row.config_json or "{}")
    except json.JSONDecodeError:
        config = {}
    return str(config.get("availability") or "ready")


def _search_datetime(body: dict):
    raw = body.get("datetime")
    if raw is None or raw == "":
        return None
    text = str(raw)
    if "/" in text:
        try:
            return parse_datetime(text)
        except SearchError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    try:
        day = datetime.fromisoformat(text[:10]).replace(tzinfo=UTC)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="时间格式无效") from exc
    return day, day + timedelta(days=1)


def _provider_document(row: Provider, plugin=None) -> dict:
    manifest = plugin.manifest if plugin is not None else {}
    availability = _availability(row)
    drape = bool(manifest.get("drape")) and availability == "ready" and row.status != "skeleton"
    return {
        "id": row.id,
        "name": row.name,
        "mode": row.mode,
        "status": row.status,
        "enabled": row.enabled,
        "license_note": row.license_note,
        "cache_allowed": row.cache_allowed,
        "error": row.error,
        "availability": availability,
        "drape": drape,
        "picker": manifest.get("picker") if drape else None,
    }
