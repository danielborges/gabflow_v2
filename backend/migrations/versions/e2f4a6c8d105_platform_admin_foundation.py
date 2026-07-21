"""platform admin foundation

Revision ID: e2f4a6c8d105
Revises: d6e7f8a9b104
Create Date: 2026-07-21 14:45:00
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "e2f4a6c8d105"
down_revision = "d6e7f8a9b104"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("ALTER TYPE user_role ADD VALUE IF NOT EXISTS 'PLATFORM_ADMIN'")
        op.execute("ALTER TYPE tenant_status ADD VALUE IF NOT EXISTS 'SUSPENDED'")
        op.execute("ALTER TYPE tenant_status ADD VALUE IF NOT EXISTS 'CANCELLED'")

    contract_status = sa.Enum("TRIAL", "ACTIVE", "SUSPENDED", "CANCELLED", name="contract_status")
    platform_setting_type = sa.Enum(
        "PARAMETER",
        "GLOBAL_TEMPLATE",
        "INTEGRATION_PROVIDER",
        "FEATURE_FLAG",
        "SECURITY_POLICY",
        name="platform_setting_type",
    )
    contract_status.create(bind, checkfirst=True)
    platform_setting_type.create(bind, checkfirst=True)
    enum_type = postgresql.ENUM if bind.dialect.name == "postgresql" else sa.Enum
    enum_options = {"create_type": False} if bind.dialect.name == "postgresql" else {}
    contract_status_column = enum_type(
        "TRIAL", "ACTIVE", "SUSPENDED", "CANCELLED", name="contract_status", **enum_options
    )
    platform_setting_type_column = enum_type(
        "PARAMETER",
        "GLOBAL_TEMPLATE",
        "INTEGRATION_PROVIDER",
        "FEATURE_FLAG",
        "SECURITY_POLICY",
        name="platform_setting_type",
        **enum_options,
    )

    op.add_column("tenants", sa.Column("plan", sa.String(length=80), nullable=False, server_default="starter"))
    op.add_column(
        "tenants",
        sa.Column("contract_status", contract_status_column, nullable=False, server_default="TRIAL"),
    )
    op.add_column("tenants", sa.Column("user_limit", sa.Integer(), nullable=False, server_default="5"))
    op.add_column(
        "tenants",
        sa.Column("storage_limit_mb", sa.Integer(), nullable=False, server_default="1024"),
    )
    op.add_column("tenants", sa.Column("enabled_modules", sa.JSON(), nullable=False, server_default="[]"))
    op.add_column("tenants", sa.Column("contract_notes", sa.Text(), nullable=True))

    with op.batch_alter_table("users") as batch_op:
        batch_op.alter_column("tenant_id", existing_type=sa.Uuid(), nullable=True)

    with op.batch_alter_table("audit_logs") as batch_op:
        batch_op.alter_column("tenant_id", existing_type=sa.Uuid(), nullable=True)

    op.create_table(
        "platform_settings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("setting_type", platform_setting_type_column, nullable=False),
        sa.Column("key", sa.String(length=120), nullable=False),
        sa.Column("name", sa.String(length=180), nullable=False),
        sa.Column("value", sa.JSON(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("updated_by_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["updated_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("setting_type", "key"),
    )
    op.create_index("ix_platform_settings_setting_type", "platform_settings", ["setting_type"])
    op.create_index("ix_platform_settings_created_at", "platform_settings", ["created_at"])
    op.create_index("ix_platform_settings_updated_by_id", "platform_settings", ["updated_by_id"])

    op.create_table(
        "platform_support_accesses",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("requested_by", sa.String(length=180), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("authorized_by", sa.String(length=180), nullable=True),
        sa.Column("scope", sa.String(length=180), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("created_by_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_platform_support_accesses_tenant_id", "platform_support_accesses", ["tenant_id"])
    op.create_index(
        "ix_platform_support_accesses_created_by_id",
        "platform_support_accesses",
        ["created_by_id"],
    )
    op.create_index(
        "ix_platform_support_accesses_created_at",
        "platform_support_accesses",
        ["created_at"],
    )


def downgrade():
    op.drop_index("ix_platform_support_accesses_created_at", table_name="platform_support_accesses")
    op.drop_index("ix_platform_support_accesses_created_by_id", table_name="platform_support_accesses")
    op.drop_index("ix_platform_support_accesses_tenant_id", table_name="platform_support_accesses")
    op.drop_table("platform_support_accesses")

    op.drop_index("ix_platform_settings_updated_by_id", table_name="platform_settings")
    op.drop_index("ix_platform_settings_created_at", table_name="platform_settings")
    op.drop_index("ix_platform_settings_setting_type", table_name="platform_settings")
    op.drop_table("platform_settings")

    with op.batch_alter_table("audit_logs") as batch_op:
        batch_op.alter_column("tenant_id", existing_type=sa.Uuid(), nullable=False)
    with op.batch_alter_table("users") as batch_op:
        batch_op.alter_column("tenant_id", existing_type=sa.Uuid(), nullable=False)

    op.drop_column("tenants", "contract_notes")
    op.drop_column("tenants", "enabled_modules")
    op.drop_column("tenants", "storage_limit_mb")
    op.drop_column("tenants", "user_limit")
    op.drop_column("tenants", "contract_status")
    op.drop_column("tenants", "plan")

    bind = op.get_bind()
    sa.Enum(name="platform_setting_type").drop(bind, checkfirst=True)
    sa.Enum(name="contract_status").drop(bind, checkfirst=True)
