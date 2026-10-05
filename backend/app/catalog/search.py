from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Collection, Item, Provider
from app.spatial import intersects


class SearchError(ValueError):
    pass


def parse_bbox(value: str) -> tuple[float, float, float, float]:
    parts = [part.strip() for part in value.split(",")]
    if len(parts) != 4:
        raise SearchError("bbox must be minLon,minLat,maxLon,maxLat")
    try:
        minx, miny, maxx, maxy = (float(part) for part in parts)
    except ValueError as exc:
        raise SearchError("bbox values must be numbers") from exc
    if minx > maxx:
        raise SearchError("bbox crosses the antimeridian; split the search into two ranges")
    if miny > maxy:
        raise SearchError("bbox min latitude is greater than max latitude")
    return minx, miny, maxx, maxy


def parse_datetime(value: str) -> tuple[datetime | None, datetime | None]:
    if "/" not in value:
        raise SearchError("datetime must be an interval start/end, start/.., or ../end")
    raw_start, raw_end = value.split("/", 1)
    return _parse_bound(raw_start), _parse_bound(raw_end)


def _parse_bound(raw: str) -> datetime | None:
    if raw in {"", ".."}:
        return None
    text = raw.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise SearchError(f"invalid datetime bound {raw!r}") from exc
    if parsed.tzinfo is None:
        raise SearchError(f"datetime bound {raw!r} must include a timezone")
    return parsed


def search_items(
    session: Session,
    *,
    bbox: tuple[float, float, float, float] | None = None,
    datetime_range: tuple[datetime | None, datetime | None] | None = None,
    cloud_cover_lt: float | None = None,
    limit: int | None = None,
    offset: int = 0,
) -> list[Item]:
    statement = (
        select(Item)
        .join(Collection, Item.collection_id == Collection.id)
        .join(Provider, Collection.provider_id == Provider.id)
        .where(Provider.enabled.is_(True))
    )
    if bbox is not None:
        # 空间过滤交给 app.spatial：有没有 PostGIS 是存储层的事，
        # 这个模块不该出现任何 PostGIS 字样。
        statement = statement.where(intersects(Item, bbox, session.get_bind()))
    if datetime_range is not None:
        start, end = datetime_range
        if start is not None:
            statement = statement.where(Item.acquired_at >= start)
        if end is not None:
            # 左闭右开，与数据源检索的上界一致：结束时刻本身不属于这一段。
            statement = statement.where(Item.acquired_at < end)
    if cloud_cover_lt is not None:
        # 云量未知（NULL）不算"低于阈值"。调用方要的是已知且更晴的景。
        statement = statement.where(Item.cloud_cover.is_not(None), Item.cloud_cover < cloud_cover_lt)
    if offset:
        statement = statement.offset(max(offset, 0))
    if limit is not None:
        statement = statement.limit(max(limit, 0))
    return list(session.scalars(statement))
