"""catalog tables

Revision ID: 0001
Revises:
Create Date: 2026-09-28
"""

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "provider",
        sa.Column("id", sa.String(128), primary_key=True),
        sa.Column("name", sa.String(256), nullable=False),
        sa.Column("mode", sa.String(32), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("config_json", sa.Text(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("license_note", sa.Text(), nullable=False),
        sa.Column("cache_allowed", sa.Boolean(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
    )
    op.create_table(
        "collection",
        sa.Column("id", sa.String(128), primary_key=True),
        sa.Column("provider_id", sa.String(128), sa.ForeignKey("provider.id"), nullable=False),
        sa.Column("title", sa.String(256), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
    )
    op.create_table(
        "item",
        sa.Column("id", sa.String(128), primary_key=True),
        sa.Column("collection_id", sa.String(128), sa.ForeignKey("collection.id"), nullable=False),
        sa.Column("minx", sa.Float(), nullable=False),
        sa.Column("miny", sa.Float(), nullable=False),
        sa.Column("maxx", sa.Float(), nullable=False),
        sa.Column("maxy", sa.Float(), nullable=False),
        sa.Column("acquired_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("cloud_cover", sa.Float(), nullable=True),
        sa.Column("asset_href", sa.Text(), nullable=False),
        sa.Column("access_mode", sa.String(32), nullable=False),
    )
    op.create_table(
        "layer",
        sa.Column("id", sa.String(128), primary_key=True),
        sa.Column("item_id", sa.String(128), sa.ForeignKey("item.id"), nullable=True),
        sa.Column("collection_id", sa.String(128), sa.ForeignKey("collection.id"), nullable=True),
        sa.Column("type", sa.String(32), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("style_json", sa.Text(), nullable=False),
        sa.Column("time_dimension", sa.String(64), nullable=True),
        sa.Column("publisher_id", sa.String(64), nullable=False),
    )
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("CREATE EXTENSION IF NOT EXISTS postgis")
        op.execute("ALTER TABLE item ADD COLUMN geometry geometry(Polygon, 4326)")
        op.execute(
            "UPDATE item SET geometry = ST_MakeEnvelope(minx, miny, maxx, maxy, 4326)"
        )


def downgrade() -> None:
    op.drop_table("layer")
    op.drop_table("item")
    op.drop_table("collection")
    op.drop_table("provider")
