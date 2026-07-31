"""Add resumable RAG security rescan runs.

Revision ID: f7b2d4e9a631
Revises: e6a1c3d8f520
"""

import os

import sqlalchemy as sa
from alembic import op

revision = "f7b2d4e9a631"
down_revision = "e6a1c3d8f520"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "rag_security_rescan_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid()),
        sa.Column("scope", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("phase", sa.String(20), nullable=False),
        sa.Column("cursor_id", sa.Uuid()),
        sa.Column("cutoff_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("policy_version", sa.String(80), nullable=False),
        sa.Column("signature_version", sa.String(80)),
        sa.Column("batch_size", sa.Integer(), nullable=False),
        sa.Column("total_targets", sa.Integer(), server_default="0", nullable=False),
        sa.Column("processed_targets", sa.Integer(), server_default="0", nullable=False),
        sa.Column("clean_targets", sa.Integer(), server_default="0", nullable=False),
        sa.Column("quarantined_targets", sa.Integer(), server_default="0", nullable=False),
        sa.Column("error_targets", sa.Integer(), server_default="0", nullable=False),
        sa.Column("purged_chunks", sa.Integer(), server_default="0", nullable=False),
        sa.Column("purged_ocr", sa.Integer(), server_default="0", nullable=False),
        sa.Column("purged_transcriptions", sa.Integer(), server_default="0", nullable=False),
        sa.Column("initiated_by_id", sa.Uuid(), nullable=False),
        sa.Column("error", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "batch_size > 0 AND batch_size <= 100", name="ck_rag_security_rescan_batch"
        ),
        sa.CheckConstraint(
            "(scope = 'TENANT' AND tenant_id IS NOT NULL) OR "
            "(scope = 'GLOBAL' AND tenant_id IS NULL)",
            name="ck_rag_security_rescan_scope_tenant",
        ),
        sa.ForeignKeyConstraint(["initiated_by_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ("tenant_id", "scope", "status", "cursor_id", "initiated_by_id", "created_at"):
        op.create_index(
            f"ix_rag_security_rescan_runs_{column}", "rag_security_rescan_runs", [column]
        )

    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            """
            CREATE UNIQUE INDEX uq_rag_security_rescan_runs_active_scope
            ON rag_security_rescan_runs (
                scope,
                COALESCE(tenant_id, '00000000-0000-0000-0000-000000000000'::uuid)
            )
            WHERE status IN ('PENDENTE', 'PROCESSANDO')
            """
        )
        _enable_rls()
        _grant_runtime_access()


def downgrade():
    op.drop_table("rag_security_rescan_runs")


def _enable_rls() -> None:
    op.execute("ALTER TABLE rag_security_rescan_runs ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE rag_security_rescan_runs FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY rag_security_rescan_runs_isolation
        ON rag_security_rescan_runs
        FOR ALL
        USING (
            tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
            OR (
                tenant_id IS NULL
                AND current_setting('app.global_knowledge_admin', true) = 'true'
            )
        )
        WITH CHECK (
            tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
            OR (
                tenant_id IS NULL
                AND current_setting('app.global_knowledge_admin', true) = 'true'
            )
        )
        """
    )


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
        op.execute(
            sa.text(
                f'GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE rag_security_rescan_runs TO "{role}"'
            )
        )
