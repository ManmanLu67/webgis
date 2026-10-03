import threading
import time

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.annotations import router as annotations_router
from app.api.routes import router
from app.catalog.sync import sync_catalog
from app.config import Settings
from app.db import make_engine, make_session_factory
from app.ingest.converter import default_converter
from app.ingest.worker import recover_interrupted, run_once
from app.models import Base
from app.plugins.loader import load_plugins
from app.publishers.registry import build_registry


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    engine = make_engine(settings.database_url)
    Base.metadata.create_all(engine)
    factory = make_session_factory(engine)
    report = load_plugins(settings.plugins_dir)
    session = factory()
    try:
        recover_interrupted(session)
        sync_catalog(session, report)
    finally:
        session.close()

    app = FastAPI(title="目录接口", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.state.settings = settings
    app.state.session_factory = factory
    app.state.load_errors = report.errors
    app.state.plugins = {item.manifest["id"]: item for item in report.loaded}
    app.state.publishers = build_registry(tile_service_prefix=settings.tile_service_prefix)
    app.state.converter = default_converter()
    app.include_router(router)
    app.include_router(annotations_router)
    _mount_tile_service(app, settings)
    if settings.worker_enabled:
        thread = threading.Thread(target=_worker_loop, args=(app,), daemon=True, name="ingest-worker")
        thread.start()
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


app = create_app()
