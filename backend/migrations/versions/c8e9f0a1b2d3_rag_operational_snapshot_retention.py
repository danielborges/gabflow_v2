"""Add retention compaction marker to operational RAG snapshots.

Revision ID: c8e9f0a1b2d3
Revises: b7d8e9f0a1c2
"""

import sqlalchemy as sa
from alembic import op

revision = "c8e9f0a1b2d3"
down_revision = "b7d8e9f0a1c2"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("rag_document_versions") as batch:
        batch.add_column(sa.Column("retention_purged_at", sa.DateTime(timezone=True)))
        batch.create_index(
            "ix_rag_document_versions_retention_purged_at",
            ["retention_purged_at"],
        )


def downgrade():
    with op.batch_alter_table("rag_document_versions") as batch:
        batch.drop_index("ix_rag_document_versions_retention_purged_at")
        batch.drop_column("retention_purged_at")
