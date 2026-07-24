"""operational RAG memory

Revision ID: 4c8d0f2a6b93
Revises: 3b7c9e1f5a82
Create Date: 2026-07-24 23:00:00
"""

import os

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "4c8d0f2a6b93"
down_revision = "3b7c9e1f5a82"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    status = sa.Enum(
        "ATIVA", "INELEGIVEL", "EXPIRADA", name="rag_knowledge_source_status"
    )
    status.create(bind, checkfirst=True)
    op.create_table(
        "rag_knowledge_sources",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("source_module", sa.String(length=60), nullable=False),
        sa.Column("entity_type", sa.String(length=80), nullable=False),
        sa.Column("entity_id", sa.Uuid(), nullable=False),
        sa.Column("purpose", sa.String(length=120), nullable=False),
        sa.Column("legal_basis", sa.String(length=160), nullable=False),
        sa.Column(
            "access_level",
            postgresql.ENUM(name="rag_document_access", create_type=False),
            nullable=False,
        ),
        sa.Column("retention_until", sa.Date(), nullable=True),
        sa.Column(
            "status",
            postgresql.ENUM(name="rag_knowledge_source_status", create_type=False),
            nullable=False,
        ),
        sa.Column("eligibility_reason", sa.String(length=120), nullable=True),
        sa.Column("content_hash", sa.String(length=64), nullable=True),
        sa.Column("source_version", sa.Integer(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=True),
        sa.Column("latest_version_id", sa.Uuid(), nullable=True),
        sa.Column("last_projected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "document_id"],
            ["rag_documents.tenant_id", "rag_documents.id"],
            name="fk_rag_knowledge_sources_tenant_document",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "latest_version_id"],
            ["rag_document_versions.tenant_id", "rag_document_versions.id"],
            name="fk_rag_knowledge_sources_tenant_version",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "source_module",
            "entity_type",
            "entity_id",
            name="uq_rag_knowledge_sources_origin",
        ),
    )
    for column in (
        "tenant_id",
        "source_module",
        "entity_type",
        "entity_id",
        "status",
        "content_hash",
        "document_id",
        "latest_version_id",
    ):
        op.create_index(
            f"ix_rag_knowledge_sources_{column}",
            "rag_knowledge_sources",
            [column],
        )

    op.execute("ALTER TABLE rag_knowledge_sources ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE rag_knowledge_sources FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY rag_knowledge_sources_isolation
        ON rag_knowledge_sources
        FOR ALL
        USING (
            tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
        )
        WITH CHECK (
            tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
        )
        """
    )
    _grant_runtime_access()


def downgrade():
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute(
        "DROP POLICY IF EXISTS rag_knowledge_sources_isolation "
        "ON rag_knowledge_sources"
    )
    op.execute("ALTER TABLE rag_knowledge_sources NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE rag_knowledge_sources DISABLE ROW LEVEL SECURITY")
    op.drop_table("rag_knowledge_sources")
    sa.Enum(name="rag_knowledge_source_status").drop(bind, checkfirst=True)


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
        op.execute(
            "GRANT SELECT, INSERT, UPDATE, DELETE ON "
            f"rag_knowledge_sources TO {quoted}"
        )
