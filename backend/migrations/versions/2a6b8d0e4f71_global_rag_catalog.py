"""global RAG catalog

Revision ID: 2a6b8d0e4f71
Revises: 1f4a7c9d2e60
Create Date: 2026-07-24 20:00:00
"""

import os

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "2a6b8d0e4f71"
down_revision = "1f4a7c9d2e60"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.execute("ALTER TYPE user_role ADD VALUE IF NOT EXISTS 'GLOBAL_KNOWLEDGE_ADMIN'")
    op.execute("CREATE SCHEMA IF NOT EXISTS rag_global")

    distribution_policy = sa.Enum(
        "OBRIGATORIA",
        "PADRAO",
        "OPCIONAL",
        "DIRECIONADA",
        "RESTRITA_JURISDICAO",
        "PRIVADA_PLATAFORMA",
        name="rag_global_distribution_policy",
    )
    catalog_status = sa.Enum(
        "RASCUNHO",
        "PUBLICADA",
        "SUSPENSA",
        "ARQUIVADA",
        name="rag_global_catalog_status",
    )
    version_status = sa.Enum(
        "RASCUNHO",
        "PUBLICADA",
        "SUSPENSA",
        "SUBSTITUIDA",
        "REVOGADA",
        name="rag_global_version_status",
    )
    distribution_policy.create(bind, checkfirst=True)
    catalog_status.create(bind, checkfirst=True)
    version_status.create(bind, checkfirst=True)

    op.create_table(
        "collections",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=180), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "distribution_policy",
            postgresql.ENUM(name="rag_global_distribution_policy", create_type=False),
            nullable=False,
        ),
        sa.Column("jurisdiction", sa.JSON(), nullable=False),
        sa.Column(
            "status",
            postgresql.ENUM(name="rag_global_catalog_status", create_type=False),
            nullable=False,
        ),
        sa.Column("created_by_id", sa.Uuid(), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["created_by_id"], ["public.users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", name="uq_rag_global_collections_name"),
        schema="rag_global",
    )
    _index("ix_rag_global_collections_distribution_policy", "collections", ["distribution_policy"])
    _index("ix_rag_global_collections_status", "collections", ["status"])
    _index("ix_rag_global_collections_created_by_id", "collections", ["created_by_id"])
    _index("ix_rag_global_collections_created_at", "collections", ["created_at"])

    op.create_table(
        "documents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("collection_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=240), nullable=False),
        sa.Column("document_type", sa.String(length=80), nullable=False),
        sa.Column("agency", sa.String(length=180), nullable=True),
        sa.Column("jurisdiction", sa.JSON(), nullable=False),
        sa.Column("provenance", sa.Text(), nullable=False),
        sa.Column("confidence_level", sa.Float(), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("created_by_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["collection_id"],
            ["rag_global.collections.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["created_by_id"], ["public.users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "collection_id",
            "title",
            name="uq_rag_global_documents_collection_title",
        ),
        schema="rag_global",
    )
    _index("ix_rag_global_documents_collection_id", "documents", ["collection_id"])
    _index("ix_rag_global_documents_document_type", "documents", ["document_type"])
    _index("ix_rag_global_documents_agency", "documents", ["agency"])
    _index("ix_rag_global_documents_active", "documents", ["active"])
    _index("ix_rag_global_documents_created_by_id", "documents", ["created_by_id"])
    _index("ix_rag_global_documents_created_at", "documents", ["created_at"])

    op.create_table(
        "document_versions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("version_label", sa.String(length=80), nullable=False),
        sa.Column("valid_from", sa.Date(), nullable=True),
        sa.Column("valid_until", sa.Date(), nullable=True),
        sa.Column("source_url", sa.String(length=1000), nullable=True),
        sa.Column("storage_key", sa.String(length=400), nullable=False),
        sa.Column("original_name", sa.String(length=255), nullable=False),
        sa.Column("mime_type", sa.String(length=120), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("checksum", sa.String(length=64), nullable=False),
        sa.Column("extracted_text", sa.Text(), nullable=True),
        sa.Column("page_count", sa.Integer(), nullable=True),
        sa.Column("language", sa.String(length=20), nullable=False),
        sa.Column("embedding_model", sa.String(length=120), nullable=True),
        sa.Column("chunk_count", sa.Integer(), nullable=False),
        sa.Column(
            "ingestion_status",
            postgresql.ENUM(name="rag_ingestion_status", create_type=False),
            nullable=False,
        ),
        sa.Column(
            "publication_status",
            postgresql.ENUM(name="rag_global_version_status", create_type=False),
            nullable=False,
        ),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_by_id", sa.Uuid(), nullable=False),
        sa.Column("published_by_id", sa.Uuid(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("indexed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "storage_key LIKE ('global/rag/' || document_id::text || '/' || id::text || '/%')",
            name="ck_rag_global_document_versions_storage_namespace",
        ),
        sa.ForeignKeyConstraint(["document_id"], ["rag_global.documents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_id"], ["public.users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["published_by_id"], ["public.users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("storage_key"),
        sa.UniqueConstraint(
            "document_id",
            "version_number",
            name="uq_rag_global_document_versions_number",
        ),
        sa.UniqueConstraint(
            "document_id",
            "version_label",
            name="uq_rag_global_document_versions_label",
        ),
        schema="rag_global",
    )
    _index("ix_rag_global_document_versions_document_id", "document_versions", ["document_id"])
    _index("ix_rag_global_document_versions_checksum", "document_versions", ["checksum"])
    _index(
        "ix_rag_global_document_versions_ingestion_status",
        "document_versions",
        ["ingestion_status"],
    )
    _index(
        "ix_rag_global_document_versions_publication_status",
        "document_versions",
        ["publication_status"],
    )
    _index(
        "ix_rag_global_document_versions_created_by_id",
        "document_versions",
        ["created_by_id"],
    )
    _index(
        "ix_rag_global_document_versions_published_by_id",
        "document_versions",
        ["published_by_id"],
    )
    _index("ix_rag_global_document_versions_created_at", "document_versions", ["created_at"])

    op.create_table(
        "chunks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("version_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("content_checksum", sa.String(length=64), nullable=False),
        sa.Column("page_start", sa.Integer(), nullable=True),
        sa.Column("page_end", sa.Integer(), nullable=True),
        sa.Column("section", sa.String(length=240), nullable=True),
        sa.Column("embedding", sa.JSON(), nullable=False),
        sa.Column("embedding_model", sa.String(length=120), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["version_id"],
            ["rag_global.document_versions.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "version_id",
            "position",
            name="uq_rag_global_chunks_version_position",
        ),
        schema="rag_global",
    )
    _index("ix_rag_global_chunks_version_id", "chunks", ["version_id"])
    _index("ix_rag_global_chunks_content_checksum", "chunks", ["content_checksum"])

    op.alter_column(
        "outbox_events",
        "tenant_id",
        existing_type=sa.Uuid(),
        nullable=True,
    )
    _grant_runtime_access()


def downgrade():
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    null_global_events = bind.execute(
        sa.text("SELECT 1 FROM outbox_events WHERE tenant_id IS NULL LIMIT 1")
    ).first()
    if null_global_events:
        raise RuntimeError("Remova ou arquive eventos globais da outbox antes do downgrade.")
    op.alter_column(
        "outbox_events",
        "tenant_id",
        existing_type=sa.Uuid(),
        nullable=False,
    )
    op.drop_table("chunks", schema="rag_global")
    op.drop_table("document_versions", schema="rag_global")
    op.drop_table("documents", schema="rag_global")
    op.drop_table("collections", schema="rag_global")
    op.execute("DROP SCHEMA rag_global")
    sa.Enum(name="rag_global_version_status").drop(bind, checkfirst=True)
    sa.Enum(name="rag_global_catalog_status").drop(bind, checkfirst=True)
    sa.Enum(name="rag_global_distribution_policy").drop(bind, checkfirst=True)


def _index(name: str, table: str, columns: list[str]) -> None:
    op.create_index(name, table, columns, schema="rag_global")


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
        op.execute(f"GRANT USAGE ON SCHEMA rag_global TO {quoted}")
        op.execute(
            f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA rag_global TO {quoted}"
        )
        op.execute(f"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA rag_global TO {quoted}")
