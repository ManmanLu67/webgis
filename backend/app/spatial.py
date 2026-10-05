"""空间列与空间检索。

PostGIS 只在 PostgreSQL 上存在，SQLite（本机开发与测试）上没有对应能力，
所以类型与表达式都按方言分支。这是存储层的取舍，不是数据源或切片后端的取舍——
`catalog` 不该知道这些，所以由本模块独立承担：`app/catalog/search.py` 只调用
`intersects()`，不出现任何 PostGIS 字样。
"""

from sqlalchemy import ColumnElement, Text, and_, func

# geometry 列在非 PostgreSQL 上的替身：存 WKT 文本。用 with_variant 而不是
# 条件建模，这样 ORM 的列定义与迁移建出来的表始终对得上。
WKT_FALLBACK = Text


def has_postgis(bind) -> bool:
    return bind.dialect.name == "postgresql"


def intersects(item, bbox: tuple[float, float, float, float], bind) -> ColumnElement[bool]:
    """范围相交条件。`item` 是带范围列和 geometry 列的映射类。

    有 PostGIS 走 `ST_Intersects(geometry, envelope)`，吃 GIST 索引。
    不能把映射类本身塞进去：`ST_Intersects(Item, …)` 不是对 geometry 列的判断。
    没有 PostGIS 就退回四个 float 列的比较，语义一致，只是慢一些。
    """
    minx, miny, maxx, maxy = bbox
    if has_postgis(bind):
        return func.ST_Intersects(item.geometry, func.ST_MakeEnvelope(minx, miny, maxx, maxy, 4326))
    return and_(
        item.minx <= maxx,
        item.maxx >= minx,
        item.miny <= maxy,
        item.maxy >= miny,
    )


def geometry_from_bbox(bind, bbox: tuple[float, float, float, float]):
    """把范围写成 geometry 列的值。"""
    minx, miny, maxx, maxy = bbox
    if has_postgis(bind):
        return func.ST_MakeEnvelope(minx, miny, maxx, maxy, 4326)
    return f"POLYGON(({minx} {miny}, {maxx} {miny}, {maxx} {maxy}, {minx} {maxy}, {minx} {miny}))"


def geometry_from_geojson(bind, geojson: str):
    if has_postgis(bind):
        return func.ST_SetSRID(func.ST_GeomFromGeoJSON(geojson), 4326)
    return geojson


def populate_item_geometry(bind, row) -> None:
    """Item 落库时顺手填 geometry，GIST 索引才有东西可用。"""
    row.geometry = geometry_from_bbox(bind, (row.minx, row.miny, row.maxx, row.maxy))


def populate_annotation_geometry(bind, row) -> None:
    row.geometry = geometry_from_geojson(bind, row.geometry_json)