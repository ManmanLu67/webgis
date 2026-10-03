from datetime import UTC, datetime, timedelta
from typing import ClassVar

from app.providers.protocol import CatalogItem, LayerSpec

_TEMPLATE = (
    "https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/"
    "MODIS_Terra_CorrectedReflectance_TrueColor/default/{date}/"
    "GoogleMapsCompatible_Level9/{z}/{y}/{x}.jpg"
)
_LAG_DAYS = 5
_ATTRIBUTION = "NASA GIBS / EOSDIS"


class GibsProvider:
    id = "gibs"
    capabilities: ClassVar[set[str]] = {"search", "temporal"}
    availability = "ready"

    def __init__(self) -> None:
        self._layers: dict[str, LayerSpec] = {}

    def authenticate(self, config: dict) -> None:
        return None

    def search(self, bbox, datetime_range, filters) -> list[CatalogItem]:
        if not (filters or {}).get("fetch"):
            return []
        items = []
        for day in _candidate_days(datetime_range, (filters or {}).get("limit") or 8):
            day_text = day.isoformat()
            item_id = f"gibs-{day_text}"
            url = _TEMPLATE.format(date=day_text, z="{z}", y="{y}", x="{x}")
            self._layers[item_id] = LayerSpec(
                id=item_id,
                type="xyz",
                url=url,
                style={},
                time_dimension=day_text,
                publisher_id="gibs",
                url_template=_TEMPLATE,
                tiling_scheme="WebMercator",
                max_zoom=9,
                layer_kind="imagery",
                crs="EPSG:3857",
                attribution=_ATTRIBUTION,
            )
            items.append(
                CatalogItem(
                    id=item_id,
                    collection_id="gibs-modis-truecolor",
                    collection_title=f"MODIS 真彩色 {day_text}",
                    minx=-180,
                    miny=-85,
                    maxx=180,
                    maxy=85,
                    acquired_at=datetime(day.year, day.month, day.day, tzinfo=UTC),
                    cloud_cover=None,
                    asset_href=url,
                    access_mode="reference",
                )
            )
        return items

    def get_layer_spec(self, item_id: str) -> LayerSpec:
        return self._layers[item_id]

    def ingest(self, item_id: str):
        raise NotImplementedError("GIBS 是引用型服务，不入库")


def _candidate_days(datetime_range, limit) -> list:
    latest = datetime.now(UTC).date() - timedelta(days=_LAG_DAYS)
    if datetime_range and datetime_range[0]:
        day = datetime_range[0].astimezone(UTC).date()
        if day > latest:
            raise ValueError("这一天的全球拼接还没齐，请选更早的日期")
        return [day]
    count = max(int(limit or 1), 1)
    return [latest - timedelta(days=offset) for offset in range(count)]
