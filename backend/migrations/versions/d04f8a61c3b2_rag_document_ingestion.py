"""rag document ingestion

Revision ID: d04f8a61c3b2
Revises: c91e4f7a2d10
Create Date: 2026-07-17 13:30:00
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "d04f8a61c3b2"
down_revision = "c91e4f7a2d10"
branch_labels = None
depends_on = None


def upgrade():
    access = postgresql.ENUM(
        "INTERNO", "RESTRITO", name="rag_document_access", create_type=False
    )
    lifecycle = postgresql.ENUM(
        "RASCUNHO",
        "VIGENTE",
        "HISTORICO",
        "REVOGADO",
        name="rag_document_lifecycle",
        create_type=False,
    )
    ingestion = postgresql.ENUM(
        "PENDENTE",
        "PROCESSANDO",
        "INDEXADO",
        "FALHOU",
        name="rag_ingestion_status",
        create_type=False,
    )
    access.create(op.get_bind(), checkfirst=True)
    lifecycle.create(op.get_bind(), checkfirst=True)
    ingestion.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "rag_documents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(240), nullable=False),
        sa.Column("document_type", sa.String(80), nullable=False),
        sa.Column("agency", sa.String(180)),
        sa.Column("access_level", access, nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("created_by_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "title"),
    )
    op.create_table(
        "rag_document_versions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("version_label", sa.String(80), nullable=False),
        sa.Column("lifecycle_status", lifecycle, nullable=False),
        sa.Column("ingestion_status", ingestion, nullable=False),
        sa.Column("valid_from", sa.Date()),
        sa.Column("valid_until", sa.Date()),
        sa.Column("source_url", sa.String(1000)),
        sa.Column("storage_key", sa.String(400), nullable=False),
        sa.Column("original_name", sa.String(255), nullable=False),
        sa.Column("mime_type", sa.String(120), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("checksum", sa.String(64), nullable=False),
        sa.Column("extracted_text", sa.Text()),
        sa.Column("page_count", sa.Integer()),
        sa.Column("language", sa.String(20), nullable=False),
        sa.Column("embedding_model", sa.String(120)),
        sa.Column("chunk_count", sa.Integer(), nullable=False),
        sa.Column("error", sa.Text()),
        sa.Column("created_by_id", sa.Uuid(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("indexed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["document_id"], ["rag_documents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "document_id", "version_number", name="uq_rag_version_document_number"
        ),
        sa.UniqueConstraint(
            "document_id", "version_label", name="uq_rag_version_document_label"
        ),
        sa.UniqueConstraint("storage_key"),
    )
    op.create_table(
        "rag_chunks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("version_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("content_checksum", sa.String(64), nullable=False),
        sa.Column("page_start", sa.Integer()),
        sa.Column("page_end", sa.Integer()),
        sa.Column("section", sa.String(240)),
        sa.Column("embedding", sa.JSON(), nullable=False),
        sa.Column("embedding_model", sa.String(120), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["version_id"], ["rag_document_versions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("version_id", "position"),
    )
    for table, columns in {
        "rag_documents": (
            "tenant_id",
            "document_type",
            "agency",
            "access_level",
            "active",
            "created_at",
        ),
        "rag_document_versions": (
            "tenant_id",
            "document_id",
            "lifecycle_status",
            "ingestion_status",
            "checksum",
            "created_at",
        ),
        "rag_chunks": ("tenant_id", "version_id", "content_checksum"),
    }.items():
        for column in columns:
            op.create_index(f"ix_{table}_{column}", table, [column])


def downgrade():
    op.drop_table("rag_chunks")
    op.drop_table("rag_document_versions")
    op.drop_table("rag_documents")
    postgresql.ENUM(name="rag_ingestion_status").drop(op.get_bind(), checkfirst=True)
    postgresql.ENUM(name="rag_document_lifecycle").drop(op.get_bind(), checkfirst=True)
    postgresql.ENUM(name="rag_document_access").drop(op.get_bind(), checkfirst=True)
