"""RAG production observability and scale

Revision ID: 5d9e1a3b7c04
Revises: 4c8d0f2a6b93
Create Date: 2026-07-25 00:00:00
"""

import sqlalchemy as sa
from alembic import op

revision = "5d9e1a3b7c04"
down_revision = "4c8d0f2a6b93"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.add_column(
        "rag_assistant_queries",
        sa.Column("latency_ms", sa.Integer(), nullable=True),
    )
    op.add_column(
        "outbox_events",
        sa.Column("processing_duration_ms", sa.Integer(), nullable=True),
    )
    op.create_index(
        "ix_outbox_events_claim_ready",
        "outbox_events",
        ["available_at", "occurred_at"],
        postgresql_where=sa.text("published_at IS NULL AND failed_at IS NULL"),
    )
    op.create_index(
        "ix_outbox_events_event_claim_ready",
        "outbox_events",
        ["event_type", "available_at", "occurred_at"],
        postgresql_where=sa.text("published_at IS NULL AND failed_at IS NULL"),
    )


def downgrade():
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.drop_index("ix_outbox_events_event_claim_ready", table_name="outbox_events")
    op.drop_index("ix_outbox_events_claim_ready", table_name="outbox_events")
    op.drop_column("outbox_events", "processing_duration_ms")
    op.drop_column("rag_assistant_queries", "latency_ms")
