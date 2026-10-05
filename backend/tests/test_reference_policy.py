import importlib.util
from datetime import UTC, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load(plugin_id: str, class_name: str):
    path = ROOT / "plugins" / plugin_id / "provider.py"
    spec = importlib.util.spec_from_file_location(f"plugin_{plugin_id}", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    provider = getattr(module, class_name)()
    return provider


def test_wayback_item_url_uses_cesium_axes():
    provider = _load("arcgis_wayback", "WaybackProvider")

    def urlopen(request, timeout=0):
        class Body:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self):
                return (
                    b'{"9":{"itemID":"abc","itemTitle":"World Imagery (Wayback 2014-02-20)",'
                    b'"itemURL":"https://wayback.maptiles.arcgis.com/tile/9/{level}/{row}/{col}"}}'
                )

        return Body()

    provider._urlopen = urlopen
    provider.authenticate({"catalog_url": "https://example.invalid/wayback.json"})
    items = provider.search(None, None, {"fetch": True})
    assert items[0].asset_href.endswith("/{z}/{y}/{x}")


def test_wayback_lists_newest_release_first_and_honors_the_chosen_day():
    provider = _load("arcgis_wayback", "WaybackProvider")

    def urlopen(request, timeout=0):
        class Body:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self):
                return (
                    b'{"old":{"itemID":"old","itemTitle":"World Imagery (Wayback 2014-02-20)",'
                    b'"itemURL":"https://wayback.maptiles.arcgis.com/tile/old/{level}/{row}/{col}"},'
                    b'"new":{"itemID":"new","itemTitle":"World Imagery (Wayback 2026-08-05)",'
                    b'"itemURL":"https://wayback.maptiles.arcgis.com/tile/new/{level}/{row}/{col}"}}'
                )

        return Body()

    provider._urlopen = urlopen
    provider.authenticate({"catalog_url": "https://example.invalid/wayback.json"})
    items = provider.search(None, None, {"fetch": True, "limit": 5})
    assert [item.id for item in items] == ["new", "old"]
    start = datetime(2014, 2, 20, tzinfo=UTC)
    chosen = provider.search(None, (start, start + timedelta(days=1)), {"fetch": True, "limit": 5})
    assert [item.id for item in chosen] == ["old"]


def test_gibs_defaults_to_a_lagged_day_and_keeps_the_chosen_day():
    provider = _load("gibs", "GibsProvider")
    provider.authenticate({})
    items = provider.search(None, None, {"fetch": True, "limit": 3})
    latest = datetime.now(UTC).date() - timedelta(days=5)
    assert [item.acquired_at.date() for item in items] == [
        latest,
        latest - timedelta(days=1),
        latest - timedelta(days=2),
    ]
    assert datetime.now(UTC).date().isoformat() not in items[0].asset_href
    chosen_day = latest - timedelta(days=2)
    start = datetime(chosen_day.year, chosen_day.month, chosen_day.day, tzinfo=UTC)
    chosen = provider.search(None, (start, start + timedelta(days=1)), {"fetch": True, "limit": 3})
    assert [item.acquired_at.date() for item in chosen] == [chosen_day]
    assert chosen_day.isoformat() in chosen[0].asset_href
    provider = _load("gibs", "GibsProvider")
    provider.authenticate({})
    assert provider.search(None, None, {}) == []
    items = provider.search(None, None, {"fetch": True})
    assert len(items) >= 2
    assert "gibs.earthdata.nasa.gov" in items[0].asset_href
    layer = provider.get_layer_spec(items[0].id)
    assert layer.crs == "EPSG:4326"
    assert layer.tiling_scheme == "Geographic"
    assert layer.max_zoom == 5
    assert layer.level_zero_tiles_x == 10
    assert layer.level_zero_tiles_y == 5
    assert layer.level_offset == 3
    assert layer.tile_pixel_size == 512
    assert "epsg4326" in layer.url
    assert "VIIRS_SNPP_CorrectedReflectance_TrueColor" in layer.url
    assert "{gibsLevel}" in layer.url
    assert items[0].miny == -90 and items[0].maxy == 90
    assert "NASA" in layer.attribution
    # 重启后不靠内存：同一个 id 在新实例上也能重建
    fresh = _load("gibs", "GibsProvider")
    assert fresh.get_layer_spec(items[0].id).url == layer.url


def test_gibs_products_switch_the_layer_and_mark_seams():
    provider = _load("gibs", "GibsProvider")
    provider.authenticate({})
    listed = {row["id"]: row for row in provider.products()}
    assert listed["viirs-snpp"]["seam"] == "daily-seamless"
    assert listed["modis-terra"]["seam"] == "daily-gaps"
    assert listed["bluemarble"]["dated"] is False
    latest = datetime.now(UTC).date() - timedelta(days=5)
    start = datetime(latest.year, latest.month, latest.day, tzinfo=UTC)
    terra = provider.search(None, (start, start + timedelta(days=1)), {"fetch": True, "product": "modis-terra"})
    assert "MODIS_Terra_CorrectedReflectance_TrueColor" in terra[0].asset_href
    assert provider.get_layer_spec(terra[0].id).max_zoom == 5
    marble = provider.search(None, None, {"fetch": True, "product": "bluemarble"})
    assert len(marble) == 1
    assert "/default/500m/" in marble[0].asset_href
    assert marble[0].acquired_at.date().isoformat() not in marble[0].asset_href
    assert provider.get_layer_spec(marble[0].id).max_zoom == 4
    try:
        provider.search(None, None, {"fetch": True, "product": "nope"})
    except ValueError as exc:
        assert "没有这个" in str(exc)
    else:
        raise AssertionError("未知产品应当拒绝")


def test_tianditu_does_not_request_without_a_key():
    provider = _load("tianditu", "TiandituProvider")
    provider.authenticate({"credentials": ["tk"], "secrets": {}})
    assert provider.availability == "needs_config"
    assert provider.search(None, None, {"fetch": True}) == []


def test_tencent_has_no_tile_endpoint():
    source = (ROOT / "plugins" / "tencent_map" / "provider.py").read_text(encoding="utf-8")
    assert "map.qq.com" not in source
    provider = _load("tencent_map", "TencentMapProvider")
    provider.authenticate({"credentials": ["key"]})
    assert provider.search(None, None, {"fetch": True}) == []
    try:
        provider.get_layer_spec("any")
    except NotImplementedError as exc:
        assert "不抓取瓦片" in str(exc)
    else:
        raise AssertionError("腾讯地图不应交出瓦片图层")
