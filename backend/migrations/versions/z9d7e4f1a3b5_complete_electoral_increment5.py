"""Complete electoral Increment 5 crosswalks and alert deliveries.

Revision ID: z9d7e4f1a3b5
Revises: y8c6d3e0f2a4
"""

import os

import sqlalchemy as sa
from alembic import op

revision = "z9d7e4f1a3b5"
down_revision = "y8c6d3e0f2a4"
branch_labels = None
depends_on = None

TABLES = (
    "electoral_operational_territory_links",
    "electoral_alert_deliveries",
)


def upgrade():
    op.create_table(
        TABLES[0],
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("mandate_id", sa.Uuid(), nullable=False),
        sa.Column("territory_id", sa.Uuid(), nullable=False),
        sa.Column("electoral_territory_id", sa.Uuid(), nullable=False),
        sa.Column("method", sa.String(30), nullable=False),
        sa.Column("notes", sa.String(500)),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("reviewed_by_id", sa.Uuid(), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "method IN ('OFFICIAL', 'HUMAN_REVIEW')", name="ck_electoral_territory_links_method"
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "mandate_id"],
            ["mandates.tenant_id", "mandates.id"],
            ondelete="CASCADE",
            name="fk_electoral_territory_links_tenant_mandate",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "territory_id"],
            ["territories.tenant_id", "territories.id"],
            ondelete="CASCADE",
            name="fk_electoral_territory_links_tenant_territory",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "reviewed_by_id"],
            ["users.tenant_id", "users.id"],
            ondelete="RESTRICT",
            name="fk_electoral_territory_links_tenant_reviewer",
        ),
        sa.ForeignKeyConstraint(
            ["electoral_territory_id"], ["electoral_territories.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "mandate_id",
            "territory_id",
            "electoral_territory_id",
            name="uq_electoral_operational_territory_link",
        ),
        sa.UniqueConstraint("tenant_id", "id", name="uq_electoral_territory_links_tenant_id_id"),
    )
    op.create_table(
        TABLES[1],
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("mandate_id", sa.Uuid(), nullable=False),
        sa.Column("preference_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("snapshot_id", sa.Uuid(), nullable=False),
        sa.Column("event_key", sa.String(64), nullable=False),
        sa.Column("alert_type", sa.String(40), nullable=False),
        sa.Column("channel", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("scheduled_for", sa.DateTime(timezone=True), nullable=False),
        sa.Column("delivered_at", sa.DateTime(timezone=True)),
        sa.Column("provider_message_id", sa.String(160)),
        sa.Column("error", sa.String(1000)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "channel IN ('IN_APP', 'EMAIL')", name="ck_electoral_alert_delivery_channel"
        ),
        sa.CheckConstraint(
            "status IN ('PENDING', 'DELIVERED', 'FAILED')",
            name="ck_electoral_alert_delivery_status",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "preference_id"],
            ["electoral_alert_preferences.tenant_id", "electoral_alert_preferences.id"],
            ondelete="CASCADE",
            name="fk_electoral_alert_deliveries_tenant_preference",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "snapshot_id"],
            ["electoral_mandate_snapshots.tenant_id", "electoral_mandate_snapshots.id"],
            ondelete="CASCADE",
            name="fk_electoral_alert_deliveries_tenant_snapshot",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "user_id"],
            ["users.tenant_id", "users.id"],
            ondelete="CASCADE",
            name="fk_electoral_alert_deliveries_tenant_user",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "preference_id",
            "snapshot_id",
            "event_key",
            "channel",
            name="uq_electoral_alert_delivery_event",
        ),
        sa.UniqueConstraint("tenant_id", "id", name="uq_electoral_alert_deliveries_tenant_id_id"),
    )
    indexes = {
        TABLES[0]: (
            "tenant_id",
            "mandate_id",
            "territory_id",
            "electoral_territory_id",
            "active",
            "reviewed_by_id",
        ),
        TABLES[1]: (
            "tenant_id",
            "mandate_id",
            "preference_id",
            "user_id",
            "snapshot_id",
            "alert_type",
            "channel",
            "status",
            "scheduled_for",
            "created_at",
        ),
    }
    for table, columns in indexes.items():
        for column in columns:
            op.create_index(f"ix_{table}_{column}", table, [column])
    if op.get_bind().dialect.name == "postgresql":
        tenant = "NULLIF(current_setting('app.tenant_id', true), '')::uuid"
        for table in TABLES:
            op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
            op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
            op.execute(
                f"CREATE POLICY {table}_tenant_isolation ON {table} FOR ALL USING (tenant_id = {tenant}) WITH CHECK (tenant_id = {tenant})"
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
            for table in TABLES:
                op.execute(
                    sa.text(f'GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE {table} TO "{role}"')
                )


def downgrade():
    for table in reversed(TABLES):
        op.drop_table(table)
