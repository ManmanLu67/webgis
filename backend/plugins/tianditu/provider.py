from datetime import UTC, datetime
from typing import ClassVar

from app.providers.protocol import CatalogItem, LayerSpec

# 天地图的官方 WMTS 是 KVP 编码：基地址 + 查询参数，GetTile 形如
#   {base}?SERVICE=WMTS&REQUEST=GetTile&VERSION=1.0.0&LAYER=img&STYLE=default
#        &TILEMATRIXSET=w&FORMAT=tiles&TILEMATRIX={z}&TILEROW={y}&TILECOL={x}&tk={key}
# 所以这里给的是**基地址**，图层、格网、格式与 Key 走 wmts_* 字段，
# 由客户端补成查询参数。不自己拼 GetTile 全串，省得两处逻辑漂移。
_WMTS_BASE = "https://t0.tianditu.gov.cn/img_w/wmts"

# 保留一份完整模板，供不认 WMTS 的消费者（例如 QGIS 的自定义 XYZ 源）直接引用。
_WMTS_GET_TILE = (
    f"{_WMTS_BASE}?SERVICE=WMTS&REQUEST=GetTile&VERSION=1.0.0"
    "&LAYER=img&STYLE=default&TILEMATRIXSET=w&FORMAT=tiles"
    "&TILEMATRIX={{z}}&TILEROW={{y}}&TILECOL={{x}}&tk={{key}}"
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
        item_id = "tianditu-img"
        self._layers[item_id] = LayerSpec(
            id=item_id,
            type="wmts",
            url=_WMTS_BASE,
            style={},
            time_dimension=None,
            publisher_id="tianditu",
            url_template=_WMTS_GET_TILE.format(key=key),
            # TILEMATRIXSET=w 就是 Web Mercator 网格。数据基准是 CGCS2000，
            # 但服务方已经把它重投影进网格了，浏览器拿到的是网格上的图像字节，
            # 所以 crs 只作声明用，不参与渲染（见前端 georeference.ts）。
            tiling_scheme="WebMercator",
            max_zoom=18,
            layer_kind="imagery",
            crs="EPSG:4490",
            attribution="天地图。须标注审图号，署名以天地图当前要求为准。",
            wmts_capabilities=f"{_WMTS_BASE}?SERVICE=WMTS&REQUEST=GetCapabilities",
            wmts_layer="img",
            wmts_style="default",
            wmts_tile_matrix_set_id="w",
            # 天地图的 FORMAT 是 tiles，不是标准的 image/jpeg
            wmts_format="tiles",
            wmts_dimensions={"tk": key},
            georeference_note="CGCS2000 基准，与 WGS84 差异在厘米级，可直接叠加",
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
                asset_href=self._layers[item_id].url_template,
                access_mode="reference",
            )
        ]

    def get_layer_spec(self, item_id: str) -> LayerSpec:
        return self._layers[item_id]

    def ingest(self, item_id: str):
        raise NotImplementedError("天地图是引用型官方服务，不入库，也不抓取瓦片")