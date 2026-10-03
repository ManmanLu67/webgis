from typing import ClassVar

from app.providers.protocol import CatalogItem, LayerSpec


class TencentMapProvider:
    id = "tencent_map"
    capabilities: ClassVar[set[str]] = {"search"}
    availability = "needs_config"

    def authenticate(self, config: dict) -> None:
        secret = str((config.get("secrets") or {}).get("key") or "")
        self.availability = "ready" if secret else "needs_config"

    def search(self, bbox, datetime_range, filters) -> list[CatalogItem]:
        return []

    def get_layer_spec(self, item_id: str) -> LayerSpec:
        raise NotImplementedError("腾讯地图只走官方 SDK / JS API，不抓取瓦片，也不在 WGS84 地球上直接叠加 GCJ-02")

    def ingest(self, item_id: str):
        raise NotImplementedError("腾讯地图不入库")
