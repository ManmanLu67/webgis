from typing import ClassVar

from app.providers.protocol import CatalogItem, LayerSpec

_MESSAGE = "无授权与接口文档，不提供真实查询或入库。可把影像交给本地文件插件。"


class Beijing1Provider:
    id = "beijing1"
    capabilities: ClassVar[set[str]] = {"search", "ingest"}
    availability = "skeleton"

    def authenticate(self, config: dict) -> None:
        return None

    def search(self, bbox, datetime_range, filters) -> list[CatalogItem]:
        raise NotImplementedError(_MESSAGE)

    def get_layer_spec(self, item_id: str) -> LayerSpec:
        raise NotImplementedError(_MESSAGE)

    def ingest(self, item_id: str):
        raise NotImplementedError(_MESSAGE)
