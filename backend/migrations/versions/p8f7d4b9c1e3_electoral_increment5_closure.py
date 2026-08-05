"""Close electoral mandate intelligence with briefings and alert preferences.

Revision ID: p8f7d4b9c1e3
Revises: o7e6c3a8b0d2
"""

import os

import sqlalchemy as sa
from alembic import op

revision = "p8f7d4b9c1e3"
down_revision = "o7e6c3a8b0d2"
branch_labels = None
depends_on = None

TABLE = "electoral_alert_preferences"


def upgrade():
    op.create_table(
        TABLE,
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("mandate_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("channels", sa.JSON(), nullable=False),
        sa.Column("frequency", sa.String(20), nullable=False),
        sa.Column("alert_types", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "frequency IN ('IMMEDIATE', 'DAILY', 'WEEKLY')",
            name="ck_electoral_alert_preferences_frequency",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "mandate_id"],
            ["mandates.tenant_id", "mandates.id"],
            ondelete="CASCADE",
            name="fk_electoral_alert_preferences_tenant_mandate",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "user_id"],
            ["users.tenant_id", "users.id"],
            ondelete="CASCADE",
            name="fk_electoral_alert_preferences_tenant_user",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "mandate_id",
            "user_id",
            name="uq_electoral_alert_preferences_user_mandate",
        ),
        sa.UniqueConstraint(
            "tenant_id", "id", name="uq_electoral_alert_preferences_tenant_id_id"
        ),
    )
    for column in ("tenant_id", "mandate_id", "user_id"):
        op.create_index(f"ix_{TABLE}_{column}", TABLE, [column])

    if op.get_bind().dialect.name == "postgresql":
        op.execute(f"ALTER TABLE {TABLE} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {TABLE} FORCE ROW LEVEL SECURITY")
        actor = "NULLIF(current_setting('app.user_id', true), '')::uuid"
        tenant = "NULLIF(current_setting('app.tenant_id', true), '')::uuid"
        for command in ("SELECT", "INSERT", "UPDATE"):
            operation = command.lower()
            predicate = f"tenant_id = {tenant} AND user_id = {actor}"
            using = f"USING ({predicate})" if command in {"SELECT", "UPDATE"} else ""
            check = f"WITH CHECK ({predicate})" if command in {"INSERT", "UPDATE"} else ""
            op.execute(
                f"CREATE POLICY {TABLE}_{operation} ON {TABLE} "
                f"FOR {command} {using} {check}"
            )
        _grant_runtime_access()


def downgrade():
    if op.get_bind().dialect.name == "postgresql":
        for command in ("UPDATE", "INSERT", "SELECT"):
            op.execute(f"DROP POLICY IF EXISTS {TABLE}_{command.lower()} ON {TABLE}")
        op.execute(f"ALTER TABLE {TABLE} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {TABLE} DISABLE ROW LEVEL SECURITY")
    op.drop_table(TABLE)


def _grant_runtime_access() -> None:
    bind = op.get_bind()
    app_role = os.getenv("APP_DB_USER", "gabflow_app")
    worker_role = os.getenv("WORKER_DB_USER", "gabflow_worker")
    available = {
        row[0]
        for row in bind.execute(
            sa.text("SELECT rolname FROM pg_roles WHERE rolname = ANY(:roles)"),
            {"roles": [app_role, worker_role]},
        )
    }
    if app_role in available:
        op.execute(sa.text(f'GRANT SELECT, INSERT, UPDATE ON TABLE {TABLE} TO "{app_role}"'))
    if worker_role in available:
        op.execute(sa.text(f'GRANT SELECT ON TABLE {TABLE} TO "{worker_role}"'))
