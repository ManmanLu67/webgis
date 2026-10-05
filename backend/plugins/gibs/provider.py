from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import ClassVar

from app.providers.protocol import CatalogItem, LayerSpec

# EPSG:4326 的 250m / 500m 格网不是标准四叉树：
# 0–2 级是 2×1 / 3×2 / 5×3（单片 288° / 144° / 72°，行数是向上取整，带越界），
# 从第 3 级起才是落在 ±180/±90 上的干净倍增金字塔，零级为 10×5、单片 36°。
# Cesium 的 GeographicTilingScheme 以这个 10×5 为零级，URL 里的级别要加 3。
_BASE = "https://gibs.earthdata.nasa.gov/wmts/epsg4326/best"
_LEVEL_ZERO_X = 10
_LEVEL_ZERO_Y = 5
_LEVEL_OFFSET = 3
_TILE_PX = 512
_LAG_DAYS = 5
_ATTRIBUTION = "NASA GIBS / EOSDIS"

_SEAM_LABEL = {
    "daily-seamless": "单日无缝",
    "daily-gaps": "单日带轨道间隙",
    "composite": "8 天合成无缝",
    "static": "静态无缝",
}
_SEAM_NOTE = {
    "daily-seamless": "单日满幅，相邻轨道互相重叠。扫描带边缘仍可能有明暗差：源数据只做了瑞利校正，不是拼接错位。",
    "daily-gaps": "这一天单星盖不满赤道，会出现黑色轨道间隙。间隙和扫描带边缘的明暗来自源数据，不是叠加错位。",
    "composite": "多日合成，没有轨道间隙，辐射也更一致。",
    "static": "静态全球合成，没有日期，完全无缝。",
}


@dataclass(frozen=True)
class _Product:
    id: str
    layer: str
    title: str
    seam: str
    resolution: str
    matrix: str
    dated: bool


# 250m 的 GIBS 最高级是 8，500m 是 7。前端的 max_zoom 是 Cesium 的级别，
# 已经减去偏移，所以分别是 5 和 4。
_PRODUCTS: tuple[_Product, ...] = (
    _Product(
        "viirs-snpp",
        "VIIRS_SNPP_CorrectedReflectance_TrueColor",
        "VIIRS SNPP 真彩色",
        "daily-seamless",
        "250 m",
        "250m",
        True,
    ),
    _Product(
        "viirs-noaa20",
        "VIIRS_NOAA20_CorrectedReflectance_TrueColor",
        "VIIRS NOAA-20 真彩色",
        "daily-seamless",
        "250 m",
        "250m",
        True,
    ),
    _Product(
        "modis-terra",
        "MODIS_Terra_CorrectedReflectance_TrueColor",
        "MODIS Terra 真彩色",
        "daily-gaps",
        "250 m",
        "250m",
        True,
    ),
    _Product(
        "modis-aqua",
        "MODIS_Aqua_CorrectedReflectance_TrueColor",
        "MODIS Aqua 真彩色",
        "daily-gaps",
        "250 m",
        "250m",
        True,
    ),
    _Product(
        "viirs-snpp-8day",
        "VIIRS_SNPP_L3_SurfaceReflectance_BandsM5-M4-M3_8Day",
        "VIIRS SNPP 8 天合成",
        "composite",
        "500 m",
        "500m",
        True,
    ),
    _Product(
        "modis-terra-8day",
        "MODIS_Terra_L3_SurfaceReflectance_Bands143_8Day",
        "MODIS Terra 8 天合成",
        "composite",
        "500 m",
        "500m",
        True,
    ),
    _Product(
        "bluemarble",
        "BlueMarble_NextGeneration",
        "Blue Marble",
        "static",
        "500 m",
        "500m",
        False,
    ),
)
_BY_ID = {product.id: product for product in _PRODUCTS}
_DEFAULT_ID = "viirs-snpp"


def _max_zoom(matrix: str) -> int:
    gibs_max = 8 if matrix == "250m" else 7
    return gibs_max - _LEVEL_OFFSET


def _url(product: _Product, day: str | None) -> str:
    level = "{gibsLevel}/{y}/{x}.jpg"
    if product.dated:
        return f"{_BASE}/{product.layer}/default/{day}/{product.matrix}/{level}"
    return f"{_BASE}/{product.layer}/default/{product.matrix}/{level}"


def _item_id(product: _Product, day: str | None) -> str:
    if day:
        return f"gibs-{product.id}-{day}"
    return f"gibs-{product.id}"


def _parse_item_id(item_id: str) -> tuple[_Product, str | None]:
    """id 里带着产品和日期，重启后不用内存字典也能把图层描述重建出来。"""
    rest = item_id.removeprefix("gibs-")
    for product in sorted(_PRODUCTS, key=lambda item: len(item.id), reverse=True):
        if rest == product.id:
            return product, None
        prefix = f"{product.id}-"
        if rest.startswith(prefix):
            return product, rest[len(prefix) :]
    raise KeyError(item_id)


def _spec(product: _Product, day: str | None) -> LayerSpec:
    return LayerSpec(
        id=_item_id(product, day),
        type="xyz",
        url=_url(product, day),
        style={"product": product.id, "seam": product.seam},
        time_dimension=day,
        publisher_id="gibs",
        url_template=_url(product, "{date}" if product.dated else None),
        tiling_scheme="Geographic",
        max_zoom=_max_zoom(product.matrix),
        layer_kind="imagery",
        crs="EPSG:4326",
        attribution=_ATTRIBUTION,
        georeference_note=_SEAM_NOTE[product.seam],
        level_zero_tiles_x=_LEVEL_ZERO_X,
        level_zero_tiles_y=_LEVEL_ZERO_Y,
        level_offset=_LEVEL_OFFSET,
        tile_pixel_size=_TILE_PX,
    )


class GibsProvider:
    id = "gibs"
    capabilities: ClassVar[set[str]] = {"search", "temporal"}
    availability = "ready"

    def authenticate(self, config: dict) -> None:
        return None

    def products(self) -> list[dict]:
        return [
            {
                "id": product.id,
                "title": product.title,
                "seam": product.seam,
                "seam_label": _SEAM_LABEL[product.seam],
                "resolution": product.resolution,
                "dated": product.dated,
                "note": _SEAM_NOTE[product.seam],
            }
            for product in _PRODUCTS
        ]

    def search(self, bbox, datetime_range, filters) -> list[CatalogItem]:
        if not (filters or {}).get("fetch"):
            return []
        product = _BY_ID.get(str((filters or {}).get("product") or _DEFAULT_ID))
        if product is None:
            raise ValueError("没有这个 GIBS 产品")
        if not product.dated:
            return [_item(product, None)]
        days = _candidate_days(datetime_range, (filters or {}).get("limit") or 8)
        return [_item(product, day.isoformat()) for day in days]

    def get_layer_spec(self, item_id: str) -> LayerSpec:
        product, day = _parse_item_id(item_id)
        if product.dated and not day:
            raise KeyError(item_id)
        return _spec(product, day)

    def ingest(self, item_id: str):
        raise NotImplementedError("GIBS 是引用型服务，不入库")


def _item(product: _Product, day: str | None) -> CatalogItem:
    acquired = (
        datetime.fromisoformat(day).replace(tzinfo=UTC)
        if day
        else datetime(2004, 7, 1, tzinfo=UTC)
    )
    return CatalogItem(
        id=_item_id(product, day),
        collection_id=f"gibs-{product.id}",
        collection_title=f"{product.title} {day}" if day else product.title,
        minx=-180,
        miny=-90,
        maxx=180,
        maxy=90,
        acquired_at=acquired,
        cloud_cover=None,
        asset_href=_url(product, day),
        access_mode="reference",
    )


def _candidate_days(datetime_range, limit) -> list:
    latest = datetime.now(UTC).date() - timedelta(days=_LAG_DAYS)
    if datetime_range and datetime_range[0]:
        day = datetime_range[0].astimezone(UTC).date()
        if day > latest:
            raise ValueError("这一天的全球拼接还没齐，请选更早的日期")
        return [day]
    count = max(int(limit or 1), 1)
    return [latest - timedelta(days=offset) for offset in range(count)]
