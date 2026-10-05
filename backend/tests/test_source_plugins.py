import importlib.util
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]


def _provider(plugin_id: str, class_name: str):
    path = ROOT / "plugins" / plugin_id / "provider.py"
    spec = importlib.util.spec_from_file_location(f"plugin_{plugin_id}", path)
    if spec is None or spec.loader is None:
        raise ImportError(path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return getattr(module, class_name)


class _Body:
    def __init__(self, payload: dict) -> None:
        self.payload = json.dumps(payload).encode()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self) -> bytes:
        return self.payload


def test_public_stac_parses_one_scene_without_credentials():
    fixture = {
        "features": [
            {
                "id": "scene-1",
                "collection": "sentinel-2-l2a",
                "bbox": [0, 0, 1, 1],
                "properties": {"datetime": "2024-05-01T00:00:00Z", "eo:cloud_cover": 3},
                "assets": {"visual": {"href": "https://example.invalid/scene-1.tif", "type": "image/tiff"}},
            }
        ]
    }

    def urlopen(request, timeout=0):
        return _Body(fixture)

    provider = _provider("public_stac", "PublicStacProvider")(urlopen=urlopen)
    provider.authenticate({"endpoint": "https://example.invalid/stac/v1", "collection": "sentinel-2-l2a", "credentials": []})
    items = provider.search((0, 0, 1, 1), None, {"fetch": True, "limit": 1})
    assert len(items) == 1
    assert items[0].asset_href.endswith(".tif")
    assert provider.search(None, None, {}) == []


def test_public_stac_sends_datetime_and_returns_the_newest_scene_first():
    captured: dict = {}
    fixture = {
        "features": [
            {
                "id": "older",
                "collection": "sentinel-2-l2a",
                "bbox": [0, 0, 1, 1],
                "properties": {"datetime": "2020-01-01T00:00:00Z"},
                "assets": {"visual": {"href": "https://example.invalid/older.tif", "type": "image/tiff"}},
            },
            {
                "id": "newer",
                "collection": "sentinel-2-l2a",
                "bbox": [0, 0, 1, 1],
                "properties": {"datetime": "2024-05-01T00:00:00Z"},
                "assets": {"visual": {"href": "https://example.invalid/newer.tif", "type": "image/tiff"}},
            },
        ]
    }

    def urlopen(request, timeout=0):
        captured["payload"] = json.loads(request.data.decode())
        return _Body(fixture)

    provider = _provider("public_stac", "PublicStacProvider")(urlopen=urlopen)
    provider.authenticate({"endpoint": "https://example.invalid/stac/v1", "collection": "sentinel-2-l2a", "credentials": []})
    start = datetime(2024, 5, 1, tzinfo=UTC)
    items = provider.search((116, 39, 117, 40), (start, start + timedelta(days=1)), {"fetch": True, "limit": 2})
    assert captured["payload"]["datetime"].startswith("2024-05-01")
    assert captured["payload"]["sortby"][0]["direction"] == "desc"
    assert [item.id for item in items] == ["newer", "older"]


def test_wayback_uses_only_listed_tile_urls():
    fixture = {
        "100": {"itemId": "100", "itemTitle": "2014-02-20", "note": "no tile"},
        "200": {
            "itemId": "200",
            "itemTitle": "2014-02-20",
            "tileUrl": "https://example.invalid/tile/200/{z}/{y}/{x}",
        },
    }

    def urlopen(request, timeout=0):
        return _Body(fixture)

    provider = _provider("arcgis_wayback", "WaybackProvider")(urlopen=urlopen)
    provider.authenticate({"catalog_url": "https://example.invalid/wayback.json", "credentials": []})
    items = provider.search(None, None, {"fetch": True, "limit": 5})
    assert [item.id for item in items] == ["200"]
    assert "{z}" in items[0].asset_href


def test_wayback_catalog_is_fetched_once_and_reused():
    """清单要缓存，否则打开一次选源弹层要下载两次。

    实测清单约 0.1 MB、下载一秒多；而打开弹层会先问"最近哪一景"、确认后再按日期取，
    两次 search 各自重新拉一遍就成了这个源明显变慢的原因。时钟注入，不真的等 TTL。
    """
    calls = []

    def urlopen(request, timeout=0):
        calls.append(request.full_url)
        return _Body({"200": {"itemId": "200", "itemTitle": "2014-02-20", "tileUrl": "u/{z}/{y}/{x}"}})

    now = [1000.0]
    provider = _provider("arcgis_wayback", "WaybackProvider")(
        urlopen=urlopen, clock=lambda: now[0]
    )
    provider.authenticate({"catalog_url": "https://example.invalid/wayback.json", "credentials": []})

    provider.search(None, None, {"fetch": True, "limit": 1})
    provider.search(None, None, {"fetch": True, "limit": 1})
    assert len(calls) == 1, calls

    # 过 TTL 之后要重新拉，否则历史版本新增了永远看不到
    now[0] += 3601.0
    provider.search(None, None, {"fetch": True, "limit": 1})
    assert len(calls) == 2, calls


def test_wayback_reuses_the_cache_across_different_dates():
    """按日期取也要命中同一份缓存 —— 那正是弹层确认时的那第二次 search。"""
    calls = []

    def urlopen(request, timeout=0):
        calls.append(request.full_url)
        return _Body({"200": {"itemId": "200", "itemTitle": "2014-02-20", "tileUrl": "u/{z}/{y}/{x}"}})

    provider = _provider("arcgis_wayback", "WaybackProvider")(urlopen=urlopen, clock=lambda: 0.0)
    provider.authenticate({"catalog_url": "https://example.invalid/wayback.json", "credentials": []})
    provider.search(None, None, {"fetch": True, "limit": 1})
    day = datetime(2014, 2, 20, tzinfo=UTC)
    provider.search(None, (day, day + timedelta(days=1)), {"fetch": True, "limit": 1})
    assert len(calls) == 1, calls


def test_skeleton_search_explains_itself():
    provider = _provider("jilin1", "Jilin1Provider")()
    try:
        provider.search(None, None, {"fetch": True})
    except NotImplementedError as exc:
        assert "无授权" in str(exc)
    else:
        raise AssertionError("骨架插件应当拒绝查询")


def test_installed_plugins_expose_status_without_naming_them_in_the_catalog(build_app):
    client = TestClient(build_app(plugins_dir=ROOT / "plugins"))
    rows = {row["id"]: row["availability"] for row in client.get("/providers").json()}
    assert rows["public_stac"] == "ready"
    assert rows["arcgis_wayback"] == "ready"
    assert rows["google_tiles"] == "needs_config"
    assert rows["jilin1"] == "skeleton"
    assert rows["beijing1"] == "skeleton"
    # gee 没接真实接口，所以是骨架而不是"待配置"——配了账号它也不会去调
    assert rows["gee"] == "skeleton"
    catalog = "\n".join(path.read_text(encoding="utf-8") for path in (ROOT / "app" / "catalog").glob("*.py"))
    assert "public_stac" not in catalog
    assert "jilin1" not in catalog
    assert client.post("/providers/jilin1/search", json={"bbox": [0, 0, 1, 1]}).status_code == 501
    listed = {row["id"]: row for row in client.get("/providers").json()}
    assert listed["gibs"]["drape"] is True
    assert listed["arcgis_wayback"]["drape"] is True
    assert listed["public_stac"]["drape"] is True
    assert listed["public_stac"]["picker"] == "extent"
    assert listed["custom_xyz"]["picker"] == "template"
    assert listed["jilin1"]["drape"] is False
    assert listed["tianditu"]["drape"] is False
    assert listed["tencent_map"]["drape"] is False
    assert listed["local_file"]["drape"] is False
    day = (datetime.now(UTC).date() - timedelta(days=6)).isoformat()
    found = client.post("/providers/gibs/search", json={"datetime": day, "limit": 1})
    assert found.status_code == 200
    assert day in found.json()["items"][0]["layer"]["url"]
    assert found.json()["items"][0]["time"] == day


def test_search_without_a_bbox_is_not_a_malformed_bbox(build_app):
    """`picker: time` 的源不需要范围，前端过去发的是 `bbox: []`。

    空数组过去被判成"给了范围但长度不对"而 400，于是 GIBS 与 Wayback 在界面上
    一点就报"范围需要四个数"，永远走不到选时间那一步。空数组必须与"没给范围"
    同义：GIBS 忽略 bbox（全球），Wayback 也按清单返回。
    """
    client = TestClient(build_app(plugins_dir=ROOT / "plugins"))
    for provider_id in ("gibs", "arcgis_wayback"):
        empty = client.post(f"/providers/{provider_id}/search", json={"limit": 1, "bbox": []})
        assert empty.status_code == 200, (provider_id, empty.status_code, empty.text)
        omitted = client.post(f"/providers/{provider_id}/search", json={"limit": 1})
        assert omitted.status_code == 200, (provider_id, omitted.status_code, omitted.text)
        assert len(empty.json()["items"]) == len(omitted.json()["items"]) == 1


def test_a_present_bbox_still_has_to_have_four_numbers(build_app):
    """放宽只针对"空"，不是放弃校验：三个数或五个数仍然要拒。"""
    client = TestClient(build_app(plugins_dir=ROOT / "plugins"))
    for bbox in ([0, 0, 1], [0, 0, 1, 1, 1]):
        bad = client.post("/providers/public_stac/search", json={"limit": 1, "bbox": bbox})
        assert bad.status_code == 400, (bbox, bad.status_code, bad.text)
        assert "范围需要四个数" in bad.json()["detail"]


def test_gibs_layer_has_no_coverage_field(build_app):
    """图层描述里没有覆盖范围字段了。

    曾经加过 `coverage_bbox` 用来裁掉 GIBS 在 ±85° 以外的纯黑 no-data 瓦片，
    后来撤回 —— 所以这里钉住"没有这个字段"，免得以后当成漏删。
    """
    client = TestClient(build_app(plugins_dir=ROOT / "plugins"))
    day = (datetime.now(UTC).date() - timedelta(days=6)).isoformat()
    found = client.post("/providers/gibs/search", json={"datetime": day, "limit": 1})
    assert "coverage_bbox" not in found.json()["items"][0]["layer"]


def test_history_source_asks_for_used_layers_not_for_a_time(build_app):
    """历史版本不选时间，走"本机用过的图层"。

    它的清单有 196 个历史版本，摊成日期列表既慢又没意义；而"回到以前看过的那一景"
    才是这个源的用途。选时相的入口留给 GIBS、公开 STAC 这类每日更新的源。
    """
    client = TestClient(build_app(plugins_dir=ROOT / "plugins"))
    listed = {row["id"]: row for row in client.get("/providers").json()}
    assert listed["arcgis_wayback"]["picker"] == "recent"
    assert listed["gibs"]["picker"] == "time"
    assert listed["public_stac"]["picker"] == "extent"
    # 不选时间的源不该带任何时间相关字段
    assert "time_choices" not in listed["arcgis_wayback"]
