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
    # WMTS：capabilities 文档地址与其中的 Layer 标识。
    wmts_capabilities: str | None = None
    wmts_layer: str | None = None
    # 需要在展示时说清的重投影 / 基准差异。
    georeference_note: str = ""


class DataSourceProvider(Protocol):
    id: str
    capabilities: set[str]

    def authenticate(self, config: dict) -> None: ...

    def search(self, bbox, datetime_range, filters) -> list[CatalogItem]: ...

    def get_layer_spec(self, item_id: str) -> LayerSpec: ...

    def ingest(self, item_id: str): ...
