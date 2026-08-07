"""Add user-scoped territorial saved views.

Revision ID: b7f2d9e1a3c5
Revises: a6e1c8d0f2b4
"""

import sqlalchemy as sa
from alembic import op

revision = "b7f2d9e1a3c5"
down_revision = "a6e1c8d0f2b4"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "territorial_saved_views",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("filters", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "user_id", "name"),
    )
    op.create_index(
        "ix_territorial_saved_views_tenant_id",
        "territorial_saved_views",
        ["tenant_id"],
    )
    op.create_index(
        "ix_territorial_saved_views_user_id",
        "territorial_saved_views",
        ["user_id"],
    )


def downgrade():
    op.drop_index("ix_territorial_saved_views_user_id", table_name="territorial_saved_views")
    op.drop_index("ix_territorial_saved_views_tenant_id", table_name="territorial_saved_views")
    op.drop_table("territorial_saved_views")
