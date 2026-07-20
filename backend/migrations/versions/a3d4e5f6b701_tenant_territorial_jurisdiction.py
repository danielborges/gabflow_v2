"""tenant territorial jurisdiction

Revision ID: a3d4e5f6b701
Revises: f5b7c8d9e102
Create Date: 2026-07-20 16:15:00
"""

import sqlalchemy as sa
from alembic import op

revision = "a3d4e5f6b701"
down_revision = "f5b7c8d9e102"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("tenants", sa.Column("chamber_type", sa.String(length=40), nullable=True))
    op.add_column("tenants", sa.Column("jurisdiction_name", sa.String(length=160), nullable=True))
    op.add_column("tenants", sa.Column("jurisdiction_city", sa.String(length=120), nullable=True))
    op.add_column("tenants", sa.Column("jurisdiction_state", sa.String(length=2), nullable=True))
    op.add_column("tenants", sa.Column("jurisdiction_center_latitude", sa.Float(), nullable=True))
    op.add_column("tenants", sa.Column("jurisdiction_center_longitude", sa.Float(), nullable=True))
    op.add_column("tenants", sa.Column("jurisdiction_bounds", sa.JSON(), nullable=True))


def downgrade():
    op.drop_column("tenants", "jurisdiction_bounds")
    op.drop_column("tenants", "jurisdiction_center_longitude")
    op.drop_column("tenants", "jurisdiction_center_latitude")
    op.drop_column("tenants", "jurisdiction_state")
    op.drop_column("tenants", "jurisdiction_city")
    op.drop_column("tenants", "jurisdiction_name")
    op.drop_column("tenants", "chamber_type")
