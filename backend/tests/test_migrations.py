"""Alembic 是表结构的唯一来源。

以前 `app/main.py` 在启动时直接 `Base.metadata.create_all()`，那玩意儿只补缺失的
表，不会改已有表——列改了它装作没看见。于是"迁移"和"运行时建表"成了两套互相不知
道的真相，schema 漂移要等到某条查询报"no such column"才暴露。这里守住几条：

- 表结构只能由迁移建出来，代码里不许再有 create_all；
- ORM 声明与迁移结果必须一致（`alembic check` 无漂移）；
- 启动时发现版本落后就拒绝启动，而不是带着漂移跑。
"""

import os
import pathlib
import re
import sqlite3

import pytest
from alembic import command
from alembic.config import Config
from app.db import make_engine
from app.migrations import check_schema

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _config() -> Config:
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "alembic"))
    return config


def _columns(db_path) -> set[str]:
    with sqlite3.connect(db_path) as connection:
        return {row[1] for row in connection.execute("PRAGMA table_info(item)")}


def _indexes(db_path) -> set[str]:
    with sqlite3.connect(db_path) as connection:
        return {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type='index'")
        }


def test_alembic_ini_is_ascii():
    """Alembic 用 encoding='locale' 读 ini，Windows 中文 locale 会直接崩。"""
    raw = (ROOT / "alembic.ini").read_bytes()
    raw.decode("ascii")  # 非 ASCII 就在这里抛


def test_alembic_ini_has_no_hardcoded_url():
    """URL 必须来自 Settings，否则迁移与应用会连到两个不同的库。"""
    text = (ROOT / "alembic.ini").read_text(encoding="utf-8")
    assert not re.search(r"^\s*sqlalchemy\.url\s*=\s*\S", text, re.MULTILINE)


def test_env_reads_the_url_from_settings(monkeypatch, tmp_path):
    monkeypatch.setenv("WEBGIS_DATABASE_URL", f"sqlite:///{tmp_path / 'from-env.db'}")
    env_text = (ROOT / "alembic" / "env.py").read_text(encoding="utf-8")
    assert "Settings().database_url" in env_text


def test_no_create_all_anywhere_in_the_app():
    """运行时建表与迁移是两套互相不知情的真相，漂移要等到查询报错才暴露。"""
    offenders = [
        path.relative_to(ROOT).as_posix()
        for path in (ROOT / "app").rglob("*.py")
        if re.search(r"create_all\s*\(", path.read_text(encoding="utf-8"))
    ]
    assert offenders == []


def test_migrations_build_the_schema_the_orm_expects(monkeypatch, tmp_path):
    db_path = tmp_path / "m.db"
    url = f"sqlite:///{db_path}"
    monkeypatch.setenv("WEBGIS_DATABASE_URL", url)
    command.upgrade(_config(), "head")

    columns = _columns(db_path)
    # geometry 只在 PostgreSQL 上有真身；SQLite 上退化成 WKT 文本，但列必须在，
    # 否则 ORM 的 SELECT 会报 no such column。
    assert "geometry" in columns
    assert "minx" in columns and "maxy" in columns

    indexes = _indexes(db_path)
    assert "ix_item_acquired_at" in indexes
    assert "ix_job_status_created" in indexes


def test_orm_and_migrations_agree(monkeypatch, tmp_path):
    """`alembic check` 用 autogenerate 比对 ORM 与实际库，有漂移就非零退出。"""
    url = f"sqlite:///{tmp_path / 'agree.db'}"
    monkeypatch.setenv("WEBGIS_DATABASE_URL", url)
    command.upgrade(_config(), "head")
    command.check(_config())  # 有漂移会抛 CommandError


def test_check_schema_passes_at_head(tmp_path):
    url = f"sqlite:///{tmp_path / 'ok.db'}"
    previous = os.environ.get("WEBGIS_DATABASE_URL")
    os.environ["WEBGIS_DATABASE_URL"] = url
    try:
        command.upgrade(_config(), "head")
    finally:
        if previous is None:
            os.environ.pop("WEBGIS_DATABASE_URL", None)
        else:
            os.environ["WEBGIS_DATABASE_URL"] = previous
    engine = make_engine(url)
    try:
        assert check_schema(engine) is None
    finally:
        engine.dispose()


def test_check_schema_allows_an_empty_database(tmp_path):
    """空库不算漂移——那是还没迁移过，upgrade head 会建出来。"""
    engine = make_engine(f"sqlite:///{tmp_path / 'empty.db'}")
    try:
        assert check_schema(engine) is None
    finally:
        engine.dispose()


def test_check_schema_rejects_a_populated_database_without_version(tmp_path):
    """这就是过去 create_all 造出来的库：表在，但没有 alembic_version。"""
    db_path = tmp_path / "legacy.db"
    with sqlite3.connect(db_path) as connection:
        connection.execute("CREATE TABLE item (id TEXT PRIMARY KEY)")
    engine = make_engine(f"sqlite:///{db_path}")
    try:
        problem = check_schema(engine)
    finally:
        engine.dispose()
    assert problem is not None
    assert "alembic_version" in problem


def test_check_schema_names_the_missing_migration(tmp_path):
    url = f"sqlite:///{tmp_path / 'behind.db'}"
    previous = os.environ.get("WEBGIS_DATABASE_URL")
    os.environ["WEBGIS_DATABASE_URL"] = url
    try:
        command.upgrade(_config(), "0002")
    finally:
        if previous is None:
            os.environ.pop("WEBGIS_DATABASE_URL", None)
        else:
            os.environ["WEBGIS_DATABASE_URL"] = previous
    engine = make_engine(url)
    try:
        problem = check_schema(engine)
    finally:
        engine.dispose()
    assert problem is not None
    assert "落后于代码 head" in problem
    assert "alembic upgrade head" in problem


def test_entry_point_is_a_factory_not_a_module_level_app():
    """模块级 `app = create_app()` 会让 import 就连数据库，测试与迁移都会被绊倒。"""
    text = (ROOT / "app" / "main.py").read_text(encoding="utf-8")
    assert not re.search(r"^app\s*=\s*create_app\(\)", text, re.MULTILINE)
    assert "def build() -> FastAPI:" in text
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "app.main:build" in dockerfile
    assert "--factory" in dockerfile


@pytest.mark.parametrize("revision", ["0001", "0002", "0003", "0004"])
def test_every_revision_chains_from_the_previous_one(revision):
    """迁移链断掉的话 `upgrade head` 会只跑一半。"""
    text = (ROOT / "alembic" / "versions" / f"{revision}_*.py")
    matches = list(ROOT.glob(f"alembic/versions/{revision}_*.py"))
    assert matches, f"找不到 revision {revision}"
    assert text
    expected_previous = {"0001": None, "0002": "0001", "0003": "0002", "0004": "0003"}[revision]
    source = matches[0].read_text(encoding="utf-8")
    found = re.search(r'^down_revision\s*=\s*(.+)$', source, re.MULTILINE)
    assert found is not None
    assert found.group(1).strip().strip('"') == str(expected_previous)


def test_downgrade_returns_to_empty(tmp_path):
    """只测 upgrade 不测 downgrade，等于没测迁移。"""
    url = f"sqlite:///{tmp_path / 'down.db'}"
    previous = os.environ.get("WEBGIS_DATABASE_URL")
    os.environ["WEBGIS_DATABASE_URL"] = url
    try:
        command.upgrade(_config(), "head")
        command.downgrade(_config(), "base")
    finally:
        if previous is None:
            os.environ.pop("WEBGIS_DATABASE_URL", None)
        else:
            os.environ["WEBGIS_DATABASE_URL"] = previous
    with sqlite3.connect(tmp_path / "down.db") as connection:
        tables = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
    assert "item" not in tables
    assert "annotation" not in tables
    assert "job" not in tables