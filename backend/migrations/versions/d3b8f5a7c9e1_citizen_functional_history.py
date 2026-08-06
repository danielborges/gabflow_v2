"""Add tenant-scoped citizen functional history.

Revision ID: d3b8f5a7c9e1
Revises: c2a7e4f6b8d0
"""

import os

import sqlalchemy as sa
from alembic import op

revision = "d3b8f5a7c9e1"
down_revision = "c2a7e4f6b8d0"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "citizen_history",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("citizen_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("action", sa.String(60), nullable=False),
        sa.Column("changed_fields", sa.JSON(), nullable=False),
        sa.Column("metadata_summary", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id", "citizen_id"],
            ["citizens.tenant_id", "citizens.id"],
            name="fk_citizen_history_tenant_citizen",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "user_id"],
            ["users.tenant_id", "users.id"],
            name="fk_citizen_history_tenant_user",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ("tenant_id", "citizen_id", "user_id", "action", "created_at"):
        op.create_index(f"ix_citizen_history_{column}", "citizen_history", [column])

    if op.get_bind().dialect.name == "postgresql":
        tenant = "current_setting('app.tenant_id', true)::uuid"
        op.execute("ALTER TABLE citizen_history ENABLE ROW LEVEL SECURITY")
        op.execute("ALTER TABLE citizen_history FORCE ROW LEVEL SECURITY")
        op.execute(
            "CREATE POLICY citizen_history_tenant_isolation ON citizen_history FOR ALL "
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
            op.execute(sa.text(f'GRANT SELECT, INSERT ON TABLE citizen_history TO "{role}"'))


def downgrade():
    op.drop_table("citizen_history")
