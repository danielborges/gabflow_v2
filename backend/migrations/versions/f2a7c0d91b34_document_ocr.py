"""document ocr

Revision ID: f2a7c0d91b34
Revises: 4c3a9d7012ef
Create Date: 2026-07-17 12:30:00

"""

import sqlalchemy as sa
from alembic import op

revision = "f2a7c0d91b34"
down_revision = "4c3a9d7012ef"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "document_ocrs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("attachment_id", sa.Uuid(), nullable=False),
        sa.Column("request_id", sa.Uuid(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "PENDENTE", "PROCESSANDO", "CONCLUIDO", "FALHOU",
                name="document_ocr_status",
            ),
            nullable=False,
        ),
        sa.Column(
            "review_status",
            sa.Enum(
                "PENDENTE", "ACEITO", "EDITADO", "REJEITADO",
                name="document_ocr_review_status",
            ),
            nullable=False,
        ),
        sa.Column("provider", sa.String(length=80), nullable=False),
        sa.Column("model", sa.String(length=120), nullable=False),
        sa.Column("language", sa.String(length=20), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("page_count", sa.Integer(), nullable=True),
        sa.Column("extracted_text", sa.Text(), nullable=True),
        sa.Column("reviewed_text", sa.Text(), nullable=True),
        sa.Column("pages", sa.JSON(), nullable=True),
        sa.Column("requested_by_id", sa.Uuid(), nullable=False),
        sa.Column("reviewed_by_id", sa.Uuid(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["attachment_id"], ["attachments.id"],
            name=op.f("fk_document_ocrs_attachment_id_attachments"), ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["request_id"], ["service_requests.id"],
            name=op.f("fk_document_ocrs_request_id_service_requests"), ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["requested_by_id"], ["users.id"],
            name=op.f("fk_document_ocrs_requested_by_id_users"), ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["reviewed_by_id"], ["users.id"],
            name=op.f("fk_document_ocrs_reviewed_by_id_users"), ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"],
            name=op.f("fk_document_ocrs_tenant_id_tenants"), ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_document_ocrs")),
        sa.UniqueConstraint("attachment_id", name=op.f("uq_document_ocrs_attachment_id")),
    )
    with op.batch_alter_table("document_ocrs", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_document_ocrs_created_at"), ["created_at"])
        batch_op.create_index(batch_op.f("ix_document_ocrs_request_id"), ["request_id"])
        batch_op.create_index(batch_op.f("ix_document_ocrs_review_status"), ["review_status"])
        batch_op.create_index(batch_op.f("ix_document_ocrs_reviewed_by_id"), ["reviewed_by_id"])
        batch_op.create_index(batch_op.f("ix_document_ocrs_status"), ["status"])
        batch_op.create_index(batch_op.f("ix_document_ocrs_tenant_id"), ["tenant_id"])


def downgrade():
    with op.batch_alter_table("document_ocrs", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_document_ocrs_tenant_id"))
        batch_op.drop_index(batch_op.f("ix_document_ocrs_status"))
        batch_op.drop_index(batch_op.f("ix_document_ocrs_reviewed_by_id"))
        batch_op.drop_index(batch_op.f("ix_document_ocrs_review_status"))
        batch_op.drop_index(batch_op.f("ix_document_ocrs_request_id"))
        batch_op.drop_index(batch_op.f("ix_document_ocrs_created_at"))
    op.drop_table("document_ocrs")
    if op.get_bind().dialect.name == "postgresql":
        sa.Enum(name="document_ocr_review_status").drop(op.get_bind(), checkfirst=True)
        sa.Enum(name="document_ocr_status").drop(op.get_bind(), checkfirst=True)
