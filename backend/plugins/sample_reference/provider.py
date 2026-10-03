from datetime import UTC, datetime

from app.providers.protocol import CatalogItem, LayerSpec


class ReferenceProvider:
    id = "sample_reference"
    capabilities = {"search", "temporal"}

    def authenticate(self, config: dict) -> None:
        return None

    def search(self, bbox, datetime_range, filters) -> list[CatalogItem]:
        return [
            CatalogItem(
                id="ref-clear",
                collection_id="sample-reference",
                collection_title="示例引用",
                minx=-1,
                miny=-1,
                maxx=1,
                maxy=1,
                acquired_at=datetime(2020, 6, 1, tzinfo=UTC),
                cloud_cover=5,
                asset_href="https://example.invalid/ref-clear.tif",
                access_mode="reference",
            )
        ]

    def get_layer_spec(self, item_id: str) -> LayerSpec:
        raise NotImplementedError("layer addresses come from TilePublisher")

    def ingest(self, item_id: str):
        raise NotImplementedError("reference sources are not ingested")
