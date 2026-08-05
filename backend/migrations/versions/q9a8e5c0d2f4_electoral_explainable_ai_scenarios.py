"""Start explainable electoral insights and auditable scenarios.

Revision ID: q9a8e5c0d2f4
Revises: p8f7d4b9c1e3
"""

import os

import sqlalchemy as sa
from alembic import op

revision = "q9a8e5c0d2f4"
down_revision = "p8f7d4b9c1e3"
branch_labels = None
depends_on = None

TABLES = (
    "electoral_insights",
    "electoral_insight_feedback",
    "electoral_scenarios",
)


def upgrade():
    op.create_table(
        "electoral_insights",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("mandate_id", sa.Uuid(), nullable=False),
        sa.Column("requested_by_id", sa.Uuid(), nullable=False),
        sa.Column("analysis_type", sa.String(30), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("request_payload", sa.JSON(), nullable=False),
        sa.Column("input_snapshot", sa.JSON(), nullable=False),
        sa.Column("facts", sa.JSON(), nullable=False),
        sa.Column("calculations", sa.JSON(), nullable=False),
        sa.Column("hypotheses", sa.JSON(), nullable=False),
        sa.Column("limitations", sa.JSON(), nullable=False),
        sa.Column("citations", sa.JSON(), nullable=False),
        sa.Column("model_provider", sa.String(80), nullable=False),
        sa.Column("model_name", sa.String(120), nullable=False),
        sa.Column("prompt_version", sa.String(80), nullable=False),
        sa.Column("draft", sa.Boolean(), nullable=False),
        sa.Column("refusal_reason", sa.String(500)),
        sa.Column("error", sa.Text()),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "analysis_type IN ('candidate', 'comparison', 'question')",
            name="ck_electoral_insights_analysis_type",
        ),
        sa.CheckConstraint(
            "status IN ('QUEUED', 'PROCESSING', 'COMPLETED', 'FAILED', 'REFUSED', 'HIDDEN')",
            name="ck_electoral_insights_status",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "mandate_id"],
            ["mandates.tenant_id", "mandates.id"],
            ondelete="CASCADE",
            name="fk_electoral_insights_tenant_mandate",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "requested_by_id"],
            ["users.tenant_id", "users.id"],
            ondelete="RESTRICT",
            name="fk_electoral_insights_tenant_requester",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_electoral_insights_tenant_id_id"),
    )
    op.create_table(
        "electoral_insight_feedback",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("insight_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("rating", sa.String(20), nullable=False),
        sa.Column("reason", sa.String(160)),
        sa.Column("comment", sa.String(1000)),
        sa.Column("model_version", sa.String(120), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "rating IN ('ACCEPTED', 'DISCARDED', 'CONTESTED')",
            name="ck_electoral_insight_feedback_rating",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "insight_id"],
            ["electoral_insights.tenant_id", "electoral_insights.id"],
            ondelete="CASCADE",
            name="fk_electoral_insight_feedback_tenant_insight",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "user_id"],
            ["users.tenant_id", "users.id"],
            ondelete="RESTRICT",
            name="fk_electoral_insight_feedback_tenant_user",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "electoral_scenarios",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("mandate_id", sa.Uuid(), nullable=False),
        sa.Column("created_by_id", sa.Uuid(), nullable=False),
        sa.Column("source_scenario_id", sa.Uuid()),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("baseline_election_id", sa.Uuid(), nullable=False),
        sa.Column("candidate_id", sa.Uuid(), nullable=False),
        sa.Column("level", sa.String(30), nullable=False),
        sa.Column("assumptions", sa.JSON(), nullable=False),
        sa.Column("baseline_snapshot", sa.JSON(), nullable=False),
        sa.Column("result", sa.JSON(), nullable=False),
        sa.Column("methodology_version", sa.String(80), nullable=False),
        sa.Column("disclaimer", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id", "mandate_id"],
            ["mandates.tenant_id", "mandates.id"],
            ondelete="CASCADE",
            name="fk_electoral_scenarios_tenant_mandate",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "created_by_id"],
            ["users.tenant_id", "users.id"],
            ondelete="RESTRICT",
            name="fk_electoral_scenarios_tenant_creator",
        ),
        sa.ForeignKeyConstraint(
            ["source_scenario_id"], ["electoral_scenarios.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["baseline_election_id"], ["electoral_elections.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["candidate_id"], ["electoral_candidates.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_electoral_scenarios_tenant_id_id"),
    )
    indexes = {
        "electoral_insights": ("tenant_id", "mandate_id", "requested_by_id", "status"),
        "electoral_insight_feedback": ("tenant_id", "insight_id", "user_id"),
        "electoral_scenarios": (
            "tenant_id",
            "mandate_id",
            "created_by_id",
            "source_scenario_id",
            "baseline_election_id",
            "candidate_id",
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
    worker_role = os.getenv("WORKER_DB_USER", "gabflow_worker")
    available = {
        row[0]
        for row in bind.execute(
            sa.text("SELECT rolname FROM pg_roles WHERE rolname = ANY(:roles)"),
            {"roles": [app_role, worker_role]},
        )
    }
    for table in TABLES:
        if app_role in available:
            op.execute(sa.text(f'GRANT SELECT, INSERT, UPDATE ON TABLE {table} TO "{app_role}"'))
    if worker_role in available:
        op.execute(sa.text(f'GRANT SELECT, UPDATE ON TABLE electoral_insights TO "{worker_role}"'))
