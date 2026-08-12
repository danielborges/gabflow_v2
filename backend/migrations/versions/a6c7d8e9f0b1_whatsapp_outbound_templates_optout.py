"""Add WhatsApp outbound policy, templates and delivery tracking.

Revision ID: a6c7d8e9f0b1
Revises: f5b6c7d8e9a0
"""

import sqlalchemy as sa
from alembic import op

revision = "a6c7d8e9f0b1"
down_revision = "f5b6c7d8e9a0"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "whatsapp_message_templates",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("integration_id", sa.Uuid(), nullable=False),
        sa.Column("provider_template_id", sa.String(160)),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("language", sa.String(20), nullable=False),
        sa.Column("category", sa.String(30), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("variables", sa.JSON(), nullable=False),
        sa.Column("provider_components", sa.JSON(), nullable=False),
        sa.Column("rejection_reason", sa.String(500)),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("created_by_id", sa.Uuid(), nullable=False),
        sa.Column("synced_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "category IN ('UTILITY', 'AUTHENTICATION', 'MARKETING')",
            name="ck_whatsapp_template_category",
        ),
        sa.CheckConstraint(
            "status IN ('DRAFT', 'PENDING', 'APPROVED', 'REJECTED', 'PAUSED', 'DISABLED')",
            name="ck_whatsapp_template_status",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "integration_id"],
            ["whatsapp_integrations.tenant_id", "whatsapp_integrations.id"],
            ondelete="RESTRICT",
            name="fk_whatsapp_template_tenant_integration",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "created_by_id"],
            ["users.tenant_id", "users.id"],
            ondelete="RESTRICT",
            name="fk_whatsapp_template_tenant_creator",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id", "name", "language", "version", name="uq_whatsapp_template_version"
        ),
        sa.UniqueConstraint("tenant_id", "id", name="uq_whatsapp_templates_tenant_id_id"),
    )
    for column in (
        "tenant_id",
        "integration_id",
        "provider_template_id",
        "name",
        "language",
        "category",
        "status",
        "active",
        "created_by_id",
        "synced_at",
        "created_at",
    ):
        op.create_index(
            f"ix_whatsapp_message_templates_{column}", "whatsapp_message_templates", [column]
        )

    with op.batch_alter_table("whatsapp_messages") as batch:
        batch.add_column(sa.Column("outbound_content", sa.Text()))
        batch.add_column(sa.Column("template_id", sa.Uuid()))
        batch.add_column(
            sa.Column("template_parameters", sa.JSON(), nullable=False, server_default="[]")
        )
        batch.add_column(sa.Column("idempotency_key", sa.String(128)))
        batch.add_column(sa.Column("requested_by_id", sa.Uuid()))
        batch.add_column(sa.Column("policy_decision", sa.String(40)))
        batch.add_column(
            sa.Column(
                "opt_out_confirmation", sa.Boolean(), nullable=False, server_default=sa.false()
            )
        )
        batch.add_column(sa.Column("correlation_id", sa.String(64)))
        batch.add_column(sa.Column("error_code", sa.String(120)))
        batch.add_column(sa.Column("error", sa.String(1000)))
        batch.add_column(sa.Column("sent_at", sa.DateTime(timezone=True)))
        batch.add_column(sa.Column("delivered_at", sa.DateTime(timezone=True)))
        batch.add_column(sa.Column("read_at", sa.DateTime(timezone=True)))
        batch.add_column(sa.Column("failed_at", sa.DateTime(timezone=True)))
        batch.create_foreign_key(
            "fk_whatsapp_message_tenant_template",
            "whatsapp_message_templates",
            ["tenant_id", "template_id"],
            ["tenant_id", "id"],
            ondelete="RESTRICT",
        )
        batch.create_foreign_key(
            "fk_whatsapp_message_tenant_requester",
            "users",
            ["tenant_id", "requested_by_id"],
            ["tenant_id", "id"],
            ondelete="RESTRICT",
        )
        batch.create_unique_constraint(
            "uq_whatsapp_message_idempotency", ["tenant_id", "idempotency_key"]
        )
        for column in (
            "template_id",
            "idempotency_key",
            "requested_by_id",
            "policy_decision",
            "correlation_id",
            "error_code",
        ):
            batch.create_index(f"ix_whatsapp_messages_{column}", [column])
        batch.alter_column("template_parameters", server_default=None)
        batch.alter_column("opt_out_confirmation", server_default=None)


def downgrade():
    with op.batch_alter_table("whatsapp_messages") as batch:
        for column in (
            "error_code",
            "correlation_id",
            "policy_decision",
            "requested_by_id",
            "idempotency_key",
            "template_id",
        ):
            batch.drop_index(f"ix_whatsapp_messages_{column}")
        batch.drop_constraint("uq_whatsapp_message_idempotency", type_="unique")
        batch.drop_constraint("fk_whatsapp_message_tenant_requester", type_="foreignkey")
        batch.drop_constraint("fk_whatsapp_message_tenant_template", type_="foreignkey")
        for column in (
            "failed_at",
            "read_at",
            "delivered_at",
            "sent_at",
            "error",
            "error_code",
            "correlation_id",
            "opt_out_confirmation",
            "policy_decision",
            "requested_by_id",
            "idempotency_key",
            "template_parameters",
            "template_id",
            "outbound_content",
        ):
            batch.drop_column(column)
    op.drop_table("whatsapp_message_templates")
