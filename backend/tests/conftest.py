"""测试共用的建库方式。

schema 只有 Alembic 这一条路（`app/main.py` 里不再有 `create_all`），所以测试
也必须走迁移——这样测试顺带就在验证迁移本身，而不是绕过它。好处是迁移写坏时
测试立刻红，而不是等到部署才炸。
"""

import os
from collections.abc import Callable
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from app.config import Settings
from app.main import create_app

ROOT = Path(__file__).resolve().parents[1]


def migrate(database_url: str) -> None:
    """把目标库迁到 head。"""
    previous = os.environ.get("WEBGIS_DATABASE_URL")
    os.environ["WEBGIS_DATABASE_URL"] = database_url
    try:
        config = Config(str(ROOT / "alembic.ini"))
        config.set_main_option("script_location", str(ROOT / "alembic"))
        command.upgrade(config, "head")
    finally:
        if previous is None:
            os.environ.pop("WEBGIS_DATABASE_URL", None)
        else:
            os.environ["WEBGIS_DATABASE_URL"] = previous


@pytest.fixture
def build_app(tmp_path: Path, request: pytest.FixtureRequest) -> Callable[..., object]:
    """建一个已经迁移到 head 的应用。

    插件目录默认给一个空目录：多数测试只想验目录 API 或切片，不想被真实插件的
    检索结果干扰。需要真实插件的测试传 `plugins_dir=ROOT / "plugins"`。
    `data_dir` 固定为 `tmp_path / "data"`，所以测试往那儿放 COG 就能被切片读到。

    同一用例里要建第二个应用时传不同的 `db_name`，否则两次建到同一个库上，
    数据会互相污染（而这种污染往往表现为"测试莫名其妙通过"）。

    engine 由 pytest 在用例结束后 dispose——SQLite 上文件句柄不释放的话，
    临时目录清不掉（Windows 上会直接报 PermissionError）。
    """

    def factory(*, plugins_dir: Path | None = None, db_name: str = "catalog", **overrides):
        if plugins_dir is None:
            plugins_dir = tmp_path / "plugins"
            plugins_dir.mkdir(exist_ok=True)
        database_url = f"sqlite:///{tmp_path / f'{db_name}.db'}"
        migrate(database_url)
        app = create_app(
            Settings(
                database_url=database_url,
                plugins_dir=plugins_dir,
                data_dir=tmp_path / "data",
                **overrides,
            )
        )
        request.addfinalizer(app.state.engine.dispose)
        return app

    return factory