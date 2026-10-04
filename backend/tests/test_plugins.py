import json
from pathlib import Path

import pytest
from app.catalog.sync import _config_json
from app.plugins.loader import (
    AVAILABILITIES,
    MODES,
    PICKERS,
    REQUIRED_FIELDS,
    STATUSES,
    load_plugins,
)
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]

STUB = (
    "class Stub:\n"
    "    id = 'stub'\n"
    "    capabilities = set()\n"
    "    def authenticate(self, config):\n"
    "        return None\n"
    "    def search(self, bbox, datetime_range, filters):\n"
    "        return []\n"
    "    def get_layer_spec(self, item_id):\n"
    "        raise NotImplementedError\n"
    "    def ingest(self, item_id):\n"
    "        raise NotImplementedError\n"
)

VALID = """
id: {name}
name: {name}
version: 0.1.0
mode: reference
capabilities: [search]
credentials: []
license_note: demo
cache_allowed: false
status: implemented
availability: ready
drape: true
picker: template
entrypoint: provider:Stub
"""


def _write_plugin(directory: Path, name: str, body: str) -> Path:
    plugin = directory / name
    plugin.mkdir()
    (plugin / "plugin.yaml").write_text(body, encoding="utf-8")
    (plugin / "provider.py").write_text(STUB, encoding="utf-8")
    return plugin


@pytest.fixture
def plugin_dir(tmp_path: Path) -> Path:
    directory = tmp_path / "custom-plugins"
    directory.mkdir()
    return directory


def _load(directory: Path, name: str, body: str):
    _write_plugin(directory, name, body)
    return load_plugins(directory)


# --- 一个坏插件不该拖垮其他插件 ---


def test_missing_field_does_not_block_other_plugins(plugin_dir, build_app):
    _write_plugin(plugin_dir, "good", VALID.format(name="good"))
    broken = plugin_dir / "bad"
    broken.mkdir()
    (broken / "plugin.yaml").write_text("id: bad\nversion: 0.1.0\n", encoding="utf-8")
    report = load_plugins(plugin_dir)
    assert [item.manifest["id"] for item in report.loaded] == ["good"]
    assert any("missing field: name" in error for error in report.errors)

    client = TestClient(build_app(plugins_dir=plugin_dir))
    ids = [row["id"] for row in client.get("/providers").json()]
    assert ids == ["good"]
    assert any("missing field: name" in error for error in client.get("/providers/errors").json())


def test_broken_yaml_is_reported_without_raising(plugin_dir):
    plugin = plugin_dir / "broken"
    plugin.mkdir()
    (plugin / "plugin.yaml").write_text("id: [unclosed\n", encoding="utf-8")
    report = load_plugins(plugin_dir)
    assert report.loaded == []
    assert any("invalid plugin.yaml" in error for error in report.errors)


def test_manifest_that_is_not_a_mapping_is_rejected(plugin_dir):
    plugin = plugin_dir / "listy"
    plugin.mkdir()
    (plugin / "plugin.yaml").write_text("- a\n- b\n", encoding="utf-8")
    report = load_plugins(plugin_dir)
    assert any("must be a mapping" in error for error in report.errors)


def test_id_must_match_the_directory_name(plugin_dir):
    _write_plugin(plugin_dir, "dirname", VALID.format(name="different"))
    report = load_plugins(plugin_dir)
    assert report.loaded == []
    assert any("does not match directory name" in error for error in report.errors)


def test_missing_entrypoint_class_is_reported(plugin_dir):
    _write_plugin(plugin_dir, "noent", VALID.format(name="noent").replace("Stub", "Nope"))
    report = load_plugins(plugin_dir)
    assert any("Nope" in error for error in report.errors)


# --- 前端依赖的三个字段必须显式声明且取值合法 ---


@pytest.mark.parametrize("key", ["availability", "drape", "picker"])
def test_front_end_fields_are_required(plugin_dir, key):
    """这三个字段一漏，界面上就静默少一个源，而且没有任何报错。"""
    body = "\n".join(
        line for line in VALID.format(name="x").splitlines() if not line.startswith(f"{key}:")
    )
    report = _load(plugin_dir, "x", body)
    assert report.loaded == []
    assert any(f"missing field: {key}" in error for error in report.errors)


@pytest.mark.parametrize(
    ("field", "value", "expected"),
    [
        ("mode", "sideways", "invalid mode"),
        ("status", "halfway", "invalid status"),
        ("availability", "probably", "invalid availability"),
        ("picker", "vibes", "invalid picker"),
        ("drape", "yes-please", "drape must be"),
    ],
)
def test_invalid_values_are_rejected_with_the_allowed_options(plugin_dir, field, value, expected):
    body = VALID.format(name="x").replace(
        f"{field}: ", f"{field}: {value} # ", 1
    )
    report = _load(plugin_dir, "x", body)
    assert report.loaded == []
    errors = [error for error in report.errors if expected in error]
    assert errors, f"没有报出 {expected}，实际：{report.errors}"
    if field != "drape":
        assert "可选" in errors[0], "报错要说清可选值，插件作者才改得动"


def test_skeleton_and_availability_must_agree(plugin_dir):
    """两处状态不一致会让界面和后端各说各话。"""
    mismatched = VALID.format(name="x").replace("status: implemented", "status: skeleton")
    report = _load(plugin_dir, "x", mismatched)
    assert any("availability 必须也是 skeleton" in error for error in report.errors)

    back = VALID.format(name="y").replace("availability: ready", "availability: skeleton")
    report = _load(plugin_dir, "y", back)
    assert any("status 应写 skeleton" in error for error in report.errors)


def test_drape_without_a_picker_is_rejected(plugin_dir):
    """声明能铺到地球上，就得说得出界面该问什么。"""
    body = VALID.format(name="x").replace("picker: template", "picker: null")
    report = _load(plugin_dir, "x", body)
    assert any("请声明 picker" in error for error in report.errors)


def test_drape_false_needs_no_picker(plugin_dir):
    body = (
        VALID.format(name="x")
        .replace("drape: true", "drape: false")
        .replace("picker: template", "picker: null")
    )
    report = _load(plugin_dir, "x", body)
    assert [item.manifest["id"] for item in report.loaded] == ["x"]


def test_allowed_value_sets_are_what_the_contract_documents():
    assert MODES == {"reference", "ingest"}
    assert STATUSES == {"implemented", "skeleton"}
    assert AVAILABILITIES == {"ready", "needs_config", "skeleton"}
    assert PICKERS == {None, "template", "extent", "time"}
    assert {"availability", "drape", "picker"} <= set(REQUIRED_FIELDS)


# --- 仓库里自带的插件必须全部合规 ---


def test_every_shipped_plugin_declares_the_contract_fields():
    report = load_plugins(ROOT / "plugins")
    assert report.errors == [], f"仓库自带插件有不合规的：{report.errors}"
    for item in report.loaded:
        manifest = item.manifest
        assert manifest["drape"] is True or manifest["picker"] is None
        if manifest["drape"]:
            assert manifest["picker"] in {"template", "extent", "time"}


def test_shipped_plugins_keep_their_declared_availability():
    """前端弹层完全建立在这三项上，声明与实际能力不符就是界面在说谎。"""
    by_id = {item.manifest["id"]: item.manifest for item in load_plugins(ROOT / "plugins").loaded}
    for pid in ("public_stac", "gibs", "arcgis_wayback", "custom_xyz"):
        assert by_id[pid]["availability"] == "ready", pid
        assert by_id[pid]["drape"] is True, pid
    for pid in ("google_tiles", "tianditu", "tencent_map"):
        assert by_id[pid]["availability"] == "needs_config", pid
    for pid in ("jilin1", "beijing1", "shiji", "siwei", "gee"):
        assert by_id[pid]["availability"] == "skeleton", pid
        assert by_id[pid]["status"] == "skeleton", pid


def test_no_plugin_claims_implemented_while_refusing_to_search():
    """status 写 implemented 却在 search 里抛 NotImplementedError，就是界面在说谎。

    gee 原先就是这样：manifest 写 implemented，配了账号 `search()` 也抛错，
    于是它在弹层里看起来可用，点进去才发现不行。
    """
    report = load_plugins(ROOT / "plugins")
    for item in report.loaded:
        if item.manifest["status"] != "implemented":
            continue
        provider = item.provider
        declared = getattr(provider, "availability", item.manifest["availability"])
        if declared != "ready":
            continue
        try:
            provider.search(None, None, {"fetch": True})
        except NotImplementedError as exc:
            pytest.fail(
                f"{item.manifest['id']} 声明为可用的已实现源，search 却抛 NotImplementedError：{exc}"
            )
        except (ValueError, OSError, TimeoutError):
            # 参数校验失败、或真的去请求外部服务时网络不通，都属于正常路径：
            # 它们说明代码走到了实际检索逻辑，而不是拒绝提供这个源。
            pass


def test_sample_plugins_load_without_catalog_edits():
    report = load_plugins(ROOT / "plugins")
    ids = {item.manifest["id"] for item in report.loaded}
    assert {"sample_reference", "sample_ingest"} <= ids
    catalog_text = "\n".join(
        path.read_text(encoding="utf-8") for path in (ROOT / "app" / "catalog").glob("*.py")
    )
    assert "sample_reference" not in catalog_text


# --- needs_config 的源拿到凭据后应当变成 ready ---

CREDENTIAL_STUB = (
    "class Stub:\n"
    "    id = 'stub'\n"
    "    capabilities = set()\n"
    "    availability = 'needs_config'\n"
    "    def authenticate(self, config):\n"
    "        key = (config.get('secrets') or {}).get('api_key')\n"
    "        self.availability = 'ready' if key else 'needs_config'\n"
    "    def search(self, bbox, datetime_range, filters):\n"
    "        return []\n"
    "    def get_layer_spec(self, item_id):\n"
    "        raise NotImplementedError\n"
    "    def ingest(self, item_id):\n"
    "        raise NotImplementedError\n"
)

NEEDS_KEY = VALID.replace("availability: ready", "availability: needs_config").replace(
    "credentials: []", "credentials: [api_key]"
)


def _write_credentialed(directory: Path, name: str) -> Path:
    plugin = _write_plugin(directory, name, NEEDS_KEY.format(name=name))
    (plugin / "provider.py").write_text(CREDENTIAL_STUB, encoding="utf-8")
    return plugin


def test_credentialed_plugin_without_a_key_is_needs_config(plugin_dir, build_app):
    _write_credentialed(plugin_dir, "needskey")
    client = TestClient(build_app(plugins_dir=plugin_dir))
    row = next(r for r in client.get("/providers").json() if r["id"] == "needskey")
    assert row["availability"] == "needs_config"
    # 没 Key 的源不进弹层（宪章 C4：没 Key 不请求）
    assert row["drape"] is False
    assert row["picker"] is None


def test_availability_reflects_the_provider_after_authentication(plugin_dir):
    """manifest 声明的是基线，真正的可用性只有 provider 认证后才知道。

    所以两者不一致时以 provider 为准——否则声明 needs_config 的源拿到 Key 后
    永远不会出现在界面上。
    """
    _write_credentialed(plugin_dir, "needskey")

    report = load_plugins(plugin_dir)
    loaded = report.loaded[0]
    assert loaded.manifest["availability"] == "needs_config", "manifest 基线应保持原样"
    assert loaded.provider.availability == "needs_config", "没给 Key 时应是 needs_config"

    loaded.provider.authenticate({"secrets": {"api_key": "demo"}})
    assert loaded.provider.availability == "ready", "给了 Key 之后 provider 应改口"

    recorded = json.loads(_config_json(loaded))
    assert recorded["availability"] == "ready"
    assert recorded["credentials"] == ["api_key"]