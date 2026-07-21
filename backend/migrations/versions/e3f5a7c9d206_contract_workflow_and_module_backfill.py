"""contract workflow and module backfill

Revision ID: e3f5a7c9d206
Revises: e2f4a6c8d105
Create Date: 2026-07-21 15:35:00
"""

import json

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "e3f5a7c9d206"
down_revision = "e2f4a6c8d105"
branch_labels = None
depends_on = None

DEFAULT_MODULES = [
    "agenda",
    "canais",
    "cidadaos",
    "documentos",
    "fiscalizacao",
    "ia",
    "integracoes",
    "privacidade",
    "rag",
    "solicitacoes",
]


def upgrade():
    bind = op.get_bind()
    contract_status = (
        postgresql.ENUM(name="contract_status", create_type=False)
        if bind.dialect.name == "postgresql"
        else sa.Enum(name="contract_status")
    )
    op.create_table(
        "platform_contract_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column(
            "previous_status",
            contract_status,
            nullable=True,
        ),
        sa.Column(
            "new_status",
            contract_status,
            nullable=False,
        ),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("effective_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_platform_contract_events_tenant_id", "platform_contract_events", ["tenant_id"])
    op.create_index(
        "ix_platform_contract_events_created_by_id",
        "platform_contract_events",
        ["created_by_id"],
    )
    op.create_index(
        "ix_platform_contract_events_created_at",
        "platform_contract_events",
        ["created_at"],
    )
    modules_json = json.dumps(DEFAULT_MODULES)
    if bind.dialect.name == "postgresql":
        bind.execute(
            sa.text(
                "UPDATE tenants SET enabled_modules = CAST(:modules AS json) "
                "WHERE enabled_modules IS NULL OR enabled_modules::text = '[]'"
            ),
            {"modules": modules_json},
        )
    else:
        bind.execute(
            sa.text(
                "UPDATE tenants SET enabled_modules = :modules "
                "WHERE enabled_modules IS NULL OR enabled_modules = '[]'"
            ),
            {"modules": modules_json},
        )


def downgrade():
    op.drop_index("ix_platform_contract_events_created_at", table_name="platform_contract_events")
    op.drop_index("ix_platform_contract_events_created_by_id", table_name="platform_contract_events")
    op.drop_index("ix_platform_contract_events_tenant_id", table_name="platform_contract_events")
    op.drop_table("platform_contract_events")
