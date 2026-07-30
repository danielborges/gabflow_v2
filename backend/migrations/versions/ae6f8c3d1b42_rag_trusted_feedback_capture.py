"""RAG trusted feedback capture

Revision ID: ae6f8c3d1b42
Revises: 9d5f7b2c0e31
Create Date: 2026-07-30 00:00:00
"""

import os

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "ae6f8c3d1b42"
down_revision = "9d5f7b2c0e31"
branch_labels = None
depends_on = None

TABLES = ("rag_query_feedback", "rag_feedback_source_judgments")


def upgrade():
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    feedback_status = postgresql.ENUM(
        "PENDENTE_REVISAO",
        "APROVADO",
        "QUARENTENA",
        "REJEITADO",
        "REVOGADO",
        "SUPERADO",
        name="rag_feedback_status",
        create_type=False,
    )
    source_judgment = postgresql.ENUM(
        "RELEVANTE",
        "IRRELEVANTE",
        "AUSENTE",
        name="rag_feedback_source_judgment",
        create_type=False,
    )
    feedback_reason = postgresql.ENUM(
        "FONTES_IRRELEVANTES",
        "FONTE_AUSENTE",
        "RESPOSTA_INCORRETA",
        "CITACAO_INCORRETA",
        "FONTE_DESATUALIZADA",
        "JURISDICAO_INCORRETA",
        "ROTEAMENTO_INCORRETO",
        "FILTROS_INCORRETOS",
        "RECUSA_INDEVIDA",
        "DEVERIA_RECUSAR",
        "PROBLEMA_DE_ESTILO",
        name="rag_feedback_reason",
        create_type=False,
    )
    moderation_mode = postgresql.ENUM(
        "AUTOMATICA",
        "HUMANA",
        name="rag_feedback_moderation_mode",
        create_type=False,
    )
    for enum_type in (
        feedback_status,
        source_judgment,
        feedback_reason,
        moderation_mode,
    ):
        enum_type.create(bind, checkfirst=True)

    op.create_unique_constraint(
        "uq_rag_assistant_queries_tenant_id_id",
        "rag_assistant_queries",
        ["tenant_id", "id"],
    )
    op.create_table(
        "rag_query_feedback",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("query_id", sa.Uuid(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("previous_feedback_id", sa.Uuid(), nullable=True),
        sa.Column("idempotency_key", sa.String(length=120), nullable=True),
        sa.Column(
            "rating",
            postgresql.ENUM(
                name="rag_query_feedback_rating",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column(
            "reasons",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("corrected_response", sa.Text(), nullable=True),
        sa.Column("expected_method", sa.String(length=20), nullable=True),
        sa.Column(
            "expected_filters",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("status", feedback_status, nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("created_by_id", sa.Uuid(), nullable=False),
        sa.Column("moderation_mode", moderation_mode, nullable=True),
        sa.Column("moderation_rule", sa.String(length=120), nullable=True),
        sa.Column("moderated_by_id", sa.Uuid(), nullable=True),
        sa.Column("moderated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("moderation_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("revision > 0", name="ck_rag_query_feedback_revision_positive"),
        sa.CheckConstraint(
            "expected_method IS NULL OR expected_method IN "
            "('DOCUMENTAL', 'ESTRUTURADO', 'HIBRIDO')",
            name="ck_rag_query_feedback_expected_method",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "query_id"],
            ["rag_assistant_queries.tenant_id", "rag_assistant_queries.id"],
            name="fk_rag_query_feedback_tenant_query",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "previous_feedback_id"],
            ["rag_query_feedback.tenant_id", "rag_query_feedback.id"],
            name="fk_rag_query_feedback_tenant_previous",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "created_by_id"],
            ["users.tenant_id", "users.id"],
            name="fk_rag_query_feedback_tenant_creator",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "moderated_by_id"],
            ["users.tenant_id", "users.id"],
            name="fk_rag_query_feedback_tenant_moderator",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "id",
            name="uq_rag_query_feedback_tenant_id_id",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "query_id",
            "revision",
            name="uq_rag_query_feedback_revision",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "query_id",
            "idempotency_key",
            name="uq_rag_query_feedback_idempotency",
        ),
    )
    op.create_table(
        "rag_feedback_source_judgments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("feedback_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("version_id", sa.Uuid(), nullable=False),
        sa.Column("chunk_id", sa.Uuid(), nullable=True),
        sa.Column("source_scope", sa.String(length=10), nullable=False),
        sa.Column("judgment", source_judgment, nullable=False),
        sa.Column("reason", feedback_reason, nullable=False),
        sa.Column("original_position", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "source_scope IN ('GLOBAL', 'PRIVADO')",
            name="ck_rag_feedback_source_scope",
        ),
        sa.CheckConstraint(
            "original_position IS NULL OR original_position >= 0",
            name="ck_rag_feedback_source_position",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "feedback_id"],
            ["rag_query_feedback.tenant_id", "rag_query_feedback.id"],
            name="fk_rag_feedback_source_judgments_tenant_feedback",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "feedback_id",
            "document_id",
            "version_id",
            name="uq_rag_feedback_source_judgment",
        ),
    )

    indexes = {
        "rag_query_feedback": (
            "tenant_id",
            "query_id",
            "previous_feedback_id",
            "rating",
            "status",
            "content_hash",
            "created_by_id",
            "moderated_by_id",
            "created_at",
        ),
        "rag_feedback_source_judgments": (
            "tenant_id",
            "feedback_id",
            "document_id",
            "version_id",
            "chunk_id",
            "judgment",
            "reason",
        ),
    }
    for table, columns in indexes.items():
        for column in columns:
            op.create_index(f"ix_{table}_{column}", table, [column])
        _enable_rls(table)
    _grant_runtime_access()


def downgrade():
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    for table in reversed(TABLES):
        op.execute(f"DROP POLICY IF EXISTS {table}_isolation ON {table}")
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
        op.drop_table(table)
    op.drop_constraint(
        "uq_rag_assistant_queries_tenant_id_id",
        "rag_assistant_queries",
        type_="unique",
    )
    for enum_name in (
        "rag_feedback_moderation_mode",
        "rag_feedback_reason",
        "rag_feedback_source_judgment",
        "rag_feedback_status",
    ):
        postgresql.ENUM(name=enum_name).drop(bind, checkfirst=True)


def _enable_rls(table: str) -> None:
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"""
        CREATE POLICY {table}_isolation
        ON {table}
        FOR ALL
        USING (
            tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
        )
        WITH CHECK (
            tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
        )
        """
    )


def _grant_runtime_access() -> None:
    bind = op.get_bind()
    roles = {
        os.getenv("APP_DB_USER", "gabflow_app"),
        os.getenv("WORKER_DB_USER", "gabflow_worker"),
    }
    available = {
        row[0]
        for row in bind.execute(
            sa.text("SELECT rolname FROM pg_roles WHERE rolname = ANY(:roles)"),
            {"roles": list(roles)},
        )
    }
    for role in roles & available:
        quoted = bind.dialect.identifier_preparer.quote_identifier(role)
        for table in TABLES:
            op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO {quoted}")
