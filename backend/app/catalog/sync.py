import json

from sqlalchemy.orm import Session

from app.models import Collection, Item, Provider
from app.plugins.loader import LoadReport
from app.spatial import populate_item_geometry


def sync_catalog(session: Session, report: LoadReport) -> None:
    for plugin in report.loaded:
        manifest = plugin.manifest
        row = session.get(Provider, manifest["id"])
        if row is None:
            row = Provider(
                id=manifest["id"],
                name=manifest["name"],
                mode=manifest["mode"],
                status=manifest["status"],
                config_json=_config_json(plugin),
                enabled=True,
                license_note=str(manifest["license_note"]),
                cache_allowed=bool(manifest["cache_allowed"]),
                error=None,
            )
            session.add(row)
        else:
            row.name = manifest["name"]
            row.mode = manifest["mode"]
            row.status = manifest["status"]
            row.license_note = str(manifest["license_note"])
            row.cache_allowed = bool(manifest["cache_allowed"])
            row.error = None
            row.config_json = _config_json(plugin)
        if manifest["status"] != "implemented" or "search" not in set(manifest["capabilities"]):
            continue
        try:
            found_items = plugin.provider.search(None, None, {})
        except NotImplementedError:
            continue
        for found in found_items:
            upsert_found(session, manifest["id"], found)
    session.commit()


def upsert_found(session: Session, provider_id: str, found) -> None:
    collection = session.get(Collection, found.collection_id)
    if collection is None:
        session.add(
            Collection(
                id=found.collection_id,
                provider_id=provider_id,
                title=found.collection_title,
                description="",
            )
        )
        session.flush()
    if session.get(Item, found.id) is None:
        row = Item(
            id=found.id,
            collection_id=found.collection_id,
            minx=found.minx,
            miny=found.miny,
            maxx=found.maxx,
            maxy=found.maxy,
            acquired_at=found.acquired_at,
            cloud_cover=found.cloud_cover,
            asset_href=found.asset_href,
            access_mode=found.access_mode,
        )
        # 顺手填 geometry，空间索引才有东西可指；没有 PostGIS 时存 WKT 文本。
        populate_item_geometry(session.get_bind(), row)
        session.add(row)


def _config_json(plugin) -> str:
    """记进目录的可用性。

    `availability` 有两个来源，优先级是「provider 在 authenticate() 之后的取值
    覆盖 manifest 声明」：

    - manifest 是必填且已校验的基线，漏写会在加载时报错（原先这里是纯
      `getattr(provider, "availability", "ready")` 的 duck-type，manifest 根本不参与）；
    - 只有 provider 知道凭据在不在，所以允许它在认证后收紧：声明 needs_config 的源
      拿到 Key 后应当变成 ready，否则界面上永远列不出来。
    """
    availability = getattr(plugin.provider, "availability", None) or plugin.manifest[
        "availability"
    ]
    if plugin.manifest["status"] == "skeleton":
        availability = "skeleton"
    return json.dumps(
        {"availability": availability, "credentials": plugin.manifest["credentials"]}
    )
