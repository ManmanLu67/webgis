import json
import re
import urllib.request
from datetime import UTC, datetime

from app.providers.protocol import CatalogItem, LayerSpec


class WaybackProvider:
    id = "arcgis_wayback"
    capabilities = {"search", "temporal"}
    availability = "ready"

    def __init__(self, urlopen=None) -> None:
        self._urlopen = urlopen or urllib.request.urlopen
        self.catalog_url = ""
        self._items: list[CatalogItem] = []

    def authenticate(self, config: dict) -> None:
        self.catalog_url = str(config.get("catalog_url") or "")
        if not self.catalog_url:
            raise ValueError("历史版本插件缺少 catalog_url")

    def search(self, bbox, datetime_range, filters) -> list[CatalogItem]:
        if not (filters or {}).get("fetch"):
            return []
        document = self._read_json(self.catalog_url)
        items = sorted(_releases(document), key=lambda item: item.acquired_at, reverse=True)
        if datetime_range:
            start, end = datetime_range
            items = [
                item
                for item in items
                if (start is None or item.acquired_at >= start) and (end is None or item.acquired_at < end)
            ]
        if not items:
            raise ValueError("历史版本清单里没有带瓦片地址的记录")
        self._items = items
        limit = int((filters or {}).get("limit") or 1)
        return items[:limit]

    def get_layer_spec(self, item_id: str) -> LayerSpec:
        for item in self._items:
            if item.id == item_id:
                return LayerSpec(
                    id=item.id,
                    type="xyz",
                    url=item.asset_href,
                    style={},
                    time_dimension=item.acquired_at.date().isoformat(),
                    publisher_id="wayback",
                )
        raise KeyError(item_id)

    def ingest(self, item_id: str):
        raise NotImplementedError("历史版本是引用型数据源，不入库")

    def _read_json(self, url: str) -> dict:
        request = urllib.request.Request(url, headers={"Accept": "application/json"})
        with self._urlopen(request, timeout=20) as response:
            return json.loads(response.read().decode())


def _releases(document: dict) -> list[CatalogItem]:
    found = []
    for key, record in document.items():
        if not isinstance(record, dict):
            continue
        tile_url = record.get("tileUrl") or record.get("tile_url") or record.get("itemURL") or record.get("itemUrl")
        if not tile_url:
            continue
        tile_url = (
            str(tile_url)
            .replace("{level}", "{z}")
            .replace("{row}", "{y}")
            .replace("{col}", "{x}")
        )
        title = str(record.get("itemTitle") or record.get("title") or key)
        when = _title_date(title)
        found.append(
            CatalogItem(
                id=str(record.get("itemId") or key),
                collection_id="arcgis-wayback",
                collection_title=title,
                minx=-180,
                miny=-85,
                maxx=180,
                maxy=85,
                acquired_at=when,
                cloud_cover=0,
                asset_href=str(tile_url),
                access_mode="reference",
            )
        )
    return found


_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")


def _title_date(title: str) -> datetime:
    match = _DATE.search(title)
    if match:
        return datetime.fromisoformat(match.group(0)).replace(tzinfo=UTC)
    return datetime(2014, 2, 20, tzinfo=UTC)
