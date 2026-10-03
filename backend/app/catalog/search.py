from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Collection, Item, Provider


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
) -> list[Item]:
    statement = (
        select(Item)
        .join(Collection, Item.collection_id == Collection.id)
        .join(Provider, Collection.provider_id == Provider.id)
        .where(Provider.enabled.is_(True))
    )
    if bbox is not None:
        minx, miny, maxx, maxy = bbox
        statement = statement.where(
            Item.maxx >= minx,
            Item.minx <= maxx,
            Item.maxy >= miny,
            Item.miny <= maxy,
        )
    if datetime_range is not None:
        start, end = datetime_range
        if start is not None:
            statement = statement.where(Item.acquired_at >= start)
        if end is not None:
            statement = statement.where(Item.acquired_at <= end)
    if cloud_cover_lt is not None:
        statement = statement.where(Item.cloud_cover.is_not(None), Item.cloud_cover < cloud_cover_lt)
    return list(session.scalars(statement))
