from typing import Protocol
from urllib.parse import quote

from app.models import Item
from app.providers.protocol import LayerSpec


class TilePublisher(Protocol):
    id: str

    def publish(self, item: Item) -> LayerSpec: ...

    def unpublish(self, layer_id: str) -> None: ...


class UrlTemplatePublisher:
    def __init__(self, publisher_id: str, layer_type: str, url_template: str) -> None:
        self.id = publisher_id
        self.layer_type = layer_type
        self.url_template = url_template

    def publish(self, item: Item) -> LayerSpec:
        when = item.acquired_at.isoformat()
        return LayerSpec(
            id=f"{item.id}:{self.id}",
            type=self.layer_type,
            url=self.url_template.format(item_id=quote(item.id), asset_href=quote(item.asset_href, safe="")),
            style={},
            time_dimension=when,
            publisher_id=self.id,
        )

    def unpublish(self, layer_id: str) -> None:
        return None
