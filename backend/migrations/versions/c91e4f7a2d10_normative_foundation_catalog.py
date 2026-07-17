"""normative foundation catalog

Revision ID: c91e4f7a2d10
Revises: b72e1a4d6f03
Create Date: 2026-07-17 12:30:00
"""

import sqlalchemy as sa
from alembic import op

revision = "c91e4f7a2d10"
down_revision = "b72e1a4d6f03"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "normative_sources",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("source_type", sa.String(length=50), nullable=False),
        sa.Column("title", sa.String(length=240), nullable=False),
        sa.Column("reference", sa.String(length=240), nullable=False),
        sa.Column("excerpt", sa.Text(), nullable=False),
        sa.Column("jurisdiction", sa.String(length=120), nullable=True),
        sa.Column("source_url", sa.String(length=1000), nullable=True),
        sa.Column("version", sa.String(length=80), nullable=False),
        sa.Column("checksum", sa.String(length=64), nullable=False),
        sa.Column("valid_from", sa.Date(), nullable=True),
        sa.Column("valid_until", sa.Date(), nullable=True),
        sa.Column("rag_collection", sa.String(length=80), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("created_by_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "title", "reference", "version"),
    )
    for column in (
        "tenant_id",
        "source_type",
        "rag_collection",
        "active",
        "created_at",
    ):
        op.create_index(
            f"ix_normative_sources_{column}", "normative_sources", [column]
        )


def downgrade():
    op.drop_table("normative_sources")
