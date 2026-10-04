"""凭据注入：能用、不外泄、不落库。

凭据从 `WEBGIS_PROVIDER_SECRETS_<插件名大写>` 注入，格式是 JSON 对象。
`plugin.yaml` 只声明需要哪些**名字**，值不进仓库 —— 这是它唯一该出现的地方。

三条边界必须守住：
1. 值不出现在加载错误里 —— 否则一条报错就把密钥写进日志；
2. 值不落进 `provider.config_json` —— 目录是要被读、被导出、被备份的；
3. 缺凭据的源行为不变（`needs_config`、不进弹层），这是宪章 C4。
"""

import json

import pytest
from app.plugins.loader import (
    SECRETS_ENV_PREFIX,
    SecretsError,
    inject_secrets,
    load_plugins,
    read_secrets,
    secrets_env_name,
)

ROOT_ID = "tianditu"
KEY = "a-very-distinctive-demo-key"


@pytest.fixture
def env(monkeypatch):
    def setter(value, plugin_id: str = ROOT_ID):
        name = secrets_env_name(plugin_id)
        if value is None:
            monkeypatch.delenv(name, raising=False)
        else:
            monkeypatch.setenv(name, value)
    return setter


def test_env_name_is_derived_from_the_plugin_id():
    assert secrets_env_name("tianditu") == f"{SECRETS_ENV_PREFIX}TIANDITU"
    assert secrets_env_name("arcgis_wayback") == f"{SECRETS_ENV_PREFIX}ARCGIS_WAYBACK"


# --- 读取 ---


def test_absent_env_means_no_secrets():
    assert read_secrets(ROOT_ID, {}) == {}


def test_blank_env_means_no_secrets():
    assert read_secrets(ROOT_ID, {secrets_env_name(ROOT_ID): "   "}) == {}


def test_reads_a_json_object():
    env = {secrets_env_name(ROOT_ID): json.dumps({"tk": KEY})}
    assert read_secrets(ROOT_ID, env) == {"tk": KEY}


@pytest.mark.parametrize(
    ("raw", "hint"),
    [
        ("{tk: x}", "JSON"),
        ('"just-a-string"', "JSON 对象"),
        ("[1, 2]", "JSON 对象"),
        ('{"tk": 123}', "字符串"),
    ],
)
def test_malformed_values_are_rejected_with_a_readable_reason(raw, hint):
    with pytest.raises(SecretsError) as caught:
        read_secrets(ROOT_ID, {secrets_env_name(ROOT_ID): raw})
    assert hint in str(caught.value)


def test_error_message_never_echoes_the_value():
    """这是本文件最要紧的一条：报错会进 load_errors，进而进 API 响应与日志。"""
    with pytest.raises(SecretsError) as caught:
        read_secrets(ROOT_ID, {secrets_env_name(ROOT_ID): f'{{"tk": "{KEY}", "x": 1}}'})
    assert KEY not in str(caught.value)


# --- 注入 ---


def test_injection_does_not_mutate_the_manifest():
    """就地改的话，"这个插件带了凭据"会跟着 manifest 流进写进目录的 config_json。"""
    manifest = {"id": ROOT_ID, "credentials": ["tk"]}
    inject_secrets(manifest, {secrets_env_name(ROOT_ID): json.dumps({"tk": KEY})})
    assert "secrets" not in manifest


def test_injection_returns_a_new_object():
    manifest = {"id": ROOT_ID, "credentials": []}
    result = inject_secrets(manifest, {secrets_env_name(ROOT_ID): json.dumps({"a": "b"})})
    assert result is not manifest
    assert result["secrets"] == {"a": "b"}


def test_declared_credential_missing_is_rejected():
    manifest = {"id": ROOT_ID, "credentials": ["tk"]}
    with pytest.raises(SecretsError) as caught:
        inject_secrets(manifest, {secrets_env_name(ROOT_ID): json.dumps({"other": "x"})})
    assert "tk" in str(caught.value)


def test_extra_credentials_are_tolerated():
    """插件可能接受可选参数，多给一个键不该让插件加载失败。"""
    manifest = {"id": ROOT_ID, "credentials": ["tk"]}
    result = inject_secrets(
        manifest, {secrets_env_name(ROOT_ID): json.dumps({"tk": KEY, "extra": "x"})}
    )
    assert result["secrets"]["extra"] == "x"


def test_no_secrets_leaves_the_manifest_untouched():
    manifest = {"id": ROOT_ID, "credentials": ["tk"]}
    assert inject_secrets(manifest, {}) is manifest


# --- 与加载器、目录、接口的衔接 ---


def _repo_plugins():
    from pathlib import Path

    return Path(__file__).resolve().parents[1] / "plugins"


def _dump_tables(app, tables):
    import sqlite3

    db = app.state.engine.url.database
    with sqlite3.connect(str(db)) as con:
        return json.dumps(
            [con.execute(f"SELECT * FROM {name}").fetchall() for name in sorted(tables)],
            ensure_ascii=False,
            default=str,
        )


def _providers(app):
    import sqlite3

    db = app.state.engine.url.database
    with sqlite3.connect(str(db)) as con:
        con.row_factory = sqlite3.Row
        return con.execute("SELECT id, config_json FROM provider").fetchall()


def test_plugin_becomes_ready_once_the_env_var_is_set(tmp_path, env):
    """没配就 needs_config，配了就 ready —— 这条链是 C4 的兑现。"""
    assert not load_plugins(tmp_path / "plugins").loaded  # 空目录：不加载任何插件

    real = load_plugins(_repo_plugins())
    assert KEY not in "".join(real.errors)
    before = next(item for item in real.loaded if item.manifest["id"] == ROOT_ID)
    assert before.provider.availability == "needs_config"

    env(json.dumps({"tk": KEY}))
    after = load_plugins(_repo_plugins())
    assert KEY not in "".join(after.errors)
    assert not any(secrets_env_name(ROOT_ID) in e for e in after.errors)
    assert {item.manifest["id"] for item in after.loaded} == {
        item.manifest["id"] for item in real.loaded
    }  # 没有插件因为这次配置而增减
    now = next(item for item in after.loaded if item.manifest["id"] == ROOT_ID)
    assert now.provider.availability == "ready"


def test_a_broken_env_var_fails_only_that_plugin(tmp_path, env, monkeypatch):
    """一个源配错不该拖垮其他源（宪章 C1）。"""
    plugins_dir = tmp_path / "plugins"
    plugins_dir.mkdir()
    env("{not json")
    report = load_plugins(_repo_plugins())
    assert any(secrets_env_name(ROOT_ID) in error for error in report.errors)
    assert KEY not in "".join(report.errors)
    # 其他插件照常加载
    ids = {item.manifest["id"] for item in report.loaded}
    assert {"public_stac", "gibs", "custom_xyz"} <= ids


def test_secrets_never_reach_the_catalog(build_app, env):
    """目录是要被读、被导出、被备份的，凭据值不该出现在里面。"""
    env(json.dumps({"tk": KEY}))
    from fastapi.testclient import TestClient

    app = build_app(plugins_dir=_repo_plugins())
    client = TestClient(app)

    listed = client.get("/providers").json()
    assert KEY not in json.dumps(listed, ensure_ascii=False)

    body = client.post(f"/providers/{ROOT_ID}/search", json={"limit": 1, "fetch": True})
    assert body.status_code == 200
    # 检索确实用上了凭据：WMTS 参数齐了
    layer = body.json()["items"][0]["layer"]
    assert layer["wmts_layer"] == "img"
    assert layer["wmts_tile_matrix_set_id"] == "w"
    assert layer["wmts_format"] == "tiles"
    assert layer["wmts_dimensions"] == {"tk": KEY}

    # 但目录表里只有凭据的名字
    import sqlite3

    db = app.state.engine.url.database
    with sqlite3.connect(str(db)) as con:
        rows = [config for (config,) in con.execute("SELECT config_json FROM provider")]
    assert rows
    assert KEY not in "".join(rows)
    # tianditu 的记录里应当出现凭据**名字** tk —— 说明记的是"需要什么"而不是"是什么"
    records = {row["id"]: json.loads(row["config_json"]) for row in _providers(app)}
    assert records[ROOT_ID]["credentials"] == ["tk"]


def test_credentials_are_not_persisted_columns(build_app, env):
    """wmts_dimensions 不是持久化列，所以凭据没机会随图层落库。

    这条比"跑一次入库再查库"更靠得住：不依赖网络，也不依赖入库流程是否改动。
    """
    env(json.dumps({"tk": KEY}))
    from app.models import Layer
    from sqlalchemy import inspect

    persisted = {column.name for column in inspect(Layer).columns}
    assert "wmts_dimensions" not in persisted
    assert persisted == {
        "id", "item_id", "collection_id", "type",
        "url", "style_json", "time_dimension", "publisher_id",
    }

    app = build_app(plugins_dir=_repo_plugins())
    from fastapi.testclient import TestClient

    assert KEY not in TestClient(app).get("/providers").text
    assert KEY not in _dump_tables(app, {"provider"})
