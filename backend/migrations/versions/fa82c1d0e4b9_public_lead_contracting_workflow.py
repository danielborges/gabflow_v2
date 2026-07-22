"""public lead contracting workflow

Revision ID: fa82c1d0e4b9
Revises: f7d2a1c4b6e8
Create Date: 2026-07-22 15:25:00
"""

import sqlalchemy as sa
from alembic import op

revision = "fa82c1d0e4b9"
down_revision = "f7d2a1c4b6e8"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("public_leads", sa.Column("admin_name", sa.String(length=160), nullable=True))
    op.add_column("public_leads", sa.Column("whatsapp", sa.String(length=40), nullable=True))
    op.add_column("public_leads", sa.Column("municipality_ibge_id", sa.Integer(), nullable=True))
    op.add_column("public_leads", sa.Column("preferred_contact", sa.String(length=30), nullable=True))
    op.add_column("public_leads", sa.Column("discovery_source", sa.String(length=80), nullable=True))
    op.add_column("public_leads", sa.Column("payment_status", sa.String(length=40), nullable=True))
    op.add_column("public_leads", sa.Column("onboarding_date", sa.Date(), nullable=True))
    op.add_column(
        "public_leads",
        sa.Column("contact_attempts", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
    )
    op.add_column("public_leads", sa.Column("contract_notes", sa.Text(), nullable=True))
    op.add_column(
        "public_leads",
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.alter_column("public_leads", "contact_attempts", server_default=None)
    op.alter_column("public_leads", "updated_at", server_default=None)


def downgrade():
    op.drop_column("public_leads", "updated_at")
    op.drop_column("public_leads", "contract_notes")
    op.drop_column("public_leads", "contact_attempts")
    op.drop_column("public_leads", "onboarding_date")
    op.drop_column("public_leads", "payment_status")
    op.drop_column("public_leads", "discovery_source")
    op.drop_column("public_leads", "preferred_contact")
    op.drop_column("public_leads", "municipality_ibge_id")
    op.drop_column("public_leads", "whatsapp")
    op.drop_column("public_leads", "admin_name")
