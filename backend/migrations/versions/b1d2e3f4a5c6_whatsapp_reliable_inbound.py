"""Add reliable WhatsApp webhook inbox.

Revision ID: b1d2e3f4a5c6
Revises: a0c1e2f3b4d5
"""

import sqlalchemy as sa
from alembic import op

revision = "b1d2e3f4a5c6"
down_revision = "a0c1e2f3b4d5"
branch_labels = None
depends_on = None


webhook_status = sa.Enum(
    "RECEIVED",
    "QUEUED",
    "PROCESSING",
    "PROCESSED",
    "QUARANTINED",
    "FAILED",
    name="whatsapp_webhook_event_status",
)


def upgrade():
    op.create_table(
        "whatsapp_webhook_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("provider_event_key", sa.String(255), nullable=False),
        sa.Column("correlation_id", sa.String(64), nullable=False),
        sa.Column("tenant_id", sa.Uuid()),
        sa.Column("integration_id", sa.Uuid()),
        sa.Column("phone_number_id", sa.String(80)),
        sa.Column("provider_message_id", sa.String(160)),
        sa.Column("event_type", sa.String(80), nullable=False),
        sa.Column("payload_hash", sa.String(64), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("status", webhook_status, nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("quarantine_reason", sa.String(120)),
        sa.Column("last_error_code", sa.String(120)),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("queued_at", sa.DateTime(timezone=True)),
        sa.Column("processing_started_at", sa.DateTime(timezone=True)),
        sa.Column("processed_at", sa.DateTime(timezone=True)),
        sa.Column("retention_until", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload_redacted_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["integration_id"], ["whatsapp_integrations.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "provider_event_key", name="uq_whatsapp_webhook_provider_event"
        ),
    )
    for column in (
        "correlation_id",
        "tenant_id",
        "integration_id",
        "phone_number_id",
        "provider_message_id",
        "event_type",
        "payload_hash",
        "status",
        "quarantine_reason",
        "received_at",
        "processed_at",
        "retention_until",
        "payload_redacted_at",
    ):
        op.create_index(
            f"ix_whatsapp_webhook_events_{column}",
            "whatsapp_webhook_events",
            [column],
        )
    op.create_index(
        "ix_whatsapp_webhook_status_received",
        "whatsapp_webhook_events",
        ["status", "received_at"],
    )


def downgrade():
    op.drop_table("whatsapp_webhook_events")
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        webhook_status.drop(bind, checkfirst=True)
