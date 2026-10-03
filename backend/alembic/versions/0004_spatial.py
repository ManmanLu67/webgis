"""spatial columns and indexes

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-28

背景：`app.spatial` 需要 `item.geometry` / `annotation.geometry` 两列，并且
时序与任务队列的检索要走索引。之前这三件事都只存在于 ORM 声明与 PostGIS 分支的
裸 SQL 里，SQLite（本机开发与测试）上根本没有对应的列，也没有一个索引。

注意 revision 0001 与 0003 已经在 PostgreSQL 上用裸 SQL 建过 `item.geometry` 与
`annotation.geometry`，所以这里只在缺列时补，不重复建。历史迁移保持原样不改。
"""

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

SPATIAL_INDEXES = (
    ("ix_item_geometry", "item", "geometry"),
    ("ix_annotation_geometry", "annotation", "geometry"),
)
PLAIN_INDEXES = (
    ("ix_item_acquired_at", "item", ["acquired_at"]),
    ("ix_job_status_created", "job", ["status", "created_at"]),
)


def _columns(bind, table: str) -> set[str]:
    inspector = sa.inspect(bind)
    if table not in inspector.get_table_names():
        return set()
    return {column["name"] for column in inspector.get_columns(table)}


def _is_postgres(bind) -> bool:
    return bind.dialect.name == "postgresql"


def upgrade() -> None:
    bind = op.get_bind()

    # SQLite 与其他非 PostgreSQL 方言没有 PostGIS，用 WKT 文本占位，
    # 与 ORM 的 with_variant 保持一致。
    if "geometry" not in _columns(bind, "item"):
        if _is_postgres(bind):
            op.execute("ALTER TABLE item ADD COLUMN geometry geometry(Polygon, 4326)")
        else:
            op.add_column("item", sa.Column("geometry", sa.Text(), nullable=True))

    if "geometry" not in _columns(bind, "annotation"):
        if _is_postgres(bind):
            op.execute("ALTER TABLE annotation ADD COLUMN geometry geometry(Geometry, 4326)")
        else:
            op.add_column("annotation", sa.Column("geometry", sa.Text(), nullable=True))

    # 已有数据回填。新插入的条目会在 app.spatial 里同步填，不依赖这一步。
    if "geometry" in _columns(bind, "item"):
        op.execute(
            "UPDATE item SET geometry = ST_MakeEnvelope(minx, miny, maxx, maxy, 4326)"
            " WHERE geometry IS NULL"
            if _is_postgres(bind)
            else "UPDATE item SET geometry = 'POLYGON((' || minx || ' ' || miny || ', '"
            " || maxx || ' ' || miny || ', ' || maxx || ' ' || maxy || ', '"
            " || minx || ' ' || maxy || ', ' || minx || ' ' || miny || '))'"
            " WHERE geometry IS NULL"
        )
    if "geometry" in _columns(bind, "annotation"):
        op.execute(
            "UPDATE annotation SET geometry = "
            "ST_SetSRID(ST_GeomFromGeoJSON(geometry_json), 4326) WHERE geometry IS NULL"
            if _is_postgres(bind)
            else "UPDATE annotation SET geometry = geometry_json WHERE geometry IS NULL"
        )

    for name, table, _ in SPATIAL_INDEXES:
        if _is_postgres(bind):
            op.execute(f"CREATE INDEX IF NOT EXISTS {name} ON {table} USING GIST (geometry)")

    for name, table, columns in PLAIN_INDEXES:
        if _columns(bind, table):
            column_list = ", ".join(columns)
            op.execute(f"CREATE INDEX IF NOT EXISTS {name} ON {table} ({column_list})")


def downgrade() -> None:
    bind = op.get_bind()
    for name, table, _ in SPATIAL_INDEXES:
        if _is_postgres(bind):
            op.execute(f"DROP INDEX IF EXISTS {name}")
    for name, table, _ in PLAIN_INDEXES:
        op.execute(f"DROP INDEX IF EXISTS {name}")
    for table in ("item", "annotation"):
        if "geometry" in _columns(bind, table):
            op.drop_column(table, "geometry")