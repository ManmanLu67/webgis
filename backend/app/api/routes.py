import json
import time
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import quote

import fsspec
import httpx
from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile

from app.catalog.search import SearchError, parse_bbox, parse_datetime, search_items
from app.catalog.stac import items_to_feature_collection
from app.catalog.sync import upsert_found
from app.config import Settings
from app.models import Item, Job, Layer, Provider
from app.providers.protocol import LayerSpec

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
def item_layer(
    item_id: str,
    request: Request,
    publisher: str | None = None,
    variant: str = "xyz",
) -> dict:
    registry = request.app.state.publishers
    publisher_id = publisher or request.app.state.settings.default_publisher
    if publisher_id not in registry:
        raise HTTPException(status_code=400, detail=f"unknown publisher {publisher_id}")
    session = request.app.state.session_factory()
    try:
        item = session.get(Item, item_id)
        if item is None:
            raise HTTPException(status_code=404, detail="unknown item")
        try:
            spec = registry[publisher_id].publish(item, variant=variant)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
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
        payload = _layer_payload(spec)
        # 参考型图层不经过发布器，没有 variant 概念；但字段集必须一致（宪章 C3）。
        payload["variants"] = list(getattr(registry[publisher_id], "variants", ()))
        return payload
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
async def tile_timing(
    request: Request,
    url: str | None = None,
    z: int = 0,
    x: int = 0,
    y: int = 0,
) -> dict:
    """实测一次瓦片耗时。

    宪章 C8 要求：采样过才报耗时，观测到才报命中。所以这里真的发一次请求；
    没给`url` 时如实说明"未采样"，不返回编造的 0。`cache` 只有 `none` 与
    `unverified` 两种取值——命中率要从缓存层自己的日志读，不在这个端点里假设。
    """
    settings: Settings = request.app.state.settings
    cache = "unverified" if settings.tile_cache_enabled else "none"
    if not url:
        return {
            "duration_ms": None,
            "cache": cache,
            "sampled": False,
            "note": "未指定 url，没有发起请求。要采样请传 ?url=<cog>&z=&x=&y=",
        }

    from app.publishers.cog_service import (
        CogAccessError,
        allowed_remote_hosts,
        validate_cog_path,
    )

    try:
        target = validate_cog_path(
            url,
            data_dir=settings.data_dir,
            remote_hosts=allowed_remote_hosts(settings.remote_cog_hosts),
        )
    except CogAccessError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc

    base = settings.tile_service_prefix.rstrip("/")
    path = f"{base}/tiles/WebMercatorQuad/{z}/{x}/{y}.png?url={quote(target, safe='')}"
    started = time.perf_counter()
    if settings.public_base_url:
        transport, client_kwargs = None, {"base_url": settings.public_base_url.rstrip("/")}
        note = "经真实 HTTP 采样，含网关"
    else:
        transport = httpx.ASGITransport(app=request.app)
        client_kwargs = {"base_url": "http://tile-service.internal"}
        note = "进程内采样，不含网关与缓存层"
    async with httpx.AsyncClient(transport=transport, **client_kwargs) as client:
        response = await client.get(path)
    duration_ms = (time.perf_counter() - started) * 1000
    return {
        "duration_ms": round(duration_ms, 2),
        "cache": cache,
        "sampled": True,
        "status": response.status_code,
        "bytes": len(response.content),
        "server_timing": response.headers.get("server-timing"),
        "note": note,
    }


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


def _layer_payload(spec, license_note: str = "") -> dict:
    """LayerSpec 的统一出参。参考型与入库型共用这一个形状（宪章 C3）。"""
    return {
        "id": spec.id,
        "type": spec.type,
        "url": spec.url,
        "style": spec.style,
        "time_dimension": spec.time_dimension,
        "publisher_id": spec.publisher_id,
        "url_template": spec.url_template,
        "tiling_scheme": spec.tiling_scheme,
        "max_zoom": spec.max_zoom,
        "layer_kind": spec.layer_kind,
        "crs": spec.crs,
        "attribution": spec.attribution,
        "license_note": license_note,
        "wmts_capabilities": spec.wmts_capabilities,
        "wmts_layer": spec.wmts_layer,
        "georeference_note": spec.georeference_note,
        "variants": [],
    }


def _layer_document(plugin, item) -> dict:
    """参考型源：优先问插件要 LayerSpec，拿不到就按地址形状兜底合成。"""
    note = plugin.manifest["license_note"]
    try:
        spec = plugin.provider.get_layer_spec(item.id)
    except (NotImplementedError, KeyError):
        templated = "{z}" in item.asset_href
        return _layer_payload(
            LayerSpec(
                id=f"{item.id}:{plugin.manifest['id']}",
                type="xyz" if templated else "cog",
                url=item.asset_href,
                style={},
                time_dimension=item.acquired_at.isoformat(),
                publisher_id=plugin.manifest["id"],
                url_template=item.asset_href if templated else None,
                layer_kind="imagery",
            ),
            license_note=note,
        )
    return _layer_payload(spec, license_note=note)


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
