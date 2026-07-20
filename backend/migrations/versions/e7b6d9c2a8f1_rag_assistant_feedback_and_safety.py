"""rag assistant feedback and safety

Revision ID: e7b6d9c2a8f1
Revises: d04f8a61c3b2
Create Date: 2026-07-20 13:25:00
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "e7b6d9c2a8f1"
down_revision = "d04f8a61c3b2"
branch_labels = None
depends_on = None


def upgrade():
    feedback_rating = postgresql.ENUM(
        "POSITIVA",
        "NEGATIVA",
        "CORRIGIDA",
        name="rag_query_feedback_rating",
        create_type=False,
    )
    feedback_rating.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "rag_assistant_queries",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("query_text", sa.Text(), nullable=False),
        sa.Column("query_hash", sa.String(64), nullable=False),
        sa.Column("response", sa.Text(), nullable=False),
        sa.Column("sources", sa.JSON(), nullable=False),
        sa.Column("safety_flags", sa.JSON(), nullable=False),
        sa.Column("grounded", sa.Boolean(), nullable=False),
        sa.Column("refused", sa.Boolean(), nullable=False),
        sa.Column("evidence_threshold", sa.Float(), nullable=False),
        sa.Column("embedding_model", sa.String(120), nullable=False),
        sa.Column("fallback_used", sa.Boolean(), nullable=False),
        sa.Column("feedback_rating", feedback_rating),
        sa.Column("feedback_comment", sa.Text()),
        sa.Column("corrected_response", sa.Text()),
        sa.Column("reviewed_by_id", sa.Uuid()),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["reviewed_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in (
        "tenant_id",
        "user_id",
        "query_hash",
        "grounded",
        "refused",
        "feedback_rating",
        "reviewed_by_id",
        "created_at",
    ):
        op.create_index(f"ix_rag_assistant_queries_{column}", "rag_assistant_queries", [column])


def downgrade():
    op.drop_table("rag_assistant_queries")
    postgresql.ENUM(name="rag_query_feedback_rating").drop(op.get_bind(), checkfirst=True)
