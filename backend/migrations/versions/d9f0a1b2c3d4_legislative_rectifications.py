"""legislative rectifications

Revision ID: d9f0a1b2c3d4
Revises: c8e9f0a1b2d3
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "d9f0a1b2c3d4"
down_revision = "c8e9f0a1b2d3"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "legislative_tramitations",
        sa.Column("rectifies_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "legislative_tramitations",
        sa.Column("rectification_reason", sa.String(length=500), nullable=True),
    )
    op.create_foreign_key(
        "fk_legislative_tramitations_rectifies_id",
        "legislative_tramitations",
        "legislative_tramitations",
        ["rectifies_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        "ix_legislative_tramitations_rectifies_id",
        "legislative_tramitations",
        ["rectifies_id"],
        unique=False,
    )
    op.create_unique_constraint(
        "uq_legislative_tramitations_rectifies_id",
        "legislative_tramitations",
        ["rectifies_id"],
    )


def downgrade():
    op.drop_constraint(
        "uq_legislative_tramitations_rectifies_id",
        "legislative_tramitations",
        type_="unique",
    )
    op.drop_index(
        "ix_legislative_tramitations_rectifies_id",
        table_name="legislative_tramitations",
    )
    op.drop_constraint(
        "fk_legislative_tramitations_rectifies_id",
        "legislative_tramitations",
        type_="foreignkey",
    )
    op.drop_column("legislative_tramitations", "rectification_reason")
    op.drop_column("legislative_tramitations", "rectifies_id")
