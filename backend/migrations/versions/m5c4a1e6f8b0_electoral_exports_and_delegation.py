"""Add auditable electoral exports.

Revision ID: m5c4a1e6f8b0
Revises: l4b3f0d5e7a9
"""

import os

import sqlalchemy as sa
from alembic import op

revision = "m5c4a1e6f8b0"
down_revision = "l4b3f0d5e7a9"
branch_labels = None
depends_on = None

TABLES = ("electoral_report_jobs", "electoral_generated_reports")


def upgrade():
    op.create_table(
        "electoral_report_jobs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("mandate_id", sa.Uuid(), nullable=False),
        sa.Column("requested_by_id", sa.Uuid(), nullable=False),
        sa.Column("report_type", sa.String(30), nullable=False),
        sa.Column("format", sa.String(10), nullable=False),
        sa.Column("purpose", sa.String(500), nullable=False),
        sa.Column("filters", sa.JSON(), nullable=False),
        sa.Column("source_metadata", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("retry_count", sa.Integer(), nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("error", sa.Text()),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("revoked_by_id", sa.Uuid()),
        sa.CheckConstraint("format IN ('PDF', 'CSV', 'XLSX')", name="ck_electoral_report_format"),
        sa.CheckConstraint(
            "report_type IN ('candidate', 'comparison')", name="ck_electoral_report_type"
        ),
        sa.CheckConstraint(
            "status IN ('QUEUED', 'PROCESSING', 'COMPLETED', 'FAILED', 'REVOKED')",
            name="ck_electoral_report_status",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "mandate_id"],
            ["mandates.tenant_id", "mandates.id"],
            ondelete="CASCADE",
            name="fk_electoral_report_jobs_tenant_mandate",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "requested_by_id"],
            ["users.tenant_id", "users.id"],
            ondelete="RESTRICT",
            name="fk_electoral_report_jobs_tenant_requester",
        ),
        sa.ForeignKeyConstraint(["revoked_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_electoral_report_jobs_tenant_id_id"),
    )
    for column in (
        "tenant_id",
        "mandate_id",
        "requested_by_id",
        "status",
        "revoked_at",
        "revoked_by_id",
    ):
        op.create_index(f"ix_electoral_report_jobs_{column}", "electoral_report_jobs", [column])

    op.create_table(
        "electoral_generated_reports",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("report_job_id", sa.Uuid(), nullable=False),
        sa.Column("storage_key", sa.String(500), nullable=False),
        sa.Column("filename", sa.String(240), nullable=False),
        sa.Column("mime_type", sa.String(120), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("encryption_key_version", sa.Integer(), nullable=False),
        sa.Column("encryption_algorithm", sa.String(40), nullable=False),
        sa.Column("encrypted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("download_count", sa.Integer(), nullable=False),
        sa.Column("last_downloaded_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id", "report_job_id"],
            ["electoral_report_jobs.tenant_id", "electoral_report_jobs.id"],
            ondelete="CASCADE",
            name="fk_electoral_generated_reports_tenant_job",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("report_job_id", name="uq_electoral_generated_report_job"),
    )
    for column in ("tenant_id", "report_job_id", "expires_at", "revoked_at"):
        op.create_index(
            f"ix_electoral_generated_reports_{column}",
            "electoral_generated_reports",
            [column],
        )

    if op.get_bind().dialect.name == "postgresql":
        for table in TABLES:
            op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
            op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
            op.execute(
                f"""
                CREATE POLICY {table}_tenant_isolation ON {table} FOR ALL
                USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
                WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
                """
            )
        _grant_runtime_access()


def downgrade():
    if op.get_bind().dialect.name == "postgresql":
        for table in reversed(TABLES):
            op.execute(f"DROP POLICY IF EXISTS {table}_tenant_isolation ON {table}")
            op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
            op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
    op.drop_table("electoral_generated_reports")
    op.drop_table("electoral_report_jobs")


def _grant_runtime_access() -> None:
    bind = op.get_bind()
    roles = {
        os.getenv("APP_DB_USER", "gabflow_app"),
        os.getenv("WORKER_DB_USER", "gabflow_worker"),
    }
    available = {
        row[0]
        for row in bind.execute(
            sa.text("SELECT rolname FROM pg_roles WHERE rolname = ANY(:roles)"),
            {"roles": list(roles)},
        )
    }
    for role in roles & available:
        for table in TABLES:
            op.execute(
                sa.text(f'GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE {table} TO "{role}"')
            )
