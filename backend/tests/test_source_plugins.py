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
