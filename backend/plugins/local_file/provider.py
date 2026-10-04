from typing import ClassVar

from app.providers.protocol import CatalogItem, LayerSpec


class LocalFileProvider:
    id = "local_file"
    capabilities: ClassVar[set[str]] = {"search", "ingest"}
    availability = "ready"

    def authenticate(self, config: dict) -> None:
        return None

    def search(self, bbox, datetime_range, filters) -> list[CatalogItem]:
        return []

    def get_layer_spec(self, item_id: str) -> LayerSpec:
        raise NotImplementedError("本地影像的图层地址由上传完成后的发布步骤给出")

    def ingest(self, item_id: str):
        raise NotImplementedError("请使用上传接口入库。插件内不再做第二套转换。")
