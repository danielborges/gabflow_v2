"""oversight agenda evidence

Revision ID: a5d9f1b3c7e2
Revises: f4c8e2a6d0b1
Create Date: 2026-08-11 14:00:00
"""

import os

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "a5d9f1b3c7e2"
down_revision = "f4c8e2a6d0b1"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("ALTER TYPE agenda_event_type ADD VALUE IF NOT EXISTS 'FISCALIZACAO'")

    op.add_column(
        "oversight_actions",
        sa.Column("agenda_event_id", sa.Uuid(), nullable=True),
    )
    op.create_foreign_key(
        "fk_oversight_actions_agenda_event",
        "oversight_actions",
        "agenda_events",
        ["agenda_event_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_oversight_actions_agenda_event_id",
        "oversight_actions",
        ["agenda_event_id"],
        unique=True,
    )
    op.create_table(
        "oversight_evidence",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("oversight_action_id", sa.Uuid(), nullable=False),
        sa.Column("evidence_type", sa.String(length=40), nullable=False),
        sa.Column("observation", sa.Text(), nullable=True),
        sa.Column("storage_key", sa.String(length=300), nullable=False),
        sa.Column("original_name", sa.String(length=255), nullable=False),
        sa.Column("mime_type", sa.String(length=120), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column(
            "scan_status",
            postgresql.ENUM(name="attachment_scan_status", create_type=False),
            nullable=False,
        ),
        sa.Column("scan_provider", sa.String(length=80), nullable=True),
        sa.Column("scan_engine_version", sa.String(length=80), nullable=True),
        sa.Column("scan_signature_version", sa.String(length=80), nullable=True),
        sa.Column("scan_threat", sa.String(length=160), nullable=True),
        sa.Column("scan_error_code", sa.String(length=80), nullable=True),
        sa.Column("scanned_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("encryption_key_version", sa.Integer(), nullable=True),
        sa.Column("encryption_algorithm", sa.String(length=40), nullable=True),
        sa.Column("encrypted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["oversight_action_id"], ["oversight_actions.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("storage_key"),
    )
    op.create_index("ix_oversight_evidence_tenant_id", "oversight_evidence", ["tenant_id"])
    op.create_index(
        "ix_oversight_evidence_action_id", "oversight_evidence", ["oversight_action_id"]
    )
    op.create_index("ix_oversight_evidence_type", "oversight_evidence", ["evidence_type"])
    op.create_index("ix_oversight_evidence_sha256", "oversight_evidence", ["sha256"])
    op.create_index("ix_oversight_evidence_created_at", "oversight_evidence", ["created_at"])
    if bind.dialect.name == "postgresql":
        app_user = os.getenv("APP_DB_USER", "gabflow_app")
        worker_user = os.getenv("WORKER_DB_USER", "gabflow_worker")
        op.execute(
            f"GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE oversight_evidence "
            f'TO "{app_user}", "{worker_user}"'
        )
        op.execute("ALTER TABLE oversight_evidence ENABLE ROW LEVEL SECURITY")
        op.execute("ALTER TABLE oversight_evidence FORCE ROW LEVEL SECURITY")
        op.execute(
            "CREATE POLICY oversight_evidence_tenant_isolation ON oversight_evidence FOR ALL "
            "USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid) "
            "WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)"
        )


def downgrade():
    op.drop_index("ix_oversight_evidence_created_at", table_name="oversight_evidence")
    op.drop_index("ix_oversight_evidence_sha256", table_name="oversight_evidence")
    op.drop_index("ix_oversight_evidence_type", table_name="oversight_evidence")
    op.drop_index("ix_oversight_evidence_action_id", table_name="oversight_evidence")
    op.drop_index("ix_oversight_evidence_tenant_id", table_name="oversight_evidence")
    op.drop_table("oversight_evidence")
    op.drop_index("ix_oversight_actions_agenda_event_id", table_name="oversight_actions")
    op.drop_constraint("fk_oversight_actions_agenda_event", "oversight_actions", type_="foreignkey")
    op.drop_column("oversight_actions", "agenda_event_id")
