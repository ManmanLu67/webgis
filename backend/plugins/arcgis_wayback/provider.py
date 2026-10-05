import json
import re
import time
import urllib.request
from datetime import UTC, datetime
from typing import ClassVar

from app.providers.protocol import CatalogItem, LayerSpec

# 清单缓存多久。清单本身不大（实测约 0.1 MB / 196 条），但一次下载要一秒多，
# 而打开一次选源弹层会触发两次 search（先问"最近哪一景"，确认后再按日期取），
# 所以每次都重新拉会让这个源明显变慢。一小时足够 —— 历史版本清单不是分钟级变化的。
CATALOG_TTL_SECONDS = 3600.0


class WaybackProvider:
    id = "arcgis_wayback"
    capabilities: ClassVar[set[str]] = {"search", "temporal"}
    availability = "ready"

    def __init__(self, urlopen=None, clock=time.monotonic) -> None:
        self._urlopen = urlopen or urllib.request.urlopen
        self._clock = clock
        self.catalog_url = ""
        self._items: list[CatalogItem] = []
        self._catalog: dict | None = None
        self._catalog_at = 0.0
        self._ttl = CATALOG_TTL_SECONDS

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
        """取清单，带进程内缓存。

        缓存的是**解析后的 JSON 对象**，不是原始字节 —— `_releases` 要遍历全部记录，
        而一次 search 只要排序后的前几条，但遍历本身得先有一份完整的文档。

        时钟可注入，这样测试不用真的等一小时。
        """
        fresh_enough = self._catalog is not None and (self._clock() - self._catalog_at) < self._ttl
        if fresh_enough and self._catalog is not None:
            return self._catalog
        request = urllib.request.Request(url, headers={"Accept": "application/json"})
        with self._urlopen(request, timeout=20) as response:
            document = json.loads(response.read().decode())
        self._catalog = document
        self._catalog_at = self._clock()
        return document


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
