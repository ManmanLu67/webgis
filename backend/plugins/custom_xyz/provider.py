import hashlib
from datetime import UTC, datetime
from typing import ClassVar

from app.providers.protocol import CatalogItem, LayerSpec
from app.providers.xyz_template import apply_time, normalize_xyz_template

_SCHEMES = {"WebMercator", "Geographic"}
_KINDS = {"imagery", "map"}


class CustomXyzProvider:
    """用户填 URL 模板即可接入。插件内不存放任何现成瓦片地址。"""

    id = "custom_xyz"
    capabilities: ClassVar[set[str]] = {"search", "temporal"}
    availability = "ready"

    def __init__(self) -> None:
        self._layers: dict[str, LayerSpec] = {}

    def authenticate(self, config: dict) -> None:
        return None

    def search(self, bbox, datetime_range, filters) -> list[CatalogItem]:
        raw = (filters or {}).get("template")
        if not raw:
            return []
        if not isinstance(raw, dict):
            raise TypeError("template 必须是对象")
        name = str(raw.get("name") or "").strip()
        if not name:
            raise ValueError("需要地图名称")
        template = normalize_xyz_template(str(raw.get("url_template") or ""))
        scheme = str(raw.get("tiling_scheme") or "WebMercator")
        kind = str(raw.get("layer_kind") or "imagery")
        if scheme not in _SCHEMES:
            raise ValueError("投影只能是 WebMercator 或 Geographic")
        if kind not in _KINDS:
            raise ValueError("图层种类只能是 imagery 或 map")
        max_zoom = int(raw.get("max_zoom") or 18)
        if not 0 <= max_zoom <= 24:
            raise ValueError("最大级别须在 0 到 24")
        crs = str(raw.get("crs") or "EPSG:3857")
        if crs == "GCJ-02":
            raise ValueError("GCJ-02 不能当作 WGS84 直接叠加")
        if crs not in {"EPSG:3857", "EPSG:4326", "EPSG:4490"}:
            raise ValueError("坐标系必须显式声明")
        when = str(raw.get("time") or "")
        url = apply_time(template, when or None)
        digest = hashlib.sha1(f"{name}\n{url}".encode()).hexdigest()[:10]
        item_id = f"custom-{digest}"
        acquired = datetime.now(UTC)
        if when:
            try:
                acquired = datetime.fromisoformat(when)
                if acquired.tzinfo is None:
                    acquired = acquired.replace(tzinfo=UTC)
            except ValueError:
                acquired = datetime.now(UTC)
        self._layers[item_id] = LayerSpec(
            id=item_id,
            type="xyz",
            url=url,
            style={},
            time_dimension=when or None,
            publisher_id="custom_xyz",
            url_template=template,
            tiling_scheme=scheme,
            max_zoom=max_zoom,
            layer_kind=kind,
            crs=crs,
            attribution=str(raw.get("attribution") or "用户自备地址"),
        )
        return [
            CatalogItem(
                id=item_id,
                collection_id="custom-xyz",
                collection_title=name,
                minx=-180,
                miny=-85,
                maxx=180,
                maxy=85,
                acquired_at=acquired,
                cloud_cover=None,
                asset_href=url,
                access_mode="reference",
            )
        ]

    def get_layer_spec(self, item_id: str) -> LayerSpec:
        try:
            return self._layers[item_id]
        except KeyError as exc:
            raise KeyError(item_id) from exc

    def ingest(self, item_id: str):
        raise NotImplementedError("自定义 XYZ 是引用型，不入库")
