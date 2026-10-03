from app.providers.protocol import CatalogItem, LayerSpec


class GeeProvider:
    id = "gee"
    capabilities = {"search"}
    availability = "needs_config"

    def authenticate(self, config: dict) -> None:
        secrets = config.get("secrets") or {}
        required = config.get("credentials") or []
        self.availability = "needs_config" if required and not secrets else "ready"

    def search(self, bbox, datetime_range, filters) -> list[CatalogItem]:
        if self.availability == "needs_config":
            return []
        raise NotImplementedError("账号已配置，但本插件仍不调用地球引擎接口")

    def get_layer_spec(self, item_id: str) -> LayerSpec:
        raise NotImplementedError("地球引擎需配置后才有图层")

    def ingest(self, item_id: str):
        raise NotImplementedError("地球引擎插件不入库")
