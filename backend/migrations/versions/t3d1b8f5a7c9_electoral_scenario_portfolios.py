"""Add electoral scenario portfolios, goals and append-only history.

Revision ID: t3d1b8f5a7c9
Revises: s2c0a7e4f6b8
"""

import os

import sqlalchemy as sa
from alembic import op

revision = "t3d1b8f5a7c9"
down_revision = "s2c0a7e4f6b8"
branch_labels = None
depends_on = None

TABLES = (
    "electoral_scenario_portfolios",
    "electoral_scenario_portfolio_items",
    "electoral_scenario_portfolio_events",
)


def upgrade():
    op.create_table(
        "electoral_scenario_portfolios",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("mandate_id", sa.Uuid(), nullable=False),
        sa.Column("created_by_id", sa.Uuid(), nullable=False),
        sa.Column("reference_scenario_id", sa.Uuid()),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("description", sa.String(1000)),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("goals", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('ACTIVE', 'ARCHIVED')",
            name="ck_electoral_scenario_portfolios_status",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "mandate_id"],
            ["mandates.tenant_id", "mandates.id"],
            ondelete="CASCADE",
            name="fk_electoral_scenario_portfolios_tenant_mandate",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "created_by_id"],
            ["users.tenant_id", "users.id"],
            ondelete="RESTRICT",
            name="fk_electoral_scenario_portfolios_tenant_creator",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "reference_scenario_id"],
            ["electoral_scenarios.tenant_id", "electoral_scenarios.id"],
            ondelete="RESTRICT",
            name="fk_electoral_scenario_portfolios_tenant_reference",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id", "id", name="uq_electoral_scenario_portfolios_tenant_id_id"
        ),
    )
    op.create_table(
        "electoral_scenario_portfolio_items",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("portfolio_id", sa.Uuid(), nullable=False),
        sa.Column("scenario_id", sa.Uuid(), nullable=False),
        sa.Column("added_by_id", sa.Uuid(), nullable=False),
        sa.Column("label", sa.String(160)),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("added_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("removed_at", sa.DateTime(timezone=True)),
        sa.Column("removed_by_id", sa.Uuid()),
        sa.ForeignKeyConstraint(
            ["tenant_id", "portfolio_id"],
            ["electoral_scenario_portfolios.tenant_id", "electoral_scenario_portfolios.id"],
            ondelete="CASCADE",
            name="fk_electoral_scenario_portfolio_items_tenant_portfolio",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "scenario_id"],
            ["electoral_scenarios.tenant_id", "electoral_scenarios.id"],
            ondelete="CASCADE",
            name="fk_electoral_scenario_portfolio_items_tenant_scenario",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "added_by_id"],
            ["users.tenant_id", "users.id"],
            ondelete="RESTRICT",
            name="fk_electoral_scenario_portfolio_items_tenant_adder",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "removed_by_id"],
            ["users.tenant_id", "users.id"],
            ondelete="RESTRICT",
            name="fk_electoral_scenario_portfolio_items_tenant_remover",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "portfolio_id",
            "scenario_id",
            name="uq_electoral_scenario_portfolio_items_membership",
        ),
    )
    op.create_table(
        "electoral_scenario_portfolio_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("portfolio_id", sa.Uuid(), nullable=False),
        sa.Column("actor_id", sa.Uuid(), nullable=False),
        sa.Column("event_type", sa.String(40), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id", "portfolio_id"],
            ["electoral_scenario_portfolios.tenant_id", "electoral_scenario_portfolios.id"],
            ondelete="CASCADE",
            name="fk_electoral_scenario_portfolio_events_tenant_portfolio",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "actor_id"],
            ["users.tenant_id", "users.id"],
            ondelete="RESTRICT",
            name="fk_electoral_scenario_portfolio_events_tenant_actor",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    indexes = {
        "electoral_scenario_portfolios": (
            "tenant_id",
            "mandate_id",
            "created_by_id",
            "reference_scenario_id",
            "status",
        ),
        "electoral_scenario_portfolio_items": (
            "tenant_id",
            "portfolio_id",
            "scenario_id",
            "added_by_id",
            "removed_at",
            "removed_by_id",
        ),
        "electoral_scenario_portfolio_events": (
            "tenant_id",
            "portfolio_id",
            "actor_id",
            "event_type",
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
