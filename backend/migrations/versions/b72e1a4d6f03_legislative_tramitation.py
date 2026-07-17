"""legislative tramitation

Revision ID: b72e1a4d6f03
Revises: a61d8f2c4e90
Create Date: 2026-07-17 11:30:00
"""

import uuid

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "b72e1a4d6f03"
down_revision = "a61d8f2c4e90"
branch_labels = None
depends_on = None

STATUS_VALUES = (
    "PROTOCOLADA",
    "DISTRIBUIDA",
    "EM_COMISSAO",
    "EM_PAUTA",
    "APROVADA",
    "REJEITADA",
    "SANCIONADA",
    "VETADA",
    "ARQUIVADA",
    "RETIRADA",
)


def _status_type():
    if op.get_bind().dialect.name == "postgresql":
        return postgresql.ENUM(
            *STATUS_VALUES,
            name="legislative_tramitation_status",
            create_type=False,
        )
    return sa.Enum(*STATUS_VALUES, name="legislative_tramitation_status")


def upgrade():
    if op.get_bind().dialect.name == "postgresql":
        postgresql.ENUM(
            *STATUS_VALUES,
            name="legislative_tramitation_status",
        ).create(op.get_bind(), checkfirst=True)

    status_type = _status_type()
    with op.batch_alter_table("legislative_drafts") as batch_op:
        batch_op.add_column(
            sa.Column("current_tramitation_status", status_type, nullable=True)
        )
        batch_op.create_index(
            "ix_legislative_drafts_current_tramitation_status",
            ["current_tramitation_status"],
        )

    op.create_table(
        "legislative_tramitations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("draft_id", sa.Uuid(), nullable=False),
        sa.Column("status", status_type, nullable=False),
        sa.Column("stage", sa.String(length=160), nullable=False),
        sa.Column("destination", sa.String(length=180), nullable=True),
        sa.Column("external_reference", sa.String(length=180), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["draft_id"], ["legislative_drafts.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ("tenant_id", "draft_id", "status", "occurred_at", "created_at"):
        op.create_index(
            f"ix_legislative_tramitations_{column}",
            "legislative_tramitations",
            [column],
        )

    bind = op.get_bind()
    metadata = sa.MetaData()
    drafts = sa.Table("legislative_drafts", metadata, autoload_with=bind)
    tramitations = sa.Table("legislative_tramitations", metadata, autoload_with=bind)
    existing_protocols = bind.execute(
        sa.select(
            drafts.c.id,
            drafts.c.tenant_id,
            drafts.c.protocol_number,
            drafts.c.protocolled_at,
            drafts.c.created_by_id,
        ).where(drafts.c.protocol_number.is_not(None))
    ).mappings()
    for draft in existing_protocols:
        occurred_at = draft["protocolled_at"] or sa.func.now()
        bind.execute(
            tramitations.insert().values(
                id=uuid.uuid4(),
                tenant_id=draft["tenant_id"],
                draft_id=draft["id"],
                status="PROTOCOLADA",
                stage="Protocolo",
                external_reference=draft["protocol_number"],
                occurred_at=occurred_at,
                created_by_id=draft["created_by_id"],
                created_at=occurred_at,
            )
        )
        bind.execute(
            drafts.update()
            .where(drafts.c.id == draft["id"])
            .values(current_tramitation_status="PROTOCOLADA")
        )


def downgrade():
    op.drop_table("legislative_tramitations")
    with op.batch_alter_table("legislative_drafts") as batch_op:
        batch_op.drop_index("ix_legislative_drafts_current_tramitation_status")
        batch_op.drop_column("current_tramitation_status")
    if op.get_bind().dialect.name == "postgresql":
        postgresql.ENUM(name="legislative_tramitation_status").drop(
            op.get_bind(), checkfirst=True
        )
