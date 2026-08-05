"""RAG learning candidate artifacts

Revision ID: c08e1f4a6b72
Revises: bf7a9d4e2c53
Create Date: 2026-07-30 00:00:00
"""

import os

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "c08e1f4a6b72"
down_revision = "bf7a9d4e2c53"
branch_labels = None
depends_on = None

TABLES = (
    "rag_learning_runs",
    "rag_learning_artifacts",
    "rag_learning_artifact_feedback",
)


def upgrade():
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    run_status = postgresql.ENUM(
        "PENDENTE",
        "PROCESSANDO",
        "CONCLUIDA",
        "ERRO",
        name="rag_learning_run_status",
        create_type=False,
    )
    artifact_type = postgresql.ENUM(
        "RERANK_PROFILE",
        "ROUTING_EXAMPLES",
        "EVALUATION_CASES",
        "ANSWER_EXEMPLARS",
        name="rag_learning_artifact_type",
        create_type=False,
    )
    artifact_status = postgresql.ENUM(
        "CANDIDATO",
        "EM_AVALIACAO",
        "REJEITADO",
        "APROVADO",
        "ATIVO",
        "SUBSTITUIDO",
        "REVOGADO",
        name="rag_learning_artifact_status",
        create_type=False,
    )
    for enum_type in (run_status, artifact_type, artifact_status):
        enum_type.create(bind, checkfirst=True)

    op.create_table(
        "rag_learning_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("window_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "configuration",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("configuration_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "baseline",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("total_feedbacks", sa.Integer(), server_default="0", nullable=False),
        sa.Column("total_approved", sa.Integer(), server_default="0", nullable=False),
        sa.Column("total_quarantine", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "metrics",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("status", run_status, nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("initiated_by_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "window_start < window_end",
            name="ck_rag_learning_runs_window",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "initiated_by_id"],
            ["users.tenant_id", "users.id"],
            name="fk_rag_learning_runs_tenant_initiator",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "id",
            name="uq_rag_learning_runs_tenant_id_id",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "window_start",
            "window_end",
            "configuration_hash",
            name="uq_rag_learning_runs_idempotency",
        ),
    )
    op.create_table(
        "rag_learning_artifacts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("artifact_type", artifact_type, nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("payload_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "source_feedback_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "baseline",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "metrics_before",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "metrics_after",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("status", artifact_status, nullable=False),
        sa.Column("approved_by_id", sa.Uuid(), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("replaced_by_id", sa.Uuid(), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revocation_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "version > 0",
            name="ck_rag_learning_artifacts_version_positive",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "run_id"],
            ["rag_learning_runs.tenant_id", "rag_learning_runs.id"],
            name="fk_rag_learning_artifacts_tenant_run",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "approved_by_id"],
            ["users.tenant_id", "users.id"],
            name="fk_rag_learning_artifacts_tenant_approver",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "replaced_by_id"],
            ["rag_learning_artifacts.tenant_id", "rag_learning_artifacts.id"],
            name="fk_rag_learning_artifacts_tenant_replacement",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "id",
            name="uq_rag_learning_artifacts_tenant_id_id",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "artifact_type",
            "version",
            name="uq_rag_learning_artifacts_version",
        ),
    )
    op.create_table(
        "rag_learning_artifact_feedback",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("artifact_id", sa.Uuid(), nullable=False),
        sa.Column("feedback_id", sa.Uuid(), nullable=False),
        sa.Column(
            "contribution",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "artifact_id"],
            ["rag_learning_artifacts.tenant_id", "rag_learning_artifacts.id"],
            name="fk_rag_learning_artifact_feedback_tenant_artifact",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "feedback_id"],
            ["rag_query_feedback.tenant_id", "rag_query_feedback.id"],
            name="fk_rag_learning_artifact_feedback_tenant_feedback",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "artifact_id",
            "feedback_id",
            name="uq_rag_learning_artifact_feedback",
        ),
    )

    indexes = {
        "rag_learning_runs": (
            "tenant_id",
            "window_start",
            "window_end",
            "configuration_hash",
            "status",
            "initiated_by_id",
            "created_at",
        ),
        "rag_learning_artifacts": (
            "tenant_id",
            "run_id",
            "artifact_type",
            "payload_hash",
            "status",
            "approved_by_id",
            "replaced_by_id",
            "created_at",
        ),
        "rag_learning_artifact_feedback": (
            "tenant_id",
            "artifact_id",
            "feedback_id",
        ),
    }
    for table, columns in indexes.items():
        for column in columns:
            op.create_index(f"ix_{table}_{column}", table, [column])
        _enable_rls(table)
    _grant_runtime_access()


def downgrade():
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    for table in reversed(TABLES):
        op.execute(f"DROP POLICY IF EXISTS {table}_isolation ON {table}")
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
        op.drop_table(table)
    for enum_name in (
        "rag_learning_artifact_status",
        "rag_learning_artifact_type",
        "rag_learning_run_status",
    ):
        postgresql.ENUM(name=enum_name).drop(bind, checkfirst=True)


def _enable_rls(table: str) -> None:
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"""
        CREATE POLICY {table}_isolation
        ON {table}
        FOR ALL
        USING (
            tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
        )
        WITH CHECK (
            tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
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
        quoted = bind.dialect.identifier_preparer.quote_identifier(role)
        for table in TABLES:
            op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO {quoted}")
