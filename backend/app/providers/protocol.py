from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass
class CatalogItem:
    id: str
    collection_id: str
    collection_title: str
    minx: float
    miny: float
    maxx: float
    maxy: float
    acquired_at: datetime
    cloud_cover: float | None
    asset_href: str
    access_mode: str


@dataclass
class LayerSpec:
    id: str
    type: str
    url: str
    style: dict
    time_dimension: str | None
    publisher_id: str
    url_template: str | None = None
    # 只描述瓦片网格：Cesium 认的是这个，不是 crs。
    tiling_scheme: str = "WebMercator"
    max_zoom: int | None = None
    layer_kind: str = "imagery"
    # 数据基准。用于署名与合规声明，不参与渲染决策。
    crs: str = "EPSG:4326"
    attribution: str = ""
    # WMTS：两种编码都要能描述。
    # RESTful 给了瓦片模板；KVP 只给基地址，其余靠下面的字段补齐
    # （天地图就是 KVP，且要求 VERSION=1.0.0 与 FORMAT=tiles）。
    wmts_capabilities: str | None = None
    wmts_layer: str | None = None
    wmts_tile_template: str | None = None
    wmts_style: str = "default"
    wmts_tile_matrix_set_id: str = "WebMercatorQuad"
    wmts_format: str = "image/png"
    wmts_dimensions: dict[str, str] | None = None
    # 需要在展示时说清的重投影 / 基准差异。
    georeference_note: str = ""
    # 非标准四叉树才填。默认 2×1、偏移 0、256px 就是 Cesium 的 Geographic 零级，
    # 现有源不声明这四项时行为不变。GIBS 的 4326 格网从第 3 级起才是
    # 10×5 的干净金字塔，所以要单独声明零级行列、层级偏移和瓦片像素。
    level_zero_tiles_x: int = 2
    level_zero_tiles_y: int = 1
    level_offset: int = 0
    tile_pixel_size: int = 256


class DataSourceProvider(Protocol):
    id: str
    capabilities: set[str]

    def authenticate(self, config: dict) -> None: ...

    def search(self, bbox, datetime_range, filters) -> list[CatalogItem]: ...

    def get_layer_spec(self, item_id: str) -> LayerSpec: ...

    def ingest(self, item_id: str): ...
