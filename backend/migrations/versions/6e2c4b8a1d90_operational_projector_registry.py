"""Operational memory projector registry provenance

Revision ID: 6e2c4b8a1d90
Revises: 5d9e1a3b7c04
Create Date: 2026-07-29 00:00:00
"""

import sqlalchemy as sa
from alembic import op

revision = "6e2c4b8a1d90"
down_revision = "5d9e1a3b7c04"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.add_column(
        "rag_knowledge_sources",
        sa.Column(
            "projector_version",
            sa.String(length=32),
            server_default="1.0.0",
            nullable=False,
        ),
    )
    op.add_column(
        "rag_knowledge_sources",
        sa.Column(
            "source_revision",
            sa.BigInteger(),
            server_default="0",
            nullable=False,
        ),
    )


def downgrade():
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.drop_column("rag_knowledge_sources", "source_revision")
    op.drop_column("rag_knowledge_sources", "projector_version")
