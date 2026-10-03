"""网关路由与后端路由的一致性。

`docker compose up` 的正确性完全取决于一件事：网关 Caddyfile 里反代的每条路径，
后端都得真的有。改了一边忘了另一边，表现为容器里一片 404 —— 本机 `pnpm dev`
完全正常，所以很容易漏过去。这里把两边对着读，不一致就失败。
"""

import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
CADDYFILE = ROOT / "gateway" / "Caddyfile"
COMPOSE = ROOT / "docker-compose.yml"

HANDLE = re.compile(r"handle\s+(/\S*)\s*\{")
STRIP = re.compile(r"uri\s+strip_prefix\s+(\S+)")


def app_routes() -> set[str]:
    """起一个真实应用，把它实际对外暴露的路径抓出来。

    FastAPI 0.141 起 `include_router` 不再把子路由摊平进 `app.routes`，而是塞一个
    私有结构进去，只看第一层会漏掉全部业务路由。所以路径从公开的 `openapi()`
    取（它已经算好了 include 前缀），再补上 FastAPI 自带的文档路由。
    """
    pytest.importorskip("titiler.core", reason="需要切片服务才能看到 /cog 路由")
    from app.config import Settings
    from app.main import create_app

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        plugins = Path(tmp) / "plugins"
        plugins.mkdir()
        app = create_app(
            Settings(
                database_url=f"sqlite:///{Path(tmp) / 'c.db'}",
                plugins_dir=plugins,
                data_dir=Path(tmp) / "data",
            )
        )
        routes = set(app.openapi()["paths"])
        routes |= {
            route.path for route in app.router.routes if getattr(route, "path", None)
        }
        app.state.engine.dispose()
    return routes


def test_route_introspection_sees_the_nested_routers():
    """内省本身要先自证：漏看嵌套路由的话下面所有断言都会假通过。"""
    routes = app_routes()
    assert "/providers" in routes, "目录 API 路由没被收集到"
    assert any(route.startswith("/cog/tiles/") for route in routes), "切片路由没被收集到"
    assert "/items/{item_id}/layer" in routes


def normalise(path: str) -> str:
    """把两边的通配统一成同一种写法：后端 `{z}` 与 Caddy `*` 都算通配。"""
    trimmed = re.sub(r"\{[^}]+\}", "*", path)
    return "/" + trimmed.strip("*").strip("/") if trimmed.strip("*/") else "/"


def proxied_blocks() -> dict[str, str]:
    """取出每个真正反代到 api 的 handle 块。"""
    text = CADDYFILE.read_text(encoding="utf-8")
    blocks: dict[str, str] = {}
    for match in HANDLE.finditer(text):
        body = text[match.end() :].split("}")[0]
        if "reverse_proxy api:8000" in body:
            blocks[match.group(1)] = body
    return blocks


def test_caddyfile_exists_and_declares_a_site_block():
    assert CADDYFILE.is_file(), "网关入口不存在，compose 里的 gateway 服务会构建失败"
    text = CADDYFILE.read_text(encoding="utf-8")
    assert "reverse_proxy api:8000" in text
    assert re.search(r"handle\s*\{", text), "必须有兜底的静态文件处理块，否则前端路由刷不出来"


def test_every_proxied_path_exists_on_the_backend():
    """网关反代的每条路径，后端都得真的有对应的东西。

    通配块（`/api/*`、`/cog/*`）看的是剥掉前缀之后底下还有没有子路径；
    精确块（`/openapi.json`）看的是逐字相等。
    """
    blocks = proxied_blocks()
    assert blocks, "Caddyfile 里没有任何反代到 api 的块"
    served = {normalise(route) for route in app_routes()}
    missing: list[str] = []
    for path, body in blocks.items():
        stripped = STRIP.search(body)
        effective = normalise(path[len(stripped.group(1)) :] if stripped else path)
        if path.endswith("*"):
            prefix = effective.rstrip("/")
            if not any(route == prefix or route.startswith(f"{prefix}/") for route in served):
                missing.append(f"{path} → {prefix}（后端无此子树）")
        elif effective not in served:
            missing.append(f"{path} → {effective}（后端无此路径）")
    assert missing == [], "网关转发了后端没有的路径：" + "；".join(missing)


def test_tile_service_prefix_is_not_stripped():
    """`/cog` 不能被 strip 掉前缀，否则瓦片地址会指向不存在的路由。"""
    blocks = proxied_blocks()
    assert "/cog/*" in blocks, "切片路由必须显式反代，否则入库图层拉不到瓦片"
    assert "strip_prefix" not in blocks["/cog/*"]


def test_default_path_is_three_containers():
    """宪章 C7：默认路径只允许 postgis、api 与入口，不能多出第四个。"""
    doc = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))
    # migrate 是一次性任务，跑完即退出，不构成常驻容器。
    assert set(doc["services"]) - {"migrate"} == {"postgis", "api", "gateway"}
    assert doc["services"]["gateway"]["ports"] == ["8080:8080"]


def test_api_waits_for_migrations():
    """schema 没建好就起 api，只会在第一条查询上炸。"""
    doc = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))
    assert doc["services"]["api"]["depends_on"]["migrate"]["condition"] == (
        "service_completed_successfully"
    )
    assert doc["services"]["migrate"]["command"] == ["alembic", "upgrade", "head"]


def test_api_and_migrate_share_one_environment_block():
    """两处各写一遍环境变量，迟早会漂。"""
    doc = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))
    api = doc["services"]["api"]["environment"]
    migrate = doc["services"]["migrate"]["environment"]
    assert api["WEBGIS_DATABASE_URL"] == migrate["WEBGIS_DATABASE_URL"]
    assert api["WEBGIS_DATA_DIR"] == migrate["WEBGIS_DATA_DIR"] == "/app/data"
    assert api["WEBGIS_WORKER_ENABLED"] == "true", "入库 worker 必须开，否则上传的任务永远排队"


def test_cog_files_are_shared_with_the_api_container():
    """COG 写在 api 容器的 volume 里，切片端点也在同一容器，才读得到。"""
    doc = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))
    assert "./api-data" not in doc["services"]["api"].get("volumes", [])
    assert any(
        volume.startswith("api-data:") for volume in doc["services"]["api"].get("volumes", [])
    )


def test_gateway_serves_the_frontend_build():
    """静态产物必须由网关自己发，否则默认路径又多一个容器。"""
    dockerfile = (ROOT / "gateway" / "Dockerfile").read_text(encoding="utf-8")
    assert "pnpm build" in dockerfile
    assert "/srv/web" in dockerfile
    assert not (ROOT / "frontend" / "Dockerfile").exists(), (
        "frontend/Dockerfile 已由 gateway/Dockerfile 取代，留着会让人以为有两条构建路径"
    )


def test_dev_proxy_covers_the_tile_service():
    """开发期也要能拉到瓦片，否则入库图层在 pnpm dev 下是坏的。"""
    vite = (ROOT / "frontend" / "vite.config.ts").read_text(encoding="utf-8")
    assert '"/api"' in vite
    assert '"/cog"' in vite
    assert "changeOrigin" in vite


def test_smoke_script_exists_and_checks_the_upload_path():
    """冒烟脚本必须真的跑一遍上传入库主链路，不能只探几个静态路径。"""
    script = (ROOT / "scripts" / "smoke.py").read_text(encoding="utf-8")
    assert "/api/jobs/uploads" in script
    assert "/api/jobs/" in script
    assert "/api/items/" in script and "/layer" in script
    assert "/api/tiles/timing" in script


@pytest.mark.skipif(shutil.which("caddy") is None, reason="本机没有 caddy 可校验配置语法")
def test_caddyfile_is_valid():
    result = subprocess.run(
        ["caddy", "validate", "--config", str(CADDYFILE), "--adapter", "caddyfile"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr