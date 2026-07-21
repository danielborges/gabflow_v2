"""channel messages

Revision ID: d6e7f8a9b104
Revises: c5d6e7f8a903
Create Date: 2026-07-21 13:20:00
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "d6e7f8a9b104"
down_revision = "c5d6e7f8a903"
branch_labels = None
depends_on = None


def upgrade():
    channel_message_status = sa.Enum(
        "RECEBIDA",
        "CONVERTIDA",
        "IGNORADA",
        name="channel_message_status",
    )
    op.create_table(
        "channel_messages",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column(
            "channel",
            postgresql.ENUM(
                "PRESENCIAL",
                "TELEFONE",
                "WHATSAPP",
                "EMAIL",
                "FORMULARIO",
                "REDE_SOCIAL",
                "VISITA",
                name="request_source",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("status", channel_message_status, nullable=False),
        sa.Column("sender_name", sa.String(length=180), nullable=True),
        sa.Column("sender_contact", sa.String(length=254), nullable=True),
        sa.Column("subject", sa.String(length=180), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("external_id", sa.String(length=160), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("request_id", sa.Uuid(), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reviewed_by_id", sa.Uuid(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["request_id"], ["service_requests.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["reviewed_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_channel_messages_tenant_id", "channel_messages", ["tenant_id"])
    op.create_index("ix_channel_messages_channel", "channel_messages", ["channel"])
    op.create_index("ix_channel_messages_status", "channel_messages", ["status"])
    op.create_index("ix_channel_messages_external_id", "channel_messages", ["external_id"])
    op.create_index("ix_channel_messages_request_id", "channel_messages", ["request_id"])
    op.create_index("ix_channel_messages_received_at", "channel_messages", ["received_at"])
    op.create_index("ix_channel_messages_reviewed_by_id", "channel_messages", ["reviewed_by_id"])


def downgrade():
    op.drop_index("ix_channel_messages_reviewed_by_id", table_name="channel_messages")
    op.drop_index("ix_channel_messages_received_at", table_name="channel_messages")
    op.drop_index("ix_channel_messages_request_id", table_name="channel_messages")
    op.drop_index("ix_channel_messages_external_id", table_name="channel_messages")
    op.drop_index("ix_channel_messages_status", table_name="channel_messages")
    op.drop_index("ix_channel_messages_channel", table_name="channel_messages")
    op.drop_index("ix_channel_messages_tenant_id", table_name="channel_messages")
    op.drop_table("channel_messages")
    sa.Enum(name="channel_message_status").drop(op.get_bind(), checkfirst=True)
