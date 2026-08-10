"""Add structured territorial evidence and alert lifecycle.

Revision ID: f2b5d7e9a1c3
Revises: e1a4c6d8f0b2
"""

import os

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "f2b5d7e9a1c3"
down_revision = "e1a4c6d8f0b2"
branch_labels = None
depends_on = None


def upgrade():
    alert_status = sa.Enum("ATIVO", "RECONHECIDO", "RESOLVIDO", name="territorial_alert_status")
    op.create_table(
        "territorial_action_evidence",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("action_id", sa.Uuid(), nullable=False),
        sa.Column("evidence_type", sa.String(40), nullable=False),
        sa.Column("title", sa.String(180), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("occurred_at", sa.DateTime(timezone=True)),
        sa.Column("external_url", sa.String(1000)),
        sa.Column("storage_key", sa.String(300), unique=True),
        sa.Column("original_name", sa.String(255)),
        sa.Column("mime_type", sa.String(120)),
        sa.Column("size_bytes", sa.BigInteger()),
        sa.Column("sha256", sa.String(64)),
        sa.Column(
            "scan_status",
            postgresql.ENUM(name="attachment_scan_status", create_type=False),
        ),
        sa.Column("scan_provider", sa.String(80)),
        sa.Column("scan_engine_version", sa.String(80)),
        sa.Column("scan_signature_version", sa.String(80)),
        sa.Column("scan_threat", sa.String(160)),
        sa.Column("scan_error_code", sa.String(80)),
        sa.Column("scanned_at", sa.DateTime(timezone=True)),
        sa.Column("encryption_key_version", sa.Integer()),
        sa.Column("encryption_algorithm", sa.String(40)),
        sa.Column("encrypted_at", sa.DateTime(timezone=True)),
        sa.Column("created_by_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["action_id"], ["territorial_actions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "territorial_action_alerts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("action_id", sa.Uuid(), nullable=False),
        sa.Column("alert_type", sa.String(40), nullable=False),
        sa.Column("status", alert_status, nullable=False),
        sa.Column("title", sa.String(180), nullable=False),
        sa.Column("message", sa.String(500), nullable=False),
        sa.Column("triggered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True)),
        sa.Column("acknowledged_by_id", sa.Uuid()),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
        sa.Column("resolved_by_id", sa.Uuid()),
        sa.Column("resolution_note", sa.String(500)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["action_id"], ["territorial_actions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["acknowledged_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["resolved_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "action_id", "alert_type", name="uq_territorial_alert"),
    )
    for table, columns in {
        "territorial_action_evidence": ("tenant_id", "action_id", "evidence_type", "sha256", "created_at"),
        "territorial_action_alerts": ("tenant_id", "action_id", "alert_type", "status", "created_at"),
    }.items():
        for column in columns:
            op.create_index(f"ix_{table}_{column}", table, [column])
    if op.get_bind().dialect.name == "postgresql":
        app_user = os.getenv("APP_DB_USER", "gabflow_app")
        worker_user = os.getenv("WORKER_DB_USER", "gabflow_worker")
        for table in ("territorial_action_evidence", "territorial_action_alerts"):
            op.execute(f'GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE {table} TO "{app_user}", "{worker_user}"')
            op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
            op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
            op.execute(
                f"CREATE POLICY {table}_tenant_isolation ON {table} FOR ALL "
                "USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid) "
                "WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)"
            )


def downgrade():
    op.drop_table("territorial_action_alerts")
    op.drop_table("territorial_action_evidence")
    if op.get_bind().dialect.name == "postgresql":
        sa.Enum(name="territorial_alert_status").drop(op.get_bind(), checkfirst=True)
