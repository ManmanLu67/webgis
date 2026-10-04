from typing import ClassVar

from app.providers.protocol import CatalogItem, LayerSpec


# 状态说明（写在这里而不只是 plugin.yaml）：manifest 的 status 是 skeleton，
# 不是 implemented —— 配了账号也不会真去调 Earth Engine 接口。
#
# 它原先写的是 implemented，但 search() 无论配没配账号都拿不到结果（配了就抛
# NotImplementedError），于是界面上它看起来"可用"，点进去才发现不行。
#
# 按宪章 C4，没接的来源只提供骨架。想真接的话：Earth Engine 的 Python API 需要
# service account JSON，且导出的是 GeoTIFF 而不是瓦片地址，所以落地路径是走
# ingest 转 COG 再发布，而不是直接给图层地址。
class GeeProvider:
    id = "gee"
    capabilities: ClassVar[set[str]] = {"search"}
    availability = "skeleton"

    def authenticate(self, config: dict) -> None:
        # 骨架不读凭据，也就不该因为凭据而在界面上变成"可用"
        self.availability = "skeleton"

    def search(self, bbox, datetime_range, filters) -> list[CatalogItem]:
        raise NotImplementedError("地球引擎未接入：需要 service account，且导出走入库而非直接给瓦片")

    def get_layer_spec(self, item_id: str) -> LayerSpec:
        raise NotImplementedError("地球引擎未接入，没有图层")

    def ingest(self, item_id: str):
        raise NotImplementedError("地球引擎未接入")
