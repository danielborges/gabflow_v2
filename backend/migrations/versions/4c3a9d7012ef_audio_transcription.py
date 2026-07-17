"""audio transcription

Revision ID: 4c3a9d7012ef
Revises: d93f4b7a2e61
Create Date: 2026-07-17 11:20:00

"""

import sqlalchemy as sa
from alembic import op

revision = "4c3a9d7012ef"
down_revision = "d93f4b7a2e61"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "audio_transcriptions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("attachment_id", sa.Uuid(), nullable=False),
        sa.Column("request_id", sa.Uuid(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "PENDENTE",
                "PROCESSANDO",
                "CONCLUIDA",
                "FALHOU",
                name="audio_transcription_status",
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
                name="audio_transcription_review_status",
            ),
            nullable=False,
        ),
        sa.Column("provider", sa.String(length=80), nullable=False),
        sa.Column("model", sa.String(length=120), nullable=False),
        sa.Column("language", sa.String(length=20), nullable=True),
        sa.Column("language_probability", sa.Float(), nullable=True),
        sa.Column("duration_seconds", sa.Float(), nullable=True),
        sa.Column("transcript", sa.Text(), nullable=True),
        sa.Column("reviewed_transcript", sa.Text(), nullable=True),
        sa.Column("segments", sa.JSON(), nullable=True),
        sa.Column("requested_by_id", sa.Uuid(), nullable=False),
        sa.Column("reviewed_by_id", sa.Uuid(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["attachment_id"],
            ["attachments.id"],
            name=op.f("fk_audio_transcriptions_attachment_id_attachments"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["request_id"],
            ["service_requests.id"],
            name=op.f("fk_audio_transcriptions_request_id_service_requests"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["requested_by_id"],
            ["users.id"],
            name=op.f("fk_audio_transcriptions_requested_by_id_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["reviewed_by_id"],
            ["users.id"],
            name=op.f("fk_audio_transcriptions_reviewed_by_id_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_audio_transcriptions_tenant_id_tenants"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audio_transcriptions")),
        sa.UniqueConstraint(
            "attachment_id", name=op.f("uq_audio_transcriptions_attachment_id")
        ),
    )
    with op.batch_alter_table("audio_transcriptions", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_audio_transcriptions_created_at"), ["created_at"])
        batch_op.create_index(batch_op.f("ix_audio_transcriptions_request_id"), ["request_id"])
        batch_op.create_index(
            batch_op.f("ix_audio_transcriptions_review_status"), ["review_status"]
        )
        batch_op.create_index(
            batch_op.f("ix_audio_transcriptions_reviewed_by_id"), ["reviewed_by_id"]
        )
        batch_op.create_index(batch_op.f("ix_audio_transcriptions_status"), ["status"])
        batch_op.create_index(batch_op.f("ix_audio_transcriptions_tenant_id"), ["tenant_id"])


def downgrade():
    with op.batch_alter_table("audio_transcriptions", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_audio_transcriptions_tenant_id"))
        batch_op.drop_index(batch_op.f("ix_audio_transcriptions_status"))
        batch_op.drop_index(batch_op.f("ix_audio_transcriptions_reviewed_by_id"))
        batch_op.drop_index(batch_op.f("ix_audio_transcriptions_review_status"))
        batch_op.drop_index(batch_op.f("ix_audio_transcriptions_request_id"))
        batch_op.drop_index(batch_op.f("ix_audio_transcriptions_created_at"))
    op.drop_table("audio_transcriptions")

    if op.get_bind().dialect.name == "postgresql":
        sa.Enum(name="audio_transcription_review_status").drop(
            op.get_bind(), checkfirst=True
        )
        sa.Enum(name="audio_transcription_status").drop(op.get_bind(), checkfirst=True)
