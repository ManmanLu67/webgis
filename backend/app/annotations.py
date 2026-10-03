import json
from datetime import UTC, datetime

from app.models import Annotation
from app.spatial import populate_annotation_geometry


def validate_geometry(geometry: object) -> dict:
    if not isinstance(geometry, dict):
        raise TypeError("几何必须是对象")
    kind = geometry.get("type")
    coordinates = geometry.get("coordinates")
    if kind == "Point":
        if not isinstance(coordinates, list) or len(coordinates) < 2:
            raise ValueError("点至少要有经度和纬度")
    elif kind == "LineString":
        if not isinstance(coordinates, list) or len(coordinates) < 2:
            raise ValueError("线至少两个点")
    elif kind == "Polygon":
        ring = coordinates[0] if isinstance(coordinates, list) and coordinates else []
        if not isinstance(ring, list) or len(ring) < 4:
            raise ValueError("面至少三个点")
    else:
        raise ValueError("几何必须是点、线或面")
    return geometry


def to_feature(row: Annotation) -> dict:
    return {
        "type": "Feature",
        "id": row.id,
        "geometry": json.loads(row.geometry_json),
        "properties": {**json.loads(row.properties_json), "created_at": row.created_at.isoformat()},
    }


def to_collection(rows: list[Annotation]) -> dict:
    return {"type": "FeatureCollection", "features": [to_feature(row) for row in rows]}


def new_annotation(
    annotation_id: str,
    geometry: dict,
    properties: dict | None,
    bind=None,
) -> Annotation:
    checked = validate_geometry(geometry)
    row = Annotation(
        id=annotation_id,
        geometry_json=json.dumps(checked),
        properties_json=json.dumps(properties or {}),
        created_at=datetime.now(UTC),
    )
    # 有 PostGIS 时同时落一份 geometry，空间索引才对标注有意义。
    if bind is not None:
        populate_annotation_geometry(bind, row)
    return row
