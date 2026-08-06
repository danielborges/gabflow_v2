"""Add assisted channel identity review queue.

Revision ID: e4c9a6b8d0f2
Revises: d3b8f5a7c9e1
"""

import os

import sqlalchemy as sa
from alembic import op

revision = "e4c9a6b8d0f2"
down_revision = "d3b8f5a7c9e1"
branch_labels = None
depends_on = None


def upgrade():
    op.create_unique_constraint(
        "uq_channel_messages_tenant_id_id",
        "channel_messages",
        ["tenant_id", "id"],
    )
    op.create_unique_constraint(
        "uq_channel_messages_tenant_channel_external",
        "channel_messages",
        ["tenant_id", "channel", "external_id"],
    )
    review_status = sa.Enum(
        "PENDENTE",
        "VINCULADA",
        "DESCARTADA",
        name="channel_identity_review_status",
    )
    op.create_table(
        "channel_identity_reviews",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("message_id", sa.Uuid(), nullable=False),
        sa.Column("status", review_status, nullable=False),
        sa.Column("resolution_state", sa.String(length=40), nullable=False),
        sa.Column("candidate_citizen_ids", sa.JSON(), nullable=False),
        sa.Column("match_basis", sa.JSON(), nullable=False),
        sa.Column("selected_citizen_id", sa.Uuid(), nullable=True),
        sa.Column("reviewed_by_id", sa.Uuid(), nullable=True),
        sa.Column("review_note", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["tenant_id", "message_id"],
            ["channel_messages.tenant_id", "channel_messages.id"],
            name="fk_channel_identity_reviews_tenant_message",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "selected_citizen_id"],
            ["citizens.tenant_id", "citizens.id"],
            name="fk_channel_identity_reviews_tenant_citizen",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "reviewed_by_id"],
            ["users.tenant_id", "users.id"],
            name="fk_channel_identity_reviews_tenant_reviewer",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id", "id", name="uq_channel_identity_reviews_tenant_id_id"
        ),
        sa.UniqueConstraint(
            "tenant_id", "message_id", name="uq_channel_identity_reviews_tenant_message"
        ),
    )
    for column in (
        "tenant_id",
        "message_id",
        "status",
        "resolution_state",
        "selected_citizen_id",
        "reviewed_by_id",
        "created_at",
        "reviewed_at",
    ):
        op.create_index(
            f"ix_channel_identity_reviews_{column}",
            "channel_identity_reviews",
            [column],
        )

    if op.get_bind().dialect.name == "postgresql":
        tenant = "current_setting('app.tenant_id', true)::uuid"
        op.execute("ALTER TABLE channel_identity_reviews ENABLE ROW LEVEL SECURITY")
        op.execute("ALTER TABLE channel_identity_reviews FORCE ROW LEVEL SECURITY")
        op.execute(
            "CREATE POLICY channel_identity_reviews_tenant_isolation "
            "ON channel_identity_reviews FOR ALL "
            f"USING (tenant_id = {tenant}) WITH CHECK (tenant_id = {tenant})"
        )
        roles = {
            os.getenv("APP_DB_USER", "gabflow_app"),
            os.getenv("WORKER_DB_USER", "gabflow_worker"),
        }
        available = {
            row[0]
            for row in op.get_bind().execute(
                sa.text("SELECT rolname FROM pg_roles WHERE rolname = ANY(:roles)"),
                {"roles": list(roles)},
            )
        }
        for role in roles & available:
            op.execute(
                sa.text(
                    f'GRANT SELECT, INSERT, UPDATE ON TABLE channel_identity_reviews TO "{role}"'
                )
            )


def downgrade():
    op.drop_table("channel_identity_reviews")
    sa.Enum(name="channel_identity_review_status").drop(op.get_bind(), checkfirst=True)
    op.drop_constraint(
        "uq_channel_messages_tenant_channel_external",
        "channel_messages",
        type_="unique",
    )
    op.drop_constraint(
        "uq_channel_messages_tenant_id_id",
        "channel_messages",
        type_="unique",
    )
