"""Add WhatsApp pilot controls, gates and ACK telemetry.

Revision ID: b7d8e9f0a1c2
Revises: a6c7d8e9f0b1
"""

import sqlalchemy as sa
from alembic import op

revision = "b7d8e9f0a1c2"
down_revision = "a6c7d8e9f0b1"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("whatsapp_webhook_events") as batch:
        batch.add_column(sa.Column("ack_duration_ms", sa.Integer()))
        batch.create_index("ix_whatsapp_webhook_events_ack_duration_ms", ["ack_duration_ms"])

    op.create_table(
        "whatsapp_pilot_controls",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("outbound_paused", sa.Boolean(), nullable=False),
        sa.Column("pilot_started_at", sa.DateTime(timezone=True)),
        sa.Column("pilot_completed_at", sa.DateTime(timezone=True)),
        sa.Column("pause_reason", sa.String(500)),
        sa.Column("updated_by_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('DRAFT', 'READY', 'RUNNING', 'PAUSED', 'COMPLETED')",
            name="ck_whatsapp_pilot_control_status",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "updated_by_id"],
            ["users.tenant_id", "users.id"],
            ondelete="RESTRICT",
            name="fk_whatsapp_pilot_control_tenant_actor",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", name="uq_whatsapp_pilot_control_tenant"),
    )
    op.create_index(
        "ix_whatsapp_pilot_controls_tenant_id", "whatsapp_pilot_controls", ["tenant_id"]
    )
    op.create_index("ix_whatsapp_pilot_controls_status", "whatsapp_pilot_controls", ["status"])
    op.create_index(
        "ix_whatsapp_pilot_controls_updated_by_id", "whatsapp_pilot_controls", ["updated_by_id"]
    )

    op.create_table(
        "whatsapp_pilot_gates",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("gate_key", sa.String(80), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("evidence_reference", sa.String(500)),
        sa.Column("evidence_hash", sa.String(64)),
        sa.Column("notes", sa.String(500)),
        sa.Column("reviewed_by_id", sa.Uuid(), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('PENDING', 'PASSED', 'FAILED')",
            name="ck_whatsapp_pilot_gate_status",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "reviewed_by_id"],
            ["users.tenant_id", "users.id"],
            ondelete="RESTRICT",
            name="fk_whatsapp_pilot_gate_tenant_reviewer",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "gate_key", name="uq_whatsapp_pilot_gate_key"),
    )
    for column in ("tenant_id", "gate_key", "status", "reviewed_by_id", "expires_at"):
        op.create_index(f"ix_whatsapp_pilot_gates_{column}", "whatsapp_pilot_gates", [column])


def downgrade():
    op.drop_table("whatsapp_pilot_gates")
    op.drop_table("whatsapp_pilot_controls")
    with op.batch_alter_table("whatsapp_webhook_events") as batch:
        batch.drop_index("ix_whatsapp_webhook_events_ack_duration_ms")
        batch.drop_column("ack_duration_ms")
