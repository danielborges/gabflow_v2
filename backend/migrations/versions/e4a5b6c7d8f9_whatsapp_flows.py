"""Add versioned WhatsApp Flows and submissions.

Revision ID: e4a5b6c7d8f9
Revises: d3f4a5b6c7e8
"""

import sqlalchemy as sa
from alembic import op

revision = "e4a5b6c7d8f9"
down_revision = "d3f4a5b6c7e8"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("whatsapp_request_drafts", sa.Column("declared_urgency", sa.String(20)))

    op.create_table(
        "whatsapp_flow_definitions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("flow_key", sa.String(60), nullable=False),
        sa.Column("display_name", sa.String(160), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("environment", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("meta_flow_id", sa.String(100)),
        sa.Column("schema_json", sa.JSON(), nullable=False),
        sa.Column("definition_json", sa.JSON(), nullable=False),
        sa.Column("schema_hash", sa.String(64), nullable=False),
        sa.Column("created_by_id", sa.Uuid(), nullable=False),
        sa.Column("activated_at", sa.DateTime(timezone=True)),
        sa.Column("retired_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "created_by_id"],
            ["users.tenant_id", "users.id"],
            ondelete="RESTRICT",
            name="fk_whatsapp_flow_definition_tenant_creator",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "flow_key",
            "environment",
            "version",
            name="uq_whatsapp_flow_key_environment_version",
        ),
        sa.UniqueConstraint("tenant_id", "meta_flow_id", name="uq_whatsapp_flow_meta_id"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_whatsapp_flow_definitions_tenant_id_id"),
    )
    _indexes(
        "whatsapp_flow_definitions",
        (
            "tenant_id",
            "flow_key",
            "environment",
            "status",
            "meta_flow_id",
            "schema_hash",
            "created_by_id",
            "created_at",
        ),
    )

    op.create_table(
        "whatsapp_flow_sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("definition_id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("initiated_by_id", sa.Uuid(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id", "definition_id"],
            ["whatsapp_flow_definitions.tenant_id", "whatsapp_flow_definitions.id"],
            ondelete="RESTRICT",
            name="fk_whatsapp_flow_session_tenant_definition",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "conversation_id"],
            ["whatsapp_conversations.tenant_id", "whatsapp_conversations.id"],
            ondelete="CASCADE",
            name="fk_whatsapp_flow_session_tenant_conversation",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "initiated_by_id"],
            ["users.tenant_id", "users.id"],
            ondelete="RESTRICT",
            name="fk_whatsapp_flow_session_tenant_actor",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash", name="uq_whatsapp_flow_session_token_hash"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_whatsapp_flow_sessions_tenant_id_id"),
    )
    _indexes(
        "whatsapp_flow_sessions",
        (
            "tenant_id",
            "definition_id",
            "conversation_id",
            "token_hash",
            "status",
            "initiated_by_id",
            "expires_at",
            "created_at",
        ),
    )

    op.create_table(
        "whatsapp_flow_submissions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("definition_id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("webhook_event_id", sa.Uuid(), nullable=False),
        sa.Column("provider_message_id", sa.String(160), nullable=False),
        sa.Column("response_hash", sa.String(64), nullable=False),
        sa.Column("values", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("error_code", sa.String(80)),
        sa.Column("request_id", sa.Uuid()),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(
            ["tenant_id", "session_id"],
            ["whatsapp_flow_sessions.tenant_id", "whatsapp_flow_sessions.id"],
            ondelete="RESTRICT",
            name="fk_whatsapp_flow_submission_tenant_session",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "definition_id"],
            ["whatsapp_flow_definitions.tenant_id", "whatsapp_flow_definitions.id"],
            ondelete="RESTRICT",
            name="fk_whatsapp_flow_submission_tenant_definition",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "conversation_id"],
            ["whatsapp_conversations.tenant_id", "whatsapp_conversations.id"],
            ondelete="CASCADE",
            name="fk_whatsapp_flow_submission_tenant_conversation",
        ),
        sa.ForeignKeyConstraint(
            ["webhook_event_id"], ["whatsapp_webhook_events.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["request_id"], ["service_requests.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "provider_message_id",
            name="uq_whatsapp_flow_submission_provider_message",
        ),
        sa.UniqueConstraint(
            "tenant_id", "response_hash", name="uq_whatsapp_flow_submission_response"
        ),
    )
    _indexes(
        "whatsapp_flow_submissions",
        (
            "tenant_id",
            "session_id",
            "definition_id",
            "conversation_id",
            "webhook_event_id",
            "provider_message_id",
            "response_hash",
            "status",
            "error_code",
            "request_id",
            "received_at",
        ),
    )


def downgrade():
    op.drop_table("whatsapp_flow_submissions")
    op.drop_table("whatsapp_flow_sessions")
    op.drop_table("whatsapp_flow_definitions")
    op.drop_column("whatsapp_request_drafts", "declared_urgency")


def _indexes(table: str, columns: tuple[str, ...]) -> None:
    for column in columns:
        op.create_index(f"ix_{table}_{column}", table, [column])
