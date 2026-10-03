from datetime import UTC, datetime
from typing import ClassVar

from app.providers.protocol import CatalogItem, LayerSpec

_WMTS = (
    "https://t0.tianditu.gov.cn/img_w/wmts?SERVICE=WMTS&REQUEST=GetTile&VERSION=1.0.0"
    "&LAYER=img&STYLE=default&TILEMATRIXSET=w&FORMAT=tiles"
    "&TILEMATRIX={z}&TILEROW={y}&TILECOL={x}&tk={key}"
)


class TiandituProvider:
    id = "tianditu"
    capabilities: ClassVar[set[str]] = {"search"}
    availability = "needs_config"

    def __init__(self) -> None:
        self._key = ""
        self._layers: dict[str, LayerSpec] = {}

    def authenticate(self, config: dict) -> None:
        self._key = str((config.get("secrets") or {}).get("tk") or "")
        self.availability = "ready" if self._key else "needs_config"

    def search(self, bbox, datetime_range, filters) -> list[CatalogItem]:
        key = str((filters or {}).get("key") or self._key)
        if not key or not (filters or {}).get("fetch"):
            return []
        url = _WMTS.format(z="{z}", y="{y}", x="{x}", key=key)
        item_id = "tianditu-img"
        self._layers[item_id] = LayerSpec(
            id=item_id,
            type="xyz",
            url=url,
            style={},
            time_dimension=None,
            publisher_id="tianditu",
            url_template=_WMTS,
            tiling_scheme="WebMercator",
            max_zoom=18,
            layer_kind="imagery",
            crs="EPSG:4490",
            attribution="天地图。须标注审图号，署名以天地图当前要求为准。",
        )
        return [
            CatalogItem(
                id=item_id,
                collection_id="tianditu-img",
                collection_title="天地图影像",
                minx=-180,
                miny=-85,
                maxx=180,
                maxy=85,
                acquired_at=datetime.now(UTC),
                cloud_cover=None,
                asset_href=url,
                access_mode="reference",
            )
        ]

    def get_layer_spec(self, item_id: str) -> LayerSpec:
        return self._layers[item_id]

    def ingest(self, item_id: str):
        raise NotImplementedError("天地图是引用型官方服务，不入库，也不抓取瓦片")
