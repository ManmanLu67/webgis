import json
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from typing import ClassVar

from app.providers.protocol import CatalogItem, LayerSpec


class GoogleTilesProvider:
    id = "google_tiles"
    capabilities: ClassVar[set[str]] = {"search"}
    availability = "needs_config"

    def __init__(self) -> None:
        self._layers: dict[str, LayerSpec] = {}
        self._key = ""

    def authenticate(self, config: dict) -> None:
        secrets = config.get("secrets") or {}
        required = config.get("credentials") or []
        self._key = str(secrets.get("api_key") or "")
        self.availability = "needs_config" if required and not secrets else "ready"

    def search(self, bbox, datetime_range, filters) -> list[CatalogItem]:
        key = str((filters or {}).get("key") or self._key)
        if not key or not (filters or {}).get("fetch"):
            return []
        session = _create_session(key)
        quoted_key = urllib.parse.quote(key, safe="")
        url = f"https://tile.googleapis.com/v1/2dtiles/{{z}}/{{x}}/{{y}}?session={session}&key={quoted_key}"
        item_id = "google-satellite"
        self._layers[item_id] = LayerSpec(
            id=item_id,
            type="xyz",
            url=url,
            style={},
            time_dimension=None,
            publisher_id="google_tiles",
            url_template=url,
            tiling_scheme="WebMercator",
            max_zoom=20,
            layer_kind="imagery",
            crs="EPSG:3857",
            attribution="Google Maps",
        )
        return [
            CatalogItem(
                id=item_id,
                collection_id="google-map-tiles",
                collection_title="Google 卫星影像",
                minx=-180,
                miny=-85,
                maxx=180,
                maxy=85,
                acquired_at=datetime.now(UTC),
                cloud_cover=None,
                asset_href=url,
                access_mode="reference",
            )
        ]

    def get_layer_spec(self, item_id: str) -> LayerSpec:
        return self._layers[item_id]

    def ingest(self, item_id: str):
        raise NotImplementedError("官方地图瓦片是引用型数据源，不入库")


def _create_session(key: str) -> str:
    payload = json.dumps({"mapType": "satellite", "language": "zh-CN", "region": "US"}).encode()
    request = urllib.request.Request(
        "https://tile.googleapis.com/v1/createSession?key=" + urllib.parse.quote(key, safe=""),
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            document = json.loads(response.read().decode())
    except Exception as exc:
        raise ValueError("官方地图瓦片会话创建失败") from exc
    session = document.get("session")
    if not session:
        raise ValueError("官方地图瓦片没有返回会话")
    return str(session)
