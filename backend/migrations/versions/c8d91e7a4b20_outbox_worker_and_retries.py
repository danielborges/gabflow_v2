"""outbox worker and retries

Revision ID: c8d91e7a4b20
Revises: 9e9623dd52f3
Create Date: 2026-07-16 16:45:00

"""

import sqlalchemy as sa
from alembic import op

revision = "c8d91e7a4b20"
down_revision = "9e9623dd52f3"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("outbox_events", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "available_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("CURRENT_TIMESTAMP"),
                nullable=False,
            )
        )
        batch_op.add_column(
            sa.Column("attempt_count", sa.Integer(), server_default="0", nullable=False)
        )
        batch_op.add_column(sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("locked_by", sa.String(length=120), nullable=True))
        batch_op.add_column(sa.Column("last_error", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("failed_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.create_index(
            batch_op.f("ix_outbox_events_available_at"), ["available_at"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_outbox_events_failed_at"), ["failed_at"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_outbox_events_locked_at"), ["locked_at"], unique=False
        )

    with op.batch_alter_table("contact_attempts", schema=None) as batch_op:
        batch_op.add_column(sa.Column("source_event_id", sa.Uuid(), nullable=True))
        batch_op.create_foreign_key(
            batch_op.f("fk_contact_attempts_source_event_id_outbox_events"),
            "outbox_events",
            ["source_event_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_index(
            batch_op.f("ix_contact_attempts_source_event_id"),
            ["source_event_id"],
            unique=True,
        )


def downgrade():
    with op.batch_alter_table("contact_attempts", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_contact_attempts_source_event_id"))
        batch_op.drop_constraint(
            batch_op.f("fk_contact_attempts_source_event_id_outbox_events"),
            type_="foreignkey",
        )
        batch_op.drop_column("source_event_id")

    with op.batch_alter_table("outbox_events", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_outbox_events_locked_at"))
        batch_op.drop_index(batch_op.f("ix_outbox_events_failed_at"))
        batch_op.drop_index(batch_op.f("ix_outbox_events_available_at"))
        batch_op.drop_column("failed_at")
        batch_op.drop_column("last_error")
        batch_op.drop_column("locked_by")
        batch_op.drop_column("locked_at")
        batch_op.drop_column("attempt_count")
        batch_op.drop_column("available_at")
