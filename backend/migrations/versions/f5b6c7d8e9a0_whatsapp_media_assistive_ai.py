"""Add WhatsApp media assets and assistive analysis.

Revision ID: f5b6c7d8e9a0
Revises: e4a5b6c7d8f9
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "f5b6c7d8e9a0"
down_revision = "e4a5b6c7d8f9"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "whatsapp_media_assets",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("message_id", sa.Uuid(), nullable=False),
        sa.Column("webhook_event_id", sa.Uuid(), nullable=False),
        sa.Column("integration_id", sa.Uuid(), nullable=False),
        sa.Column("provider_media_id", sa.String(160), nullable=False),
        sa.Column("provider_message_id", sa.String(160), nullable=False),
        sa.Column("media_type", sa.String(30), nullable=False),
        sa.Column("mime_type", sa.String(120)),
        sa.Column("original_name", sa.String(255)),
        sa.Column("caption", sa.String(1000)),
        sa.Column("provider_sha256", sa.String(128)),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("storage_key", sa.String(300)),
        sa.Column("size_bytes", sa.BigInteger()),
        sa.Column("sha256", sa.String(64)),
        sa.Column(
            "scan_status",
            postgresql.ENUM(name="attachment_scan_status", create_type=False),
        ),
        sa.Column("scan_provider", sa.String(80)),
        sa.Column("scan_engine_version", sa.String(80)),
        sa.Column("scan_signature_version", sa.String(80)),
        sa.Column("scan_threat", sa.String(160)),
        sa.Column("scan_error_code", sa.String(80)),
        sa.Column("scanned_at", sa.DateTime(timezone=True)),
        sa.Column("encryption_key_version", sa.Integer(), nullable=False),
        sa.Column("encryption_algorithm", sa.String(40)),
        sa.Column("encrypted_at", sa.DateTime(timezone=True)),
        sa.Column("analysis_type", sa.String(30)),
        sa.Column("analysis_status", sa.String(20), nullable=False),
        sa.Column("analysis_provider", sa.String(80)),
        sa.Column("analysis_model", sa.String(120)),
        sa.Column("prompt_version", sa.String(40)),
        sa.Column("confidence", sa.Float()),
        sa.Column("generated_text", sa.Text()),
        sa.Column("reviewed_text", sa.Text()),
        sa.Column("review_status", sa.String(20), nullable=False),
        sa.Column("reviewed_by_id", sa.Uuid()),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
        sa.Column("request_id", sa.Uuid()),
        sa.Column("attachment_id", sa.Uuid()),
        sa.Column("error_code", sa.String(80)),
        sa.Column("error", sa.String(1000)),
        sa.Column("created_by_id", sa.Uuid(), nullable=False),
        sa.Column("retention_until", sa.DateTime(timezone=True), nullable=False),
        sa.Column("downloaded_at", sa.DateTime(timezone=True)),
        sa.Column("analyzed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('RECEIVED', 'DOWNLOADING', 'READY', 'BLOCKED', 'FAILED')",
            name="ck_whatsapp_media_status",
        ),
        sa.CheckConstraint(
            "analysis_status IN ('NOT_APPLICABLE', 'PENDING', 'PROCESSING', 'COMPLETED', 'FAILED')",
            name="ck_whatsapp_media_analysis_status",
        ),
        sa.CheckConstraint(
            "review_status IN ('NOT_REQUIRED', 'PENDING', 'ACCEPTED', 'EDITED', 'REJECTED')",
            name="ck_whatsapp_media_review_status",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "conversation_id"],
            ["whatsapp_conversations.tenant_id", "whatsapp_conversations.id"],
            ondelete="CASCADE",
            name="fk_whatsapp_media_tenant_conversation",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "message_id"],
            ["whatsapp_messages.tenant_id", "whatsapp_messages.id"],
            ondelete="CASCADE",
            name="fk_whatsapp_media_tenant_message",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "request_id"],
            ["service_requests.tenant_id", "service_requests.id"],
            ondelete="RESTRICT",
            name="fk_whatsapp_media_tenant_request",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "created_by_id"],
            ["users.tenant_id", "users.id"],
            ondelete="RESTRICT",
            name="fk_whatsapp_media_tenant_creator",
        ),
        sa.ForeignKeyConstraint(
            ["webhook_event_id"], ["whatsapp_webhook_events.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["integration_id"], ["whatsapp_integrations.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["reviewed_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["attachment_id"], ["attachments.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("storage_key"),
        sa.UniqueConstraint("attachment_id"),
        sa.UniqueConstraint(
            "tenant_id", "provider_media_id", name="uq_whatsapp_media_provider_id"
        ),
        sa.UniqueConstraint("tenant_id", "id", name="uq_whatsapp_media_tenant_id_id"),
    )
    for column in (
        "tenant_id",
        "conversation_id",
        "message_id",
        "webhook_event_id",
        "integration_id",
        "provider_media_id",
        "provider_message_id",
        "media_type",
        "status",
        "sha256",
        "scan_status",
        "analysis_status",
        "review_status",
        "reviewed_by_id",
        "request_id",
        "attachment_id",
        "error_code",
        "created_by_id",
        "retention_until",
        "created_at",
    ):
        op.create_index(f"ix_whatsapp_media_assets_{column}", "whatsapp_media_assets", [column])


def downgrade():
    op.drop_table("whatsapp_media_assets")
