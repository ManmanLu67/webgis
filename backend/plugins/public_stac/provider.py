import json
import urllib.request
from datetime import UTC, datetime

from app.providers.protocol import CatalogItem, LayerSpec


class PublicStacProvider:
    """通用 STAC 检索。端点、集合和资产名都来自清单，不写死卫星波段。"""

    id = "public_stac"
    capabilities = {"search", "temporal"}
    availability = "ready"

    def __init__(self, urlopen=None) -> None:
        self._urlopen = urlopen or urllib.request.urlopen
        self.endpoint = ""
        self.collection = None
        self.asset_key = None
        self._layers: dict[str, LayerSpec] = {}

    def authenticate(self, config: dict) -> None:
        self.endpoint = str(config.get("endpoint") or "").rstrip("/")
        self.collection = config.get("collection") or None
        self.asset_key = config.get("asset_key") or None
        if not self.endpoint:
            raise ValueError("公开目录插件缺少 endpoint")

    def search(self, bbox, datetime_range, filters) -> list[CatalogItem]:
        if not (filters or {}).get("fetch"):
            return []
        if not bbox:
            raise ValueError("公开目录检索需要范围")
        payload: dict = {"limit": int((filters or {}).get("limit") or 1), "bbox": list(bbox)}
        if self.collection:
            payload["collections"] = [self.collection]
        if datetime_range and datetime_range[0] and datetime_range[1]:
            payload["datetime"] = f"{datetime_range[0].isoformat()}/{datetime_range[1].isoformat()}"
        payload["sortby"] = [{"field": "datetime", "direction": "desc"}]
        document = self._read_json(f"{self.endpoint}/search", payload)
        items = []
        for feature in document.get("features") or []:
            parsed = self._to_item(feature)
            if parsed is not None:
                items.append(parsed)
        items.sort(key=lambda item: item.acquired_at, reverse=True)
        if not items:
            raise ValueError("公开目录没有返回可用影像")
        return items

    def get_layer_spec(self, item_id: str) -> LayerSpec:
        try:
            return self._layers[item_id]
        except KeyError as exc:
            raise KeyError(item_id) from exc

    def ingest(self, item_id: str):
        raise NotImplementedError("公开目录是引用型数据源，不入库")

    def _to_item(self, feature: dict) -> CatalogItem | None:
        bbox = feature.get("bbox") or []
        if len(bbox) < 4:
            return None
        assets = feature.get("assets") or {}
        href = _asset_href(assets, self.asset_key)
        if not href:
            return None
        preview = _preview_href(assets)
        properties = feature.get("properties") or {}
        when = properties.get("datetime") or "2020-01-01T00:00:00Z"
        acquired = datetime.fromisoformat(str(when).replace("Z", "+00:00"))
        if acquired.tzinfo is None:
            acquired = acquired.replace(tzinfo=UTC)
        cloud = properties.get("eo:cloud_cover")
        item_id = str(feature.get("id"))
        self._layers[item_id] = LayerSpec(
            id=item_id,
            type="xyz" if preview else "cog",
            url=preview or href,
            style={},
            time_dimension=acquired.date().isoformat(),
            publisher_id="public_stac",
            tiling_scheme="WebMercator",
            layer_kind="imagery",
            crs="EPSG:4326",
            attribution="Copernicus Sentinel / USGS Landsat，经公开 STAC。许可以数据集说明为准。",
        )
        return CatalogItem(
            id=str(feature.get("id")),
            collection_id=str(feature.get("collection") or self.collection or "public-stac"),
            collection_title=str(self.collection or "公开目录"),
            minx=float(bbox[0]),
            miny=float(bbox[1]),
            maxx=float(bbox[2]),
            maxy=float(bbox[3]),
            acquired_at=acquired,
            cloud_cover=float(cloud) if cloud is not None else None,
            asset_href=href,
            access_mode="reference",
        )

    def _read_json(self, url: str, payload: dict) -> dict:
        request = urllib.request.Request(
            url,
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json", "Accept": "application/geo+json"},
        )
        with self._urlopen(request, timeout=20) as response:
            return json.loads(response.read().decode())


def _preview_href(assets: dict) -> str | None:
    for name in ("thumbnail", "rendered_preview", "preview"):
        href = str((assets.get(name) or {}).get("href") or "")
        if href.startswith("http"):
            return href
    return None


def _asset_href(assets: dict, preferred: str | None) -> str | None:
    if preferred and preferred in assets and assets[preferred].get("href"):
        return str(assets[preferred]["href"])
    for asset in assets.values():
        href = str(asset.get("href") or "")
        media = str(asset.get("type") or "")
        if href and ("tiff" in media or href.lower().split("?")[0].endswith((".tif", ".tiff"))):
            return href
    for asset in assets.values():
        if asset.get("href"):
            return str(asset["href"])
    return None
