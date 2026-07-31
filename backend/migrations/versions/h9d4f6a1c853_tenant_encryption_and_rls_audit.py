"""Add tenant encryption metadata and automated RLS audit.

Revision ID: h9d4f6a1c853
Revises: g8c3e5f0b742
"""

import os

import sqlalchemy as sa
from alembic import op

revision = "h9d4f6a1c853"
down_revision = "g8c3e5f0b742"
branch_labels = None
depends_on = None


def upgrade():
    for table, schema in (
        ("attachments", None),
        ("rag_document_versions", None),
        ("document_versions", "rag_global"),
    ):
        op.add_column(
            table,
            sa.Column("encryption_key_version", sa.Integer(), server_default="0", nullable=False),
            schema=schema,
        )
        op.add_column(
            table, sa.Column("encryption_algorithm", sa.String(40)), schema=schema
        )
        op.add_column(
            table, sa.Column("encrypted_at", sa.DateTime(timezone=True)), schema=schema
        )

    op.create_table(
        "rls_audit_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("initiated_by_id", sa.Uuid(), nullable=False),
        sa.Column("expected_tables", sa.Integer(), nullable=False),
        sa.Column("compliant_tables", sa.Integer(), nullable=False),
        sa.Column("findings", sa.JSON(), nullable=False),
        sa.Column("role_checks", sa.JSON(), nullable=False),
        sa.Column("error", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(["initiated_by_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_rls_audit_runs_status", "rls_audit_runs", ["status"])
    op.create_index("ix_rls_audit_runs_initiated_by_id", "rls_audit_runs", ["initiated_by_id"])
    op.create_index("ix_rls_audit_runs_created_at", "rls_audit_runs", ["created_at"])

    if op.get_bind().dialect.name == "postgresql":
        op.execute("ALTER TABLE attachments ENABLE ROW LEVEL SECURITY")
        op.execute("ALTER TABLE attachments FORCE ROW LEVEL SECURITY")
        op.execute(
            """
            CREATE POLICY attachments_tenant_isolation ON attachments FOR ALL
            USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
            WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
            """
        )
        _grant_runtime_access()


def downgrade():
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP POLICY IF EXISTS attachments_tenant_isolation ON attachments")
        op.execute("ALTER TABLE attachments NO FORCE ROW LEVEL SECURITY")
        op.execute("ALTER TABLE attachments DISABLE ROW LEVEL SECURITY")
    op.drop_table("rls_audit_runs")
    for table, schema in (
        ("attachments", None),
        ("rag_document_versions", None),
        ("document_versions", "rag_global"),
    ):
        op.drop_column(table, "encrypted_at", schema=schema)
        op.drop_column(table, "encryption_algorithm", schema=schema)
        op.drop_column(table, "encryption_key_version", schema=schema)


def _grant_runtime_access():
    bind = op.get_bind()
    roles = {os.getenv("APP_DB_USER", "gabflow_app"), os.getenv("WORKER_DB_USER", "gabflow_worker")}
    available = {
        row[0]
        for row in bind.execute(
            sa.text("SELECT rolname FROM pg_roles WHERE rolname = ANY(:roles)"),
            {"roles": list(roles)},
        )
    }
    for role in roles & available:
        op.execute(sa.text(f'GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE rls_audit_runs TO "{role}"'))
