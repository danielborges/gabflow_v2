"""Add immutable scenario analyses and revocable read-only sharing.

Revision ID: s2c0a7e4f6b8
Revises: r1b9f6d1e3a5
"""

import os

import sqlalchemy as sa
from alembic import op

revision = "s2c0a7e4f6b8"
down_revision = "r1b9f6d1e3a5"
branch_labels = None
depends_on = None

TABLES = ("electoral_scenario_shares", "electoral_scenario_analyses")


def upgrade():
    op.create_table(
        "electoral_scenario_shares",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("scenario_id", sa.Uuid(), nullable=False),
        sa.Column("created_by_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("access_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("last_accessed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id", "scenario_id"],
            ["electoral_scenarios.tenant_id", "electoral_scenarios.id"],
            ondelete="CASCADE",
            name="fk_electoral_scenario_shares_tenant_scenario",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "created_by_id"],
            ["users.tenant_id", "users.id"],
            ondelete="RESTRICT",
            name="fk_electoral_scenario_shares_tenant_creator",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash", name="uq_electoral_scenario_shares_token_hash"),
    )
    op.create_table(
        "electoral_scenario_analyses",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("mandate_id", sa.Uuid(), nullable=False),
        sa.Column("created_by_id", sa.Uuid(), nullable=False),
        sa.Column("analysis_type", sa.String(20), nullable=False),
        sa.Column("anchor_scenario_id", sa.Uuid(), nullable=False),
        sa.Column("scenario_ids", sa.JSON(), nullable=False),
        sa.Column("parameters", sa.JSON(), nullable=False),
        sa.Column("result", sa.JSON(), nullable=False),
        sa.Column("methodology_version", sa.String(80), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "analysis_type IN ('COMPARISON', 'SENSITIVITY')",
            name="ck_electoral_scenario_analyses_type",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "mandate_id"],
            ["mandates.tenant_id", "mandates.id"],
            ondelete="CASCADE",
            name="fk_electoral_scenario_analyses_tenant_mandate",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "created_by_id"],
            ["users.tenant_id", "users.id"],
            ondelete="RESTRICT",
            name="fk_electoral_scenario_analyses_tenant_creator",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "anchor_scenario_id"],
            ["electoral_scenarios.tenant_id", "electoral_scenarios.id"],
            ondelete="CASCADE",
            name="fk_electoral_scenario_analyses_tenant_anchor",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    indexes = {
        "electoral_scenario_shares": (
            "tenant_id",
            "scenario_id",
            "created_by_id",
            "token_hash",
            "expires_at",
            "revoked_at",
        ),
        "electoral_scenario_analyses": (
            "tenant_id",
            "mandate_id",
            "created_by_id",
            "analysis_type",
            "anchor_scenario_id",
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
            predicate = f"tenant_id = {tenant}"
            for command in ("SELECT", "INSERT", "UPDATE"):
                using = f"USING ({predicate})" if command in {"SELECT", "UPDATE"} else ""
                check = f"WITH CHECK ({predicate})" if command in {"INSERT", "UPDATE"} else ""
                op.execute(
                    f"CREATE POLICY {table}_{command.lower()} ON {table} "
                    f"FOR {command} {using} {check}"
                )
        _grant_runtime_access()


def downgrade():
    for table in reversed(TABLES):
        if op.get_bind().dialect.name == "postgresql":
            for command in ("UPDATE", "INSERT", "SELECT"):
                op.execute(f"DROP POLICY IF EXISTS {table}_{command.lower()} ON {table}")
            op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
            op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
        op.drop_table(table)


def _grant_runtime_access() -> None:
    bind = op.get_bind()
    app_role = os.getenv("APP_DB_USER", "gabflow_app")
    available = {
        row[0]
        for row in bind.execute(
            sa.text("SELECT rolname FROM pg_roles WHERE rolname = ANY(:roles)"),
            {"roles": [app_role]},
        )
    }
    if app_role in available:
        for table in TABLES:
            op.execute(sa.text(f'GRANT SELECT, INSERT, UPDATE ON TABLE {table} TO "{app_role}"'))
