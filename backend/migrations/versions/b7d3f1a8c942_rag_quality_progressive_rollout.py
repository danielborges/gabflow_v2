"""RAG quality progressive rollout lifecycle

Revision ID: b7d3f1a8c942
Revises: a6c9e2f4b817
Create Date: 2026-07-30 00:00:00
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "b7d3f1a8c942"
down_revision = "a6c9e2f4b817"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "rag_learning_artifacts",
        sa.Column("rollout_state", sa.String(length=24), nullable=True),
    )
    op.add_column(
        "rag_learning_artifacts",
        sa.Column(
            "rollout_stage_index",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
    )
    op.add_column(
        "rag_learning_artifacts",
        sa.Column("rollout_started_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "rag_learning_artifacts",
        sa.Column(
            "rollout_stage_started_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.add_column(
        "rag_learning_artifacts",
        sa.Column(
            "rollout_next_check_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    json_type = sa.JSON()
    if op.get_bind().dialect.name == "postgresql":
        json_type = postgresql.JSONB(astext_type=sa.Text())
    op.add_column(
        "rag_learning_artifacts",
        sa.Column(
            "rollout_history",
            json_type,
            server_default=sa.text("'[]'"),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_rag_learning_artifacts_rollout_state",
        "rag_learning_artifacts",
        ["rollout_state"],
    )
    op.create_index(
        "ix_rag_learning_artifacts_rollout_next_check_at",
        "rag_learning_artifacts",
        ["rollout_next_check_at"],
    )


def downgrade():
    op.drop_index(
        "ix_rag_learning_artifacts_rollout_next_check_at",
        table_name="rag_learning_artifacts",
    )
    op.drop_index(
        "ix_rag_learning_artifacts_rollout_state",
        table_name="rag_learning_artifacts",
    )
    for column in (
        "rollout_history",
        "rollout_next_check_at",
        "rollout_stage_started_at",
        "rollout_started_at",
        "rollout_stage_index",
        "rollout_state",
    ):
        op.drop_column("rag_learning_artifacts", column)
