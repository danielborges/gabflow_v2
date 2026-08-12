"""Add WhatsApp privacy, citizen and request flow.

Revision ID: d3f4a5b6c7e8
Revises: c2e3f4a5b6d7
"""

import base64
import secrets

import sqlalchemy as sa
from alembic import op

revision = "d3f4a5b6c7e8"
down_revision = "c2e3f4a5b6d7"
branch_labels = None
depends_on = None


def _public_protocol() -> str:
    token = base64.b32encode(secrets.token_bytes(10)).decode("ascii").rstrip("=")
    return f"GFW-{token}"


def upgrade():
    op.add_column("service_requests", sa.Column("public_protocol", sa.String(32)))
    bind = op.get_bind()
    requests = sa.table(
        "service_requests",
        sa.column("id", sa.Uuid()),
        sa.column("public_protocol", sa.String(32)),
    )
    for request_id in bind.execute(sa.select(requests.c.id)).scalars():
        bind.execute(
            requests.update()
            .where(requests.c.id == request_id)
            .values(public_protocol=_public_protocol())
        )
    op.alter_column("service_requests", "public_protocol", nullable=False)
    op.create_index(
        "ix_service_requests_public_protocol",
        "service_requests",
        ["public_protocol"],
    )
    op.create_unique_constraint(
        "uq_service_requests_tenant_public_protocol",
        "service_requests",
        ["tenant_id", "public_protocol"],
    )
    op.create_unique_constraint(
        "uq_service_requests_tenant_id_id",
        "service_requests",
        ["tenant_id", "id"],
    )

    op.create_table(
        "whatsapp_privacy_records",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("contact_id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("purpose", sa.String(80), nullable=False),
        sa.Column("legal_basis", sa.String(120), nullable=False),
        sa.Column("notice_version", sa.String(40), nullable=False),
        sa.Column("action", sa.String(40), nullable=False),
        sa.Column("consent_required", sa.Boolean(), nullable=False),
        sa.Column("granted", sa.Boolean()),
        sa.Column("evidence_hash", sa.String(64), nullable=False),
        sa.Column("provider_message_id", sa.String(160)),
        sa.Column("recorded_by_id", sa.Uuid()),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id", "contact_id"],
            ["whatsapp_contacts.tenant_id", "whatsapp_contacts.id"],
            ondelete="RESTRICT",
            name="fk_whatsapp_privacy_tenant_contact",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "conversation_id"],
            ["whatsapp_conversations.tenant_id", "whatsapp_conversations.id"],
            ondelete="CASCADE",
            name="fk_whatsapp_privacy_tenant_conversation",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "recorded_by_id"],
            ["users.tenant_id", "users.id"],
            ondelete="RESTRICT",
            name="fk_whatsapp_privacy_tenant_actor",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "conversation_id",
            "notice_version",
            "action",
            name="uq_whatsapp_privacy_conversation_action",
        ),
    )
    _indexes(
        "whatsapp_privacy_records",
        (
            "tenant_id",
            "contact_id",
            "conversation_id",
            "action",
            "provider_message_id",
            "recorded_by_id",
            "occurred_at",
        ),
    )

    op.create_table(
        "whatsapp_request_drafts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("citizen_id", sa.Uuid(), nullable=False),
        sa.Column("category_id", sa.Uuid()),
        sa.Column("title", sa.String(180)),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("address", sa.String(500)),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("idempotency_key", sa.String(120)),
        sa.Column("service_request_id", sa.Uuid()),
        sa.Column("confirmed_at", sa.DateTime(timezone=True)),
        sa.Column("created_by_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id", "conversation_id"],
            ["whatsapp_conversations.tenant_id", "whatsapp_conversations.id"],
            ondelete="CASCADE",
            name="fk_whatsapp_draft_tenant_conversation",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "citizen_id"],
            ["citizens.tenant_id", "citizens.id"],
            ondelete="RESTRICT",
            name="fk_whatsapp_draft_tenant_citizen",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "service_request_id"],
            ["service_requests.tenant_id", "service_requests.id"],
            ondelete="RESTRICT",
            name="fk_whatsapp_draft_tenant_request",
        ),
        sa.ForeignKeyConstraint(["category_id"], ["request_categories.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "conversation_id", name="uq_whatsapp_draft_conversation"),
        sa.UniqueConstraint("tenant_id", "idempotency_key", name="uq_whatsapp_draft_idempotency"),
    )
    _indexes(
        "whatsapp_request_drafts",
        (
            "tenant_id",
            "conversation_id",
            "citizen_id",
            "category_id",
            "status",
            "idempotency_key",
            "service_request_id",
            "created_by_id",
            "created_at",
        ),
    )


def downgrade():
    op.drop_table("whatsapp_request_drafts")
    op.drop_table("whatsapp_privacy_records")
    op.drop_constraint("uq_service_requests_tenant_id_id", "service_requests", type_="unique")
    op.drop_constraint(
        "uq_service_requests_tenant_public_protocol",
        "service_requests",
        type_="unique",
    )
    op.drop_index("ix_service_requests_public_protocol", table_name="service_requests")
    op.drop_column("service_requests", "public_protocol")


def _indexes(table: str, columns: tuple[str, ...]) -> None:
    for column in columns:
        op.create_index(f"ix_{table}_{column}", table, [column])
