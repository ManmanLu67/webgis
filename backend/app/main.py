import threading
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.annotations import router as annotations_router
from app.api.routes import router
from app.catalog.sync import sync_catalog
from app.config import Settings
from app.db import make_engine, make_session_factory
from app.ingest.converter import default_converter
from app.ingest.worker import recover_interrupted, run_once
from app.migrations import check_schema
from app.plugins.loader import load_plugins
from app.publishers.registry import build_registry


def build() -> FastAPI:
    """进程入口：`uvicorn app.main:build --factory`。

    schema 检查放在这里而不是模块导入期：import 这个模块必须是无害的——测试要
    从中拿 `create_app`，工具要读 `check_schema`。但进程真的开始服务之前必须确认
    schema 是对的，漂移就该拒绝启动，而不是等到某条查询报"no such column"。

    入口用工厂而不是模块级 `app = create_app()`，也是同一个理由：模块级那行会让
    `import app.main` 直接连数据库，测试和迁移脚本都会被它绊倒。
    """
    settings = Settings()
    problem = check_schema(make_engine(settings.database_url))
    if problem:
        raise RuntimeError(problem)
    return create_app(settings)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    engine = make_engine(settings.database_url)
    factory = make_session_factory(engine)
    report = load_plugins(settings.plugins_dir)
    session = factory()
    try:
        recover_interrupted(session)
        sync_catalog(session, report)
    finally:
        session.close()

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        thread: threading.Thread | None = None
        if settings.worker_enabled:
            thread = threading.Thread(
                target=_worker_loop, args=(_app,), daemon=True, name="ingest-worker"
            )
            thread.start()
        yield
        if thread is not None and thread.is_alive():
            thread.join(timeout=5)
        engine.dispose()

    app = FastAPI(title="目录接口", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.state.settings = settings
    app.state.session_factory = factory
    # 挂上 engine 是为了让关停与测试能显式 dispose；SQLite 上不释放的话
    # 文件句柄会一直占着，临时目录清不掉。
    app.state.engine = engine
    app.state.load_errors = report.errors
    app.state.plugins = {item.manifest["id"]: item for item in report.loaded}
    app.state.publishers = build_registry(tile_service_prefix=settings.tile_service_prefix)
    app.state.converter = default_converter()
    app.include_router(router)
    app.include_router(annotations_router)
    _mount_tile_service(app, settings)
    return app


def _mount_tile_service(app: FastAPI, settings: Settings) -> None:
    """把 COG 动态切片挂进同一个应用。

    具体实现与挂载细节都在 `publishers` 包里，核心只负责转达挂载失败的原因。
    挂载失败不该让目录 API 一起起不来，所以只记进 `load_errors`。
    """
    from app.publishers.cog_service import mount_tile_service

    error = mount_tile_service(app, settings)
    if error:
        app.state.load_errors.append(error)


def _worker_loop(app: FastAPI) -> None:
    while True:
        session = app.state.session_factory()
        try:
            run_once(session, app.state.converter, app.state.publishers, app.state.settings)
        finally:
            session.close()
        time.sleep(1)