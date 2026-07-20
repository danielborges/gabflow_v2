"""tenant jurisdiction geojson

Revision ID: b4c5d6e7f802
Revises: a3d4e5f6b701
Create Date: 2026-07-20 16:55:00
"""

import sqlalchemy as sa
from alembic import op

revision = "b4c5d6e7f802"
down_revision = "a3d4e5f6b701"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("tenants", sa.Column("jurisdiction_ibge_code", sa.String(length=20), nullable=True))
    op.add_column("tenants", sa.Column("jurisdiction_geojson", sa.JSON(), nullable=True))


def downgrade():
    op.drop_column("tenants", "jurisdiction_geojson")
    op.drop_column("tenants", "jurisdiction_ibge_code")
