"""RAG automatic query routing

Revision ID: 9d5f7b2c0e31
Revises: 8c4e6a1b9d20
Create Date: 2026-07-29 00:00:00
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "9d5f7b2c0e31"
down_revision = "8c4e6a1b9d20"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.add_column(
        "rag_assistant_queries",
        sa.Column(
            "method",
            sa.String(length=20),
            server_default="DOCUMENTAL",
            nullable=False,
        ),
    )
    op.add_column(
        "rag_assistant_queries",
        sa.Column(
            "routing_reasons",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
    )
    op.add_column(
        "rag_assistant_queries",
        sa.Column(
            "applied_filters",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
    )
    op.add_column(
        "rag_assistant_queries",
        sa.Column(
            "structured_result",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_rag_assistant_queries_method",
        "rag_assistant_queries",
        ["method"],
    )


def downgrade():
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.drop_index(
        "ix_rag_assistant_queries_method",
        table_name="rag_assistant_queries",
    )
    op.drop_column("rag_assistant_queries", "structured_result")
    op.drop_column("rag_assistant_queries", "applied_filters")
    op.drop_column("rag_assistant_queries", "routing_reasons")
    op.drop_column("rag_assistant_queries", "method")
