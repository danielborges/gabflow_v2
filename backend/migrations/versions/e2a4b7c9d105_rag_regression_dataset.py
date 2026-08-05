"""RAG regression dataset cases

Revision ID: e2a4b7c9d105
Revises: d19f2a7c4e83
Create Date: 2026-07-30 00:00:00
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "e2a4b7c9d105"
down_revision = "d19f2a7c4e83"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.add_column(
        "rag_evaluation_questions",
        sa.Column(
            "case_origin",
            sa.String(length=20),
            server_default="MANUAL",
            nullable=False,
        ),
    )
    op.add_column(
        "rag_evaluation_questions",
        sa.Column(
            "failure_reasons",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
    )
    op.add_column(
        "rag_evaluation_questions",
        sa.Column(
            "severity",
            sa.String(length=10),
            server_default="MEDIA",
            nullable=False,
        ),
    )
    op.add_column(
        "rag_evaluation_questions",
        sa.Column(
            "tags",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
    )
    op.add_column(
        "rag_evaluation_questions",
        sa.Column(
            "baseline_snapshot",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
    )
    op.add_column(
        "rag_evaluation_questions",
        sa.Column("baseline_captured_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "rag_evaluation_questions",
        sa.Column("source_query_id", sa.Uuid(), nullable=True),
    )
    op.execute(
        """
        UPDATE rag_evaluation_questions
        SET case_origin = CASE
            WHEN source_feedback_id IS NOT NULL THEN 'FEEDBACK'
            ELSE 'MANUAL'
        END
        """
    )
    op.create_check_constraint(
        "ck_rag_evaluation_questions_origin",
        "rag_evaluation_questions",
        "case_origin IN ('MANUAL', 'FEEDBACK', 'REGRESSAO')",
    )
    op.create_check_constraint(
        "ck_rag_evaluation_questions_severity",
        "rag_evaluation_questions",
        "severity IN ('BAIXA', 'MEDIA', 'ALTA', 'CRITICA')",
    )
    op.create_foreign_key(
        "fk_rag_evaluation_questions_tenant_query",
        "rag_evaluation_questions",
        "rag_assistant_queries",
        ["tenant_id", "source_query_id"],
        ["tenant_id", "id"],
        ondelete="RESTRICT",
    )
    op.create_unique_constraint(
        "uq_rag_evaluation_questions_source_query",
        "rag_evaluation_questions",
        ["tenant_id", "source_query_id"],
    )
    op.create_index(
        "ix_rag_evaluation_questions_case_origin",
        "rag_evaluation_questions",
        ["case_origin"],
    )
    op.create_index(
        "ix_rag_evaluation_questions_severity",
        "rag_evaluation_questions",
        ["severity"],
    )
    op.create_index(
        "ix_rag_evaluation_questions_source_query_id",
        "rag_evaluation_questions",
        ["source_query_id"],
    )


def downgrade():
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.drop_index(
        "ix_rag_evaluation_questions_source_query_id",
        table_name="rag_evaluation_questions",
    )
    op.drop_index(
        "ix_rag_evaluation_questions_severity",
        table_name="rag_evaluation_questions",
    )
    op.drop_index(
        "ix_rag_evaluation_questions_case_origin",
        table_name="rag_evaluation_questions",
    )
    op.drop_constraint(
        "uq_rag_evaluation_questions_source_query",
        "rag_evaluation_questions",
        type_="unique",
    )
    op.drop_constraint(
        "fk_rag_evaluation_questions_tenant_query",
        "rag_evaluation_questions",
        type_="foreignkey",
    )
    op.drop_constraint(
        "ck_rag_evaluation_questions_severity",
        "rag_evaluation_questions",
        type_="check",
    )
    op.drop_constraint(
        "ck_rag_evaluation_questions_origin",
        "rag_evaluation_questions",
        type_="check",
    )
    for column in (
        "source_query_id",
        "baseline_captured_at",
        "baseline_snapshot",
        "tags",
        "severity",
        "failure_reasons",
        "case_origin",
    ):
        op.drop_column("rag_evaluation_questions", column)
