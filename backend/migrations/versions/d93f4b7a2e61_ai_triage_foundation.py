"""ai triage foundation

Revision ID: d93f4b7a2e61
Revises: c8d91e7a4b20
Create Date: 2026-07-16 17:05:00

"""

import sqlalchemy as sa
from alembic import op

revision = "d93f4b7a2e61"
down_revision = "c8d91e7a4b20"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "ai_executions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("request_id", sa.Uuid(), nullable=False),
        sa.Column("case_use", sa.String(length=80), nullable=False),
        sa.Column("provider", sa.String(length=80), nullable=False),
        sa.Column("model", sa.String(length=120), nullable=False),
        sa.Column("prompt_version", sa.String(length=40), nullable=False),
        sa.Column("input_hash", sa.String(length=64), nullable=False),
        sa.Column("output", sa.JSON(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "PENDENTE",
                "PROCESSANDO",
                "CONCLUIDA",
                "FALHOU",
                name="ai_execution_status",
            ),
            nullable=False,
        ),
        sa.Column(
            "review_status",
            sa.Enum(
                "PENDENTE",
                "ACEITA",
                "EDITADA",
                "REJEITADA",
                name="ai_review_status",
            ),
            nullable=False,
        ),
        sa.Column("requested_by_id", sa.Uuid(), nullable=False),
        sa.Column("reviewed_by_id", sa.Uuid(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("estimated_cost", sa.Float(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["request_id"],
            ["service_requests.id"],
            name=op.f("fk_ai_executions_request_id_service_requests"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["requested_by_id"],
            ["users.id"],
            name=op.f("fk_ai_executions_requested_by_id_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["reviewed_by_id"],
            ["users.id"],
            name=op.f("fk_ai_executions_reviewed_by_id_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_ai_executions_tenant_id_tenants"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ai_executions")),
    )
    with op.batch_alter_table("ai_executions", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_ai_executions_case_use"), ["case_use"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_ai_executions_created_at"), ["created_at"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_ai_executions_input_hash"), ["input_hash"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_ai_executions_request_id"), ["request_id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_ai_executions_review_status"), ["review_status"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_ai_executions_reviewed_by_id"), ["reviewed_by_id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_ai_executions_status"), ["status"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_ai_executions_tenant_id"), ["tenant_id"], unique=False
        )


def downgrade():
    with op.batch_alter_table("ai_executions", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_ai_executions_tenant_id"))
        batch_op.drop_index(batch_op.f("ix_ai_executions_status"))
        batch_op.drop_index(batch_op.f("ix_ai_executions_reviewed_by_id"))
        batch_op.drop_index(batch_op.f("ix_ai_executions_review_status"))
        batch_op.drop_index(batch_op.f("ix_ai_executions_request_id"))
        batch_op.drop_index(batch_op.f("ix_ai_executions_input_hash"))
        batch_op.drop_index(batch_op.f("ix_ai_executions_created_at"))
        batch_op.drop_index(batch_op.f("ix_ai_executions_case_use"))
    op.drop_table("ai_executions")

    if op.get_bind().dialect.name == "postgresql":
        sa.Enum(name="ai_review_status").drop(op.get_bind(), checkfirst=True)
        sa.Enum(name="ai_execution_status").drop(op.get_bind(), checkfirst=True)
