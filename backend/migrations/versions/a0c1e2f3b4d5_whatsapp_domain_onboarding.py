"""Add WhatsApp domain and Meta onboarding sessions.

Revision ID: a0c1e2f3b4d5
Revises: z9d7e4f1a3b5, a5d9f1b3c7e2
"""

import sqlalchemy as sa
from alembic import op

revision = "a0c1e2f3b4d5"
down_revision = ("z9d7e4f1a3b5", "a5d9f1b3c7e2")
branch_labels = None
depends_on = None


integration_status = sa.Enum(
    "PENDING",
    "ACTIVE",
    "DEGRADED",
    "SUSPENDED",
    "DISCONNECTED",
    "REVOKED",
    name="whatsapp_integration_status",
)
onboarding_status = sa.Enum(
    "PENDING",
    "PROCESSING",
    "COMPLETED",
    "FAILED",
    "EXPIRED",
    name="whatsapp_onboarding_status",
)


def upgrade():
    op.create_table(
        "whatsapp_integrations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("business_portfolio_id", sa.String(80), nullable=False),
        sa.Column("waba_id", sa.String(80), nullable=False),
        sa.Column("phone_number_id", sa.String(80), nullable=False),
        sa.Column("display_phone", sa.String(40)),
        sa.Column("display_name", sa.String(160)),
        sa.Column("status", integration_status, nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("token_secret_ref", sa.String(500), nullable=False),
        sa.Column("webhook_subscribed_at", sa.DateTime(timezone=True)),
        sa.Column("connected_at", sa.DateTime(timezone=True)),
        sa.Column("disconnected_at", sa.DateTime(timezone=True)),
        sa.Column("last_health_check_at", sa.DateTime(timezone=True)),
        sa.Column("last_health_error", sa.String(500)),
        sa.Column("created_by_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "version", name="uq_whatsapp_integration_tenant_version"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_whatsapp_integrations_tenant_id_id"),
    )
    for column in (
        "tenant_id",
        "business_portfolio_id",
        "waba_id",
        "phone_number_id",
        "status",
        "connected_at",
        "disconnected_at",
        "created_at",
    ):
        op.create_index(f"ix_whatsapp_integrations_{column}", "whatsapp_integrations", [column])
    op.create_index(
        "uq_whatsapp_active_phone_number",
        "whatsapp_integrations",
        ["phone_number_id"],
        unique=True,
        postgresql_where=sa.text("status = 'ACTIVE'"),
        sqlite_where=sa.text("status = 'ACTIVE'"),
    )

    op.create_table(
        "whatsapp_onboarding_sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("initiated_by_id", sa.Uuid(), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("state_nonce", sa.String(128)),
        sa.Column("state_hash", sa.String(64), nullable=False),
        sa.Column("status", onboarding_status, nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True)),
        sa.Column("failure_code", sa.String(80)),
        sa.Column("integration_id", sa.Uuid()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "initiated_by_id"],
            ["users.tenant_id", "users.id"],
            ondelete="RESTRICT",
            name="fk_whatsapp_onboarding_tenant_user",
        ),
        sa.ForeignKeyConstraint(
            ["integration_id"], ["whatsapp_integrations.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("state_hash"),
        sa.UniqueConstraint(
            "tenant_id", "idempotency_key", name="uq_whatsapp_onboarding_idempotency"
        ),
        sa.UniqueConstraint("tenant_id", "id", name="uq_whatsapp_onboarding_tenant_id_id"),
    )
    for column in (
        "tenant_id",
        "initiated_by_id",
        "status",
        "expires_at",
        "integration_id",
        "created_at",
    ):
        op.create_index(
            f"ix_whatsapp_onboarding_sessions_{column}",
            "whatsapp_onboarding_sessions",
            [column],
        )


def downgrade():
    op.drop_table("whatsapp_onboarding_sessions")
    op.drop_table("whatsapp_integrations")
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        onboarding_status.drop(bind, checkfirst=True)
        integration_status.drop(bind, checkfirst=True)
