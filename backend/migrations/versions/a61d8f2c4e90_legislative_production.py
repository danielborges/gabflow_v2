"""legislative production

Revision ID: a61d8f2c4e90
Revises: f2a7c0d91b34
Create Date: 2026-07-17 10:30:00
"""

import sqlalchemy as sa
from alembic import op

revision = "a61d8f2c4e90"
down_revision = "f2a7c0d91b34"
branch_labels = None
depends_on = None

document_type = sa.Enum(
    "INDICACAO", "REQUERIMENTO", "OFICIO", "MOCAO", "PEDIDO_INFORMACAO", "PROJETO_LEI",
    name="legislative_document_type",
)
draft_status = sa.Enum(
    "RASCUNHO", "EM_REVISAO", "APROVADA", "REJEITADA",
    name="legislative_draft_status",
)
generation_status = sa.Enum(
    "PENDENTE", "PROCESSANDO", "CONCLUIDA", "FALHOU",
    name="legislative_generation_status",
)


def upgrade():
    op.create_table(
        "legislative_templates",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("document_type", document_type, nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("structure", sa.Text(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("created_by_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "name"),
    )
    op.create_index("ix_legislative_templates_tenant_id", "legislative_templates", ["tenant_id"])
    op.create_index("ix_legislative_templates_document_type", "legislative_templates", ["document_type"])

    op.create_table(
        "legislative_drafts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("document_type", document_type, nullable=False),
        sa.Column("status", draft_status, nullable=False),
        sa.Column("generation_status", generation_status, nullable=False),
        sa.Column("title", sa.String(length=240), nullable=False),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("justification", sa.Text(), nullable=True),
        sa.Column("legal_basis", sa.JSON(), nullable=False),
        sa.Column("sources", sa.JSON(), nullable=False),
        sa.Column("unsupported_passages", sa.JSON(), nullable=False),
        sa.Column("similar_proposals", sa.JSON(), nullable=False),
        sa.Column("generation_metadata", sa.JSON(), nullable=False),
        sa.Column("template_id", sa.Uuid(), nullable=True),
        sa.Column("ai_execution_id", sa.Uuid(), nullable=True),
        sa.Column("current_version", sa.Integer(), nullable=False),
        sa.Column("protocol_number", sa.String(length=100), nullable=True),
        sa.Column("protocolled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_id", sa.Uuid(), nullable=False),
        sa.Column("reviewed_by_id", sa.Uuid(), nullable=True),
        sa.Column("approved_by_id", sa.Uuid(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["ai_execution_id"], ["ai_executions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["approved_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["reviewed_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["template_id"], ["legislative_templates.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("ai_execution_id"),
        sa.UniqueConstraint("tenant_id", "protocol_number"),
    )
    for column in ("tenant_id", "document_type", "status", "generation_status", "template_id", "ai_execution_id", "created_at"):
        op.create_index(f"ix_legislative_drafts_{column}", "legislative_drafts", [column])

    op.create_table(
        "legislative_draft_requests",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("draft_id", sa.Uuid(), nullable=False),
        sa.Column("request_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["draft_id"], ["legislative_drafts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["request_id"], ["service_requests.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("draft_id", "request_id"),
    )
    for column in ("tenant_id", "draft_id", "request_id"):
        op.create_index(f"ix_legislative_draft_requests_{column}", "legislative_draft_requests", [column])

    op.create_table(
        "legislative_draft_versions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("draft_id", sa.Uuid(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=240), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("justification", sa.Text(), nullable=True),
        sa.Column("legal_basis", sa.JSON(), nullable=False),
        sa.Column("unsupported_passages", sa.JSON(), nullable=False),
        sa.Column("change_reason", sa.String(length=500), nullable=False),
        sa.Column("created_by_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["draft_id"], ["legislative_drafts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("draft_id", "version_number"),
    )
    for column in ("tenant_id", "draft_id", "created_at"):
        op.create_index(f"ix_legislative_draft_versions_{column}", "legislative_draft_versions", [column])


def downgrade():
    op.drop_table("legislative_draft_versions")
    op.drop_table("legislative_draft_requests")
    op.drop_table("legislative_drafts")
    op.drop_table("legislative_templates")
    if op.get_bind().dialect.name == "postgresql":
        generation_status.drop(op.get_bind(), checkfirst=True)
        draft_status.drop(op.get_bind(), checkfirst=True)
        document_type.drop(op.get_bind(), checkfirst=True)
