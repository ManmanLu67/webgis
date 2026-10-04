"""契约（OpenAPI yaml）与实现不许漂移。

背景：契约里原本只记了 6 个端点、6 个 Layer 字段，而实现早已是 11 个端点、
21 个字段。文档不会自己追上来，所以这里让它追。

## 为什么只做单向（docs ⊆ code）

"code ⊆ docs" 那一半靠 `app.openapi()` 取路径并不可靠：

1. FastAPI 0.141 起 `include_router` 不再把子路由摊平进 `app.routes`，而是放一个
   私有结构进去，只看第一层会漏掉全部业务路由（`test_gateway_routes.py` 里已实测）。
2. `openapi()` 受 `include_in_schema` 影响，且不覆盖 FastAPI 自带的 `/docs`、
   `/openapi.json`。
3. `/cog` 下有 13 条路由由 TiTiler 贡献，形状随它自己的版本走。

反向检查真正想抓的是"代码加了接口但忘了写文档"。这件事用下面那份显式清单来守
更直接、更少误报——清单里没有的东西就不是平台承诺的接口，加了端点忘了写契约时
它会失败。

## 为什么 `/cog` 不进这两项检查

1. `/cog` 的 13 条路由里我们只承诺 7 条。**承诺与不承诺的差别不在路径是否存在于
   代码里，而在平台是否愿意为它背书。** 契约不是第三方 API 的镜像。
2. 反向检查若要成立，就得把 13 条逐条抄进去，契约会跟着 TiTiler 升级漂移，
   而我们对那次升级没有话语权。
3. 这 7 条的真实可用性**已经**由 `tests/test_tile_service.py` 用真实请求守着
   （19 项，命中真实路由、真实 WMTS 文档、真实 403/404 行为）。
   契约的职责是"我们说了什么"，那份测试的职责是"它真的能用"，两者互补，
   不必再叠一层路径 diff。
"""

import re
import tempfile
from pathlib import Path

import pytest
import yaml
from app.api.routes import _layer_payload
from app.ingest import worker
from app.plugins.loader import AVAILABILITIES, PICKERS, TIME_CHOICES
from app.providers.protocol import LayerSpec

ROOT = Path(__file__).resolve().parents[2]
CONTRACTS = ROOT / "specs"

CATALOG = CONTRACTS / "001-catalog-provider" / "contracts" / "catalog.openapi.yaml"
JOBS = CONTRACTS / "002-ingest-publish" / "contracts" / "jobs.openapi.yaml"
TILES = CONTRACTS / "002-ingest-publish" / "contracts" / "tiles.openapi.yaml"
ANNOTATIONS = CONTRACTS / "005-map-tools" / "contracts" / "annotations.openapi.yaml"

# 平台自己的契约：路径即端点，不带网关前缀。
PLATFORM_CONTRACTS = (CATALOG, JOBS, ANNOTATIONS)

# 平台对外承诺的端点全在这儿。加了新端点却忘了写契约，这里会失败。
# 刻意写成字面量而不是从代码里推导——推导出来的话就等于没有守卫了。
CORE_ROUTES = {
    "/providers",
    "/providers/errors",
    "/providers/{provider_id}/search",
    "/items",
    "/items/{item_id}/layer",
    "/jobs",
    "/jobs/uploads",
    "/jobs/{job_id}",
    "/tiles/timing",
    "/annotations",
    "/annotations/{annotation_id}",
}

# `/cog` 下面由平台承诺的那几条。列在这里是为了让"我们承诺了什么"有明确答案，
# 而不是"契约里碰巧写了什么"。可用性由 test_tile_service.py 保证。
PROMISED_TILE_ROUTES = {
    "/tiles/{tileMatrixSetId}/{z}/{x}/{y}",
    "/tiles/{tileMatrixSetId}/{z}/{x}/{y}.{format}",
    "/WMTSCapabilities.xml",
    "/preview",
    "/info",
    "/info.geojson",
    "/{tileMatrixSetId}/tilejson.json",
}

FALLBACK_LAYER = LayerSpec(
    id="x", type="xyz", url="u", style={}, time_dimension=None, publisher_id="p"
)


def load(path: Path) -> dict:
    assert path.is_file(), f"契约不存在：{path}"
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def app_paths() -> set[str]:
    """应用真实注册的路径（含 `/cog`）。"""
    pytest.importorskip("titiler.core", reason="需要切片服务才能看到 /cog 路由")
    from app.config import Settings
    from app.main import create_app

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        root = Path(tmp)
        plugins = root / "plugins"
        plugins.mkdir()
        from conftest import migrate

        migrate(f"sqlite:///{root / 'catalog.db'}")
        app = create_app(
            Settings(
                database_url=f"sqlite:///{root / 'catalog.db'}",
                plugins_dir=plugins,
                data_dir=root / "data",
            )
        )
        paths = set(app.openapi()["paths"])
        paths |= {r.path for r in app.router.routes if getattr(r, "path", None)}
        app.state.engine.dispose()
    return paths


def templated(path: str) -> str:
    """`{provider_id}` 与 FastAPI 花括号参数同名，这里统一成正则去比对。"""
    return re.sub(r"\{[^}]+\}", "{}", path)


# --- 字段集合 ---


def test_layer_schema_matches_the_serializer():
    """yaml 的 Layer 字段必须与 `_layer_payload` 的出参逐字对应。

    这条是最容易漂的一处：加字段只改 Python 是顺手的事，忘了改 yaml 就没人发现。
    """
    schema = load(CATALOG)["components"]["schemas"]["Layer"]
    assert set(schema["properties"]) == set(_layer_payload(FALLBACK_LAYER))


def test_layer_required_fields_are_actually_present():
    schema = load(CATALOG)["components"]["schemas"]["Layer"]
    produced = set(_layer_payload(FALLBACK_LAYER))
    for name in schema["required"]:
        assert name in produced, f"required 里的 {name} 不在出参中"


# --- 路径：docs ⊆ code ---


def test_every_documented_platform_path_exists():
    """契约里写了却不存在于代码的路径，会让客户端按一份假契约集成。"""
    live = {templated(path) for path in app_paths()}
    missing = []
    for contract in PLATFORM_CONTRACTS:
        for path in load(contract)["paths"]:
            if templated(path) not in live:
                missing.append(f"{contract.name}: {path}")
    assert missing == [], f"契约记录了不存在的端点：{'；'.join(missing)}"


def test_promised_tile_paths_exist_but_are_not_path_diffed():
    """/cog 只核对"承诺的那几条确实存在"，不做全量双向比对。理由见模块文档。"""
    live = {templated(path) for path in app_paths() if path.startswith("/cog")}
    missing = [
        f"/cog{path}"
        for path in PROMISED_TILE_ROUTES
        if templated(f"/cog{path}") not in live
    ]
    assert missing == [], f"承诺了但不存在的切片端点：{'；'.join(missing)}"


def test_tile_contract_documents_exactly_what_we_promise():
    """契约里只写承诺的那几条——多写就是把第三方 API 抄成镜像。"""
    assert set(load(TILES)["paths"]) == PROMISED_TILE_ROUTES


# --- 路径：代码 ⊆ docs（用显式清单守） ---


def test_core_routes_are_all_documented():
    documented: set[str] = set()
    for contract in (*PLATFORM_CONTRACTS, TILES):
        documented |= {templated(path) for path in load(contract)["paths"]}
    undocumented = sorted(
        path for path in CORE_ROUTES if templated(path) not in documented
    )
    assert undocumented == [], f"平台端点未写进契约：{'、'.join(undocumented)}"


def test_core_route_list_is_not_outdated():
    """清单也不能腐化：文档里记的端点必须都还真实存在。"""
    live = {templated(path) for path in app_paths()}
    gone = sorted(path for path in CORE_ROUTES if templated(path) not in live)
    assert gone == [], f"清单里的端点已不存在，请更新 CORE_ROUTES：{'、'.join(gone)}"


def test_app_paths_are_not_vacuous():
    """上面那些断言全靠 `app_paths()`，它自己得先自证不是空的。

    这里用 `app.openapi()`（FastAPI 0.141 起只有它会算好 include 前缀）而不是
    `app.routes` —— 后者里是私有 `_IncludedRouter`，子路由存在
    `original_router.routes` 下，直接翻第一层只能看到 FastAPI 自带的四条。
    """
    paths = app_paths()
    assert "/providers" in paths
    assert "/items/{item_id}/layer" in paths
    assert any(path.startswith("/cog/tiles/") for path in paths)


# --- 枚举一致 ---


def test_provider_availability_enum_matches_the_loader():
    schema = load(CATALOG)["components"]["schemas"]["Provider"]["properties"]
    assert set(schema["availability"]["enum"]) == AVAILABILITIES


def test_provider_picker_enum_matches_the_loader():
    schema = load(CATALOG)["components"]["schemas"]["Provider"]["properties"]
    # PICKERS 含 None，契约里用 nullable 表达而不是把 null 塞进 enum
    assert set(schema["picker"]["enum"]) == {value for value in PICKERS if value}
    assert schema["picker"]["nullable"] is True


def test_provider_time_choices_enum_matches_the_loader():
    schema = load(CATALOG)["components"]["schemas"]["Provider"]["properties"]
    assert set(schema["time_choices"]["enum"]) == TIME_CHOICES
    assert schema["time_choices"]["nullable"] is True


def test_job_status_enum_matches_the_worker_states():
    schema = load(JOBS)["components"]["schemas"]["Job"]["properties"]
    live = {worker.QUEUED, worker.RUNNING, worker.SUCCESS, worker.FAILED, worker.CANCELLED}
    assert set(schema["status"]["enum"]) == live


def test_tile_timing_cache_enum_excludes_hit():
    """`hit` 必须不在枚举里——命中要实测，不许由配置推断。"""
    schema = load(JOBS)["components"]["schemas"]["TileTiming"]["properties"]
    assert set(schema["cache"]["enum"]) == {"none", "unverified"}
    assert "hit" not in schema["cache"]["enum"]


def test_tile_timing_duration_is_nullable():
    """没采样时返回 null，不是一个编造的 0。"""
    schema = load(JOBS)["components"]["schemas"]["TileTiming"]["properties"]
    assert schema["duration_ms"]["nullable"] is True
    assert "duration_ms" in load(JOBS)["components"]["schemas"]["TileTiming"]["required"]


# --- 契约文件本身的规矩 ---


def test_every_contract_declares_openapi_and_schemas():
    for contract in (*PLATFORM_CONTRACTS, TILES):
        doc = load(contract)
        assert doc["openapi"].startswith("3."), contract
        assert doc["info"]["title"], contract
        assert doc["paths"], contract


def test_jobs_upload_documents_the_413():
    """超限上传返回 413，契约里必须有，否则客户端只会当成网络错误。"""
    responses = load(JOBS)["paths"]["/jobs/uploads"]["post"]["responses"]
    assert "413" in responses
