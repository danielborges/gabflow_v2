"""RAG learning evaluation activation and rollback

Revision ID: d19f2a7c4e83
Revises: c08e1f4a6b72
Create Date: 2026-07-30 00:00:00
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "d19f2a7c4e83"
down_revision = "c08e1f4a6b72"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.add_column(
        "rag_assistant_queries",
        sa.Column(
            "learning_artifacts",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
    )
    op.add_column(
        "rag_learning_artifacts",
        sa.Column(
            "evaluation_details",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
    )
    op.add_column(
        "rag_learning_artifacts",
        sa.Column("activated_by_id", sa.Uuid(), nullable=True),
    )
    op.add_column(
        "rag_learning_artifacts",
        sa.Column("activation_mode", sa.String(length=20), nullable=True),
    )
    op.add_column(
        "rag_learning_artifacts",
        sa.Column(
            "rollout_percentage",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
    )
    op.add_column(
        "rag_learning_artifacts",
        sa.Column(
            "online_metrics",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
    )
    op.create_check_constraint(
        "ck_rag_learning_artifacts_rollout_percentage",
        "rag_learning_artifacts",
        "rollout_percentage >= 0 AND rollout_percentage <= 100",
    )
    op.create_foreign_key(
        "fk_rag_learning_artifacts_tenant_activator",
        "rag_learning_artifacts",
        "users",
        ["tenant_id", "activated_by_id"],
        ["tenant_id", "id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        "ix_rag_learning_artifacts_activated_by_id",
        "rag_learning_artifacts",
        ["activated_by_id"],
    )
    op.create_index(
        "uq_rag_learning_artifacts_one_active",
        "rag_learning_artifacts",
        ["tenant_id", "artifact_type"],
        unique=True,
        postgresql_where=sa.text("status = 'ATIVO'"),
    )


def downgrade():
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.drop_index(
        "uq_rag_learning_artifacts_one_active",
        table_name="rag_learning_artifacts",
    )
    op.drop_index(
        "ix_rag_learning_artifacts_activated_by_id",
        table_name="rag_learning_artifacts",
    )
    op.drop_constraint(
        "fk_rag_learning_artifacts_tenant_activator",
        "rag_learning_artifacts",
        type_="foreignkey",
    )
    op.drop_constraint(
        "ck_rag_learning_artifacts_rollout_percentage",
        "rag_learning_artifacts",
        type_="check",
    )
    for column in (
        "online_metrics",
        "rollout_percentage",
        "activation_mode",
        "activated_by_id",
        "evaluation_details",
    ):
        op.drop_column("rag_learning_artifacts", column)
    op.drop_column("rag_assistant_queries", "learning_artifacts")
