"""Add WhatsApp conversations and inbox v2 domain.

Revision ID: c2e3f4a5b6d7
Revises: b1d2e3f4a5c6
"""

import sqlalchemy as sa
from alembic import op

revision = "c2e3f4a5b6d7"
down_revision = "b1d2e3f4a5c6"
branch_labels = None
depends_on = None


contact_opt_status = sa.Enum("ACTIVE", "OPTED_OUT", "BLOCKED", name="whatsapp_contact_opt_status")
conversation_state = sa.Enum(
    "NEW",
    "PRIVACY_NOTICE",
    "IDENTIFICATION",
    "INTENT",
    "DATA_COLLECTION",
    "REVIEW",
    "PROTOCOL_CREATED",
    "FOLLOW_UP",
    "HUMAN_HANDOFF",
    "OPTED_OUT",
    "BLOCKED",
    "ERROR_RECOVERY",
    "CLOSED",
    name="whatsapp_conversation_state",
)
conversation_mode = sa.Enum("BOT", "HUMAN", name="whatsapp_conversation_mode")
message_direction = sa.Enum("INBOUND", "OUTBOUND", name="whatsapp_message_direction")
message_status = sa.Enum(
    "RECEIVED",
    "QUEUED",
    "SENT",
    "DELIVERED",
    "READ",
    "FAILED",
    name="whatsapp_message_status",
)


def upgrade():
    op.create_table(
        "whatsapp_contacts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("wa_user_id", sa.String(80), nullable=False),
        sa.Column("citizen_id", sa.Uuid()),
        sa.Column("profile_name", sa.String(180)),
        sa.Column("opt_status", contact_opt_status, nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("opted_out_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "citizen_id"],
            ["citizens.tenant_id", "citizens.id"],
            ondelete="RESTRICT",
            name="fk_whatsapp_contact_tenant_citizen",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_whatsapp_contacts_tenant_id_id"),
        sa.UniqueConstraint("tenant_id", "wa_user_id", name="uq_whatsapp_contact_tenant_user"),
    )
    _indexes(
        "whatsapp_contacts",
        ("tenant_id", "wa_user_id", "citizen_id", "opt_status", "last_seen_at"),
    )

    op.create_table(
        "whatsapp_conversations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("contact_id", sa.Uuid(), nullable=False),
        sa.Column("integration_id", sa.Uuid(), nullable=False),
        sa.Column("state", conversation_state, nullable=False),
        sa.Column("mode", conversation_mode, nullable=False),
        sa.Column("assigned_user_id", sa.Uuid()),
        sa.Column("window_expires_at", sa.DateTime(timezone=True)),
        sa.Column("last_message_at", sa.DateTime(timezone=True)),
        sa.Column("last_read_at", sa.DateTime(timezone=True)),
        sa.Column("unread_count", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id", "contact_id"],
            ["whatsapp_contacts.tenant_id", "whatsapp_contacts.id"],
            ondelete="RESTRICT",
            name="fk_whatsapp_conversation_tenant_contact",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "integration_id"],
            ["whatsapp_integrations.tenant_id", "whatsapp_integrations.id"],
            ondelete="RESTRICT",
            name="fk_whatsapp_conversation_tenant_integration",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "assigned_user_id"],
            ["users.tenant_id", "users.id"],
            ondelete="RESTRICT",
            name="fk_whatsapp_conversation_tenant_assignee",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "contact_id", name="uq_whatsapp_conversation_contact"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_whatsapp_conversations_tenant_id_id"),
    )
    _indexes(
        "whatsapp_conversations",
        (
            "tenant_id",
            "contact_id",
            "integration_id",
            "state",
            "mode",
            "assigned_user_id",
            "window_expires_at",
            "last_message_at",
            "unread_count",
            "created_at",
        ),
    )

    op.create_table(
        "whatsapp_messages",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("channel_message_id", sa.Uuid()),
        sa.Column("provider_message_id", sa.String(160), nullable=False),
        sa.Column("direction", message_direction, nullable=False),
        sa.Column("message_type", sa.String(40), nullable=False),
        sa.Column("status", message_status, nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id", "conversation_id"],
            ["whatsapp_conversations.tenant_id", "whatsapp_conversations.id"],
            ondelete="CASCADE",
            name="fk_whatsapp_message_tenant_conversation",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "channel_message_id"],
            ["channel_messages.tenant_id", "channel_messages.id"],
            ondelete="RESTRICT",
            name="fk_whatsapp_message_tenant_channel_message",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_whatsapp_messages_tenant_id_id"),
        sa.UniqueConstraint(
            "tenant_id",
            "provider_message_id",
            "direction",
            name="uq_whatsapp_message_provider_direction",
        ),
        sa.UniqueConstraint("channel_message_id", name="uq_whatsapp_message_channel_message"),
    )
    _indexes(
        "whatsapp_messages",
        (
            "tenant_id",
            "conversation_id",
            "channel_message_id",
            "provider_message_id",
            "direction",
            "message_type",
            "status",
            "occurred_at",
        ),
    )

    op.create_table(
        "whatsapp_conversation_transitions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("from_state", conversation_state, nullable=False),
        sa.Column("to_state", conversation_state, nullable=False),
        sa.Column("actor_type", sa.String(30), nullable=False),
        sa.Column("actor_id", sa.Uuid()),
        sa.Column("origin", sa.String(40), nullable=False),
        sa.Column("reason", sa.String(500)),
        sa.Column("rule_version", sa.String(40), nullable=False),
        sa.Column("correlation_id", sa.String(64)),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id", "conversation_id"],
            ["whatsapp_conversations.tenant_id", "whatsapp_conversations.id"],
            ondelete="CASCADE",
            name="fk_whatsapp_transition_tenant_conversation",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "actor_id"],
            ["users.tenant_id", "users.id"],
            ondelete="RESTRICT",
            name="fk_whatsapp_transition_tenant_actor",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    _indexes(
        "whatsapp_conversation_transitions",
        ("tenant_id", "conversation_id", "to_state", "actor_id", "correlation_id", "occurred_at"),
    )


def downgrade():
    op.drop_table("whatsapp_conversation_transitions")
    op.drop_table("whatsapp_messages")
    op.drop_table("whatsapp_conversations")
    op.drop_table("whatsapp_contacts")
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        message_status.drop(bind, checkfirst=True)
        message_direction.drop(bind, checkfirst=True)
        conversation_mode.drop(bind, checkfirst=True)
        conversation_state.drop(bind, checkfirst=True)
        contact_opt_status.drop(bind, checkfirst=True)


def _indexes(table: str, columns: tuple[str, ...]) -> None:
    for column in columns:
        op.create_index(f"ix_{table}_{column}", table, [column])
