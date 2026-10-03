"""annotation table

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-28
"""

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "annotation",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("geometry_json", sa.Text(), nullable=False),
        sa.Column("properties_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("ALTER TABLE annotation ADD COLUMN geometry geometry(Geometry, 4326)")
        op.execute(
            "UPDATE annotation SET geometry = ST_SetSRID(ST_GeomFromGeoJSON(geometry_json), 4326)"
        )


def downgrade() -> None:
    op.drop_table("annotation")
