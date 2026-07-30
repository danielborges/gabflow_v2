"""Operational memory lifecycle and tombstones

Revision ID: 7b3d5f9a2c10
Revises: 6e2c4b8a1d90
Create Date: 2026-07-29 00:00:00
"""

import sqlalchemy as sa
from alembic import op

revision = "7b3d5f9a2c10"
down_revision = "6e2c4b8a1d90"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    for value in ("PENDENTE", "QUARENTENA", "ERRO", "EXCLUIDA"):
        op.execute(
            f"ALTER TYPE rag_knowledge_source_status ADD VALUE IF NOT EXISTS '{value}'"
        )

    op.add_column(
        "rag_knowledge_sources",
        sa.Column("error_code", sa.String(length=80), nullable=True),
    )
    op.add_column(
        "rag_knowledge_sources",
        sa.Column("error_message", sa.Text(), nullable=True),
    )
    op.add_column(
        "rag_knowledge_sources",
        sa.Column(
            "sync_attempts",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
    )
    op.add_column(
        "rag_knowledge_sources",
        sa.Column("quarantined_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "rag_knowledge_sources",
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "rag_knowledge_sources",
        sa.Column("purge_completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "rag_knowledge_sources",
        sa.Column("tombstone_hash", sa.String(length=64), nullable=True),
    )
    op.create_index(
        "ix_rag_knowledge_sources_tombstone_hash",
        "rag_knowledge_sources",
        ["tombstone_hash"],
    )


def downgrade():
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.drop_index(
        "ix_rag_knowledge_sources_tombstone_hash",
        table_name="rag_knowledge_sources",
    )
    for column in (
        "tombstone_hash",
        "purge_completed_at",
        "deleted_at",
        "quarantined_at",
        "sync_attempts",
        "error_message",
        "error_code",
    ):
        op.drop_column("rag_knowledge_sources", column)
