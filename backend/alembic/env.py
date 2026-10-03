"""Alembic 环境。

URL 从 `app.config.Settings` 取，也就是走 `WEBGIS_DATABASE_URL`。
以前这里只读 `alembic.ini` 里的硬编码值，于是 `WEBGIS_DATABASE_URL` 对迁移完全无效——
迁移会打到本地 catalog.db，而应用连的是 PostGIS，两边 schema 悄悄分叉。
"""

from alembic import context
from sqlalchemy import engine_from_config, pool

from app import models  # noqa: F401
from app.config import Settings
from app.db import Base

target_metadata = Base.metadata


def database_url() -> str:
    configured = context.config.get_main_option("sqlalchemy.url", "")
    return Settings().database_url or configured


def run_migrations_offline() -> None:
    context.configure(
        url=database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    section = context.config.get_section(context.config.config_ini_section, {})
    section["sqlalchemy.url"] = database_url()
    connectable = engine_from_config(section, prefix="sqlalchemy.", poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()