"""Add idempotent territorial deadline notification markers.

Revision ID: e1a4c6d8f0b2
Revises: d9f1a3c5e7b2
"""

import sqlalchemy as sa
from alembic import op

revision = "e1a4c6d8f0b2"
down_revision = "d9f1a3c5e7b2"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "territorial_actions",
        sa.Column("due_soon_notified_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "territorial_actions",
        sa.Column("overdue_notified_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_territorial_actions_open_due",
        "territorial_actions",
        ["tenant_id", "status", "due_at"],
    )


def downgrade():
    op.drop_index("ix_territorial_actions_open_due", table_name="territorial_actions")
    op.drop_column("territorial_actions", "overdue_notified_at")
    op.drop_column("territorial_actions", "due_soon_notified_at")
