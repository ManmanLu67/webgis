from datetime import UTC, datetime
from typing import ClassVar

from app.providers.protocol import CatalogItem, LayerSpec


class IngestProvider:
    id = "sample_ingest"
    capabilities: ClassVar[set[str]] = {"search", "ingest"}

    def authenticate(self, config: dict) -> None:
        return None

    def search(self, bbox, datetime_range, filters) -> list[CatalogItem]:
        return [
            CatalogItem(
                id="ing-1",
                collection_id="sample-ingest",
                collection_title="示例入库",
                minx=-1,
                miny=-1,
                maxx=1,
                maxy=1,
                acquired_at=datetime(2021, 1, 1, tzinfo=UTC),
                cloud_cover=1,
                asset_href="file:///data/ing-1.tif",
                access_mode="ingest",
            )
        ]

    def get_layer_spec(self, item_id: str) -> LayerSpec:
        raise NotImplementedError("layer addresses come from TilePublisher")

    def ingest(self, item_id: str):
        raise NotImplementedError("COG conversion is Spec 002")
