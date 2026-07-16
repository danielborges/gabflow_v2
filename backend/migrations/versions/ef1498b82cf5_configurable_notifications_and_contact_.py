"""configurable notifications and contact attempts

Revision ID: ef1498b82cf5
Revises: 7f8f0bd60ade
Create Date: 2026-07-16 15:04:47.574056
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "ef1498b82cf5"
down_revision = "7f8f0bd60ade"
branch_labels = None
depends_on = None


def upgrade():
    notification_type = postgresql.ENUM(
        "ATRIBUICAO",
        "TAREFA",
        "SLA",
        "SISTEMA",
        name="notification_type",
        create_type=False,
    )
    op.create_table(
        "notification_preferences",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("notification_type", notification_type, nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_notification_preferences_tenant_id_tenants"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_notification_preferences_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_notification_preferences")),
        sa.UniqueConstraint(
            "tenant_id",
            "user_id",
            "notification_type",
            name=op.f("uq_notification_preferences_tenant_id"),
        ),
    )
    with op.batch_alter_table("notification_preferences", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_notification_preferences_tenant_id"),
            ["tenant_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_notification_preferences_user_id"),
            ["user_id"],
            unique=False,
        )

    op.create_table(
        "contact_attempts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("request_id", sa.Uuid(), nullable=False),
        sa.Column("citizen_id", sa.Uuid(), nullable=True),
        sa.Column("channel", sa.String(length=30), nullable=False),
        sa.Column("destination", sa.String(length=254), nullable=False),
        sa.Column(
            "outcome",
            sa.Enum(
                "REALIZADO",
                "SEM_RESPOSTA",
                "FALHOU",
                "AGENDADO",
                name="contact_attempt_outcome",
            ),
            nullable=False,
        ),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("channel_override_reason", sa.Text(), nullable=True),
        sa.Column("attempted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["citizen_id"],
            ["citizens.id"],
            name=op.f("fk_contact_attempts_citizen_id_citizens"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_id"],
            ["users.id"],
            name=op.f("fk_contact_attempts_created_by_id_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["request_id"],
            ["service_requests.id"],
            name=op.f("fk_contact_attempts_request_id_service_requests"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_contact_attempts_tenant_id_tenants"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_contact_attempts")),
    )
    with op.batch_alter_table("contact_attempts", schema=None) as batch_op:
        for column in (
            "attempted_at",
            "citizen_id",
            "next_attempt_at",
            "outcome",
            "request_id",
            "tenant_id",
        ):
            batch_op.create_index(
                batch_op.f(f"ix_contact_attempts_{column}"),
                [column],
                unique=False,
            )


def downgrade():
    with op.batch_alter_table("contact_attempts", schema=None) as batch_op:
        for column in (
            "tenant_id",
            "request_id",
            "outcome",
            "next_attempt_at",
            "citizen_id",
            "attempted_at",
        ):
            batch_op.drop_index(batch_op.f(f"ix_contact_attempts_{column}"))
    op.drop_table("contact_attempts")

    with op.batch_alter_table("notification_preferences", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_notification_preferences_user_id"))
        batch_op.drop_index(batch_op.f("ix_notification_preferences_tenant_id"))
    op.drop_table("notification_preferences")

    if op.get_bind().dialect.name == "postgresql":
        postgresql.ENUM(name="contact_attempt_outcome").drop(
            op.get_bind(),
            checkfirst=True,
        )
