from typing import ClassVar

from app.providers.protocol import CatalogItem, LayerSpec

_MESSAGE = "四维地球没有授权与接口文档，不抓取瓦片，也不编写猜测性接口。"


class SiweiProvider:
    id = "siwei"
    capabilities: ClassVar[set[str]] = {"search"}
    availability = "skeleton"

    def authenticate(self, config: dict) -> None:
        return None

    def search(self, bbox, datetime_range, filters) -> list[CatalogItem]:
        raise NotImplementedError(_MESSAGE)

    def get_layer_spec(self, item_id: str) -> LayerSpec:
        raise NotImplementedError(_MESSAGE)

    def ingest(self, item_id: str):
        raise NotImplementedError(_MESSAGE)
