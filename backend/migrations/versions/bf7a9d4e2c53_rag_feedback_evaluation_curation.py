"""RAG feedback evaluation curation

Revision ID: bf7a9d4e2c53
Revises: ae6f8c3d1b42
Create Date: 2026-07-30 00:00:00
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "bf7a9d4e2c53"
down_revision = "ae6f8c3d1b42"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.add_column(
        "rag_evaluation_questions",
        sa.Column(
            "expected_source_refs",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
    )
    op.add_column(
        "rag_evaluation_questions",
        sa.Column(
            "hard_negative_source_refs",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
    )
    op.add_column(
        "rag_evaluation_questions",
        sa.Column("expected_method", sa.String(length=20), nullable=True),
    )
    op.add_column(
        "rag_evaluation_questions",
        sa.Column(
            "expected_filters",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
    )
    op.add_column(
        "rag_evaluation_questions",
        sa.Column("source_feedback_id", sa.Uuid(), nullable=True),
    )
    op.add_column(
        "rag_evaluation_questions",
        sa.Column("curated_by_id", sa.Uuid(), nullable=True),
    )
    op.add_column(
        "rag_evaluation_questions",
        sa.Column("curated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "rag_evaluation_questions",
        sa.Column("deactivation_reason", sa.String(length=120), nullable=True),
    )
    op.create_check_constraint(
        "ck_rag_evaluation_questions_expected_method",
        "rag_evaluation_questions",
        "expected_method IS NULL OR expected_method IN "
        "('DOCUMENTAL', 'ESTRUTURADO', 'HIBRIDO')",
    )
    op.create_unique_constraint(
        "uq_rag_evaluation_questions_source_feedback",
        "rag_evaluation_questions",
        ["tenant_id", "source_feedback_id"],
    )
    op.create_foreign_key(
        "fk_rag_evaluation_questions_tenant_curator",
        "rag_evaluation_questions",
        "users",
        ["tenant_id", "curated_by_id"],
        ["tenant_id", "id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_rag_evaluation_questions_tenant_feedback",
        "rag_evaluation_questions",
        "rag_query_feedback",
        ["tenant_id", "source_feedback_id"],
        ["tenant_id", "id"],
        ondelete="RESTRICT",
    )
    for column in ("expected_method", "source_feedback_id", "curated_by_id"):
        op.create_index(
            f"ix_rag_evaluation_questions_{column}",
            "rag_evaluation_questions",
            [column],
        )

    for column in ("routing_accuracy", "filter_accuracy", "hard_negative_rate"):
        op.add_column(
            "rag_evaluation_runs",
            sa.Column(
                column,
                sa.Float(),
                server_default="0",
                nullable=False,
            ),
        )


def downgrade():
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    for column in ("hard_negative_rate", "filter_accuracy", "routing_accuracy"):
        op.drop_column("rag_evaluation_runs", column)
    for column in ("curated_by_id", "source_feedback_id", "expected_method"):
        op.drop_index(
            f"ix_rag_evaluation_questions_{column}",
            table_name="rag_evaluation_questions",
        )
    op.drop_constraint(
        "fk_rag_evaluation_questions_tenant_feedback",
        "rag_evaluation_questions",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_rag_evaluation_questions_tenant_curator",
        "rag_evaluation_questions",
        type_="foreignkey",
    )
    op.drop_constraint(
        "uq_rag_evaluation_questions_source_feedback",
        "rag_evaluation_questions",
        type_="unique",
    )
    op.drop_constraint(
        "ck_rag_evaluation_questions_expected_method",
        "rag_evaluation_questions",
        type_="check",
    )
    for column in (
        "deactivation_reason",
        "curated_at",
        "curated_by_id",
        "source_feedback_id",
        "expected_filters",
        "expected_method",
        "hard_negative_source_refs",
        "expected_source_refs",
    ):
        op.drop_column("rag_evaluation_questions", column)
