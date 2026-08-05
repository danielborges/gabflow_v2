"""Add electoral SHOULD and COULD feature persistence.

Revision ID: a0e8f5a2b4c6
Revises: z9d7e4f1a3b5
"""

import os

import sqlalchemy as sa
from alembic import op

revision = "a0e8f5a2b4c6"
down_revision = "z9d7e4f1a3b5"
branch_labels = None
depends_on = None

TABLES = (
    "electoral_user_preferences",
    "electoral_territory_segments",
    "electoral_report_schedules",
)


def upgrade():
    op.create_table(
        TABLES[0],
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("mandate_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("election_id", sa.Uuid()),
        sa.Column("office_id", sa.Uuid()),
        sa.Column("territory_level", sa.String(30), nullable=False),
        sa.Column("indicators", sa.JSON(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id", "mandate_id"],
            ["mandates.tenant_id", "mandates.id"],
            ondelete="CASCADE",
            name="fk_electoral_user_preferences_tenant_mandate",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "user_id"],
            ["users.tenant_id", "users.id"],
            ondelete="CASCADE",
            name="fk_electoral_user_preferences_tenant_user",
        ),
        sa.ForeignKeyConstraint(["election_id"], ["electoral_elections.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["office_id"], ["electoral_offices.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id", "mandate_id", "user_id", name="uq_electoral_user_preferences_scope"
        ),
        sa.UniqueConstraint("tenant_id", "id", name="uq_electoral_user_preferences_tenant_id_id"),
    )
    op.create_table(
        TABLES[1],
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("mandate_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("description", sa.String(500)),
        sa.Column("election_id", sa.Uuid(), nullable=False),
        sa.Column("territory_ids", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id", "mandate_id"],
            ["mandates.tenant_id", "mandates.id"],
            ondelete="CASCADE",
            name="fk_electoral_segments_tenant_mandate",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "user_id"],
            ["users.tenant_id", "users.id"],
            ondelete="CASCADE",
            name="fk_electoral_segments_tenant_user",
        ),
        sa.ForeignKeyConstraint(["election_id"], ["electoral_elections.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id", "mandate_id", "user_id", "name", name="uq_electoral_segment_name"
        ),
        sa.UniqueConstraint("tenant_id", "id", name="uq_electoral_segments_tenant_id_id"),
    )
    op.create_table(
        TABLES[2],
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("mandate_id", sa.Uuid(), nullable=False),
        sa.Column("created_by_id", sa.Uuid(), nullable=False),
        sa.Column("template_report_job_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("frequency", sa.String(20), nullable=False),
        sa.Column("recipient_ids", sa.JSON(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_run_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "frequency IN ('DAILY', 'WEEKLY', 'MONTHLY')",
            name="ck_electoral_report_schedule_frequency",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "mandate_id"],
            ["mandates.tenant_id", "mandates.id"],
            ondelete="CASCADE",
            name="fk_electoral_report_schedules_tenant_mandate",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "created_by_id"],
            ["users.tenant_id", "users.id"],
            ondelete="CASCADE",
            name="fk_electoral_report_schedules_tenant_creator",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "template_report_job_id"],
            ["electoral_report_jobs.tenant_id", "electoral_report_jobs.id"],
            ondelete="CASCADE",
            name="fk_electoral_report_schedules_tenant_template",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_electoral_report_schedules_tenant_id_id"),
    )
    indexes = {
        TABLES[0]: ("tenant_id", "mandate_id", "user_id", "election_id", "office_id"),
        TABLES[1]: ("tenant_id", "mandate_id", "user_id", "election_id"),
        TABLES[2]: (
            "tenant_id",
            "mandate_id",
            "created_by_id",
            "template_report_job_id",
            "active",
            "next_run_at",
        ),
    }
    for table, columns in indexes.items():
        for column in columns:
            op.create_index(f"ix_{table}_{column}", table, [column])
    if op.get_bind().dialect.name == "postgresql":
        tenant = "NULLIF(current_setting('app.tenant_id', true), '')::uuid"
        actor = "NULLIF(current_setting('app.user_id', true), '')::uuid"
        for table in TABLES:
            op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
            op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        for table in TABLES[:2]:
            op.execute(
                f"CREATE POLICY {table}_user_isolation ON {table} FOR ALL USING (tenant_id = {tenant} AND user_id = {actor}) WITH CHECK (tenant_id = {tenant} AND user_id = {actor})"
            )
        op.execute(
            f"CREATE POLICY {TABLES[2]}_tenant_isolation ON {TABLES[2]} FOR ALL USING (tenant_id = {tenant}) WITH CHECK (tenant_id = {tenant})"
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
