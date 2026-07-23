"""external agency contact metadata

Revision ID: 0d7a8b9c1e23
Revises: fc4a9e8b2d11
Create Date: 2026-07-23 11:15:00
"""

import sqlalchemy as sa
from alembic import op

revision = "0d7a8b9c1e23"
down_revision = "fc4a9e8b2d11"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("external_agencies", sa.Column("responsible", sa.String(length=160), nullable=True))
    op.add_column("external_agencies", sa.Column("phone", sa.String(length=40), nullable=True))
    op.add_column("external_agencies", sa.Column("source", sa.String(length=80), nullable=True))


def downgrade():
    op.drop_column("external_agencies", "source")
    op.drop_column("external_agencies", "phone")
    op.drop_column("external_agencies", "responsible")
