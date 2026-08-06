"""Add assisted registration operations and tenant settings.

Revision ID: f5d0b7c9e1a3
Revises: e4c9a6b8d0f2
"""

import os

import sqlalchemy as sa
from alembic import op

revision = "f5d0b7c9e1a3"
down_revision = "e4c9a6b8d0f2"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "channel_messages", sa.Column("redacted_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.create_index("ix_channel_messages_redacted_at", "channel_messages", ["redacted_at"])
    op.add_column("channel_identity_reviews", sa.Column("assigned_to_id", sa.Uuid(), nullable=True))
    op.add_column(
        "channel_identity_reviews", sa.Column("due_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "channel_identity_reviews", sa.Column("decision_type", sa.String(40), nullable=True)
    )
    op.add_column(
        "channel_identity_reviews",
        sa.Column("reopened_count", sa.Integer(), server_default="0", nullable=False),
    )
    op.create_foreign_key(
        "fk_channel_identity_reviews_tenant_assignee",
        "channel_identity_reviews",
        "users",
        ["tenant_id", "assigned_to_id"],
        ["tenant_id", "id"],
        ondelete="RESTRICT",
    )
    for column in ("assigned_to_id", "due_at", "decision_type"):
        op.create_index(
            f"ix_channel_identity_reviews_{column}", "channel_identity_reviews", [column]
        )

    op.create_table(
        "channel_assisted_settings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("default_legal_basis", sa.String(120), nullable=True),
        sa.Column("sla_hours", sa.Integer(), nullable=False),
        sa.Column("retention_days", sa.Integer(), nullable=False),
        sa.Column("updated_by_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "updated_by_id"],
            ["users.tenant_id", "users.id"],
            name="fk_channel_assisted_settings_tenant_updater",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", name="uq_channel_assisted_settings_tenant"),
    )
    op.create_index(
        "ix_channel_assisted_settings_tenant_id", "channel_assisted_settings", ["tenant_id"]
    )
    op.create_index(
        "ix_channel_assisted_settings_updated_by_id",
        "channel_assisted_settings",
        ["updated_by_id"],
    )

    if op.get_bind().dialect.name == "postgresql":
        tenant = "current_setting('app.tenant_id', true)::uuid"
        op.execute("ALTER TABLE channel_assisted_settings ENABLE ROW LEVEL SECURITY")
        op.execute("ALTER TABLE channel_assisted_settings FORCE ROW LEVEL SECURITY")
        op.execute(
            "CREATE POLICY channel_assisted_settings_tenant_isolation "
            "ON channel_assisted_settings FOR ALL "
            f"USING (tenant_id = {tenant}) WITH CHECK (tenant_id = {tenant})"
        )
        roles = {
            os.getenv("APP_DB_USER", "gabflow_app"),
            os.getenv("WORKER_DB_USER", "gabflow_worker"),
        }
        available = {
            row[0]
            for row in op.get_bind().execute(
                sa.text("SELECT rolname FROM pg_roles WHERE rolname = ANY(:roles)"),
                {"roles": list(roles)},
            )
        }
        for role in roles & available:
            op.execute(
                sa.text(
                    f'GRANT SELECT, INSERT, UPDATE ON TABLE channel_assisted_settings TO "{role}"'
                )
            )


def downgrade():
    op.drop_table("channel_assisted_settings")
    for column in ("decision_type", "due_at", "assigned_to_id"):
        op.drop_index(
            f"ix_channel_identity_reviews_{column}", table_name="channel_identity_reviews"
        )
    op.drop_constraint(
        "fk_channel_identity_reviews_tenant_assignee",
        "channel_identity_reviews",
        type_="foreignkey",
    )
    op.drop_column("channel_identity_reviews", "reopened_count")
    op.drop_column("channel_identity_reviews", "decision_type")
    op.drop_column("channel_identity_reviews", "due_at")
    op.drop_column("channel_identity_reviews", "assigned_to_id")
    op.drop_index("ix_channel_messages_redacted_at", table_name="channel_messages")
    op.drop_column("channel_messages", "redacted_at")
