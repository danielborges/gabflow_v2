"""contracting interest operations

Revision ID: fb36d8e1a904
Revises: fa82c1d0e4b9
Create Date: 2026-07-22 15:45:00
"""

import sqlalchemy as sa
from alembic import op

revision = "fb36d8e1a904"
down_revision = "fa82c1d0e4b9"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "public_leads",
        sa.Column("onboarding_details", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
    )
    op.add_column(
        "public_leads",
        sa.Column("contract_documents", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
    )
    op.add_column(
        "public_leads",
        sa.Column("payments", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
    )
    op.add_column(
        "public_leads",
        sa.Column("action_history", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
    )
    op.add_column("public_leads", sa.Column("converted_tenant_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_public_leads_converted_tenant_id_tenants",
        "public_leads",
        "tenants",
        ["converted_tenant_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_public_leads_converted_tenant_id", "public_leads", ["converted_tenant_id"])
    op.alter_column("public_leads", "onboarding_details", server_default=None)
    op.alter_column("public_leads", "contract_documents", server_default=None)
    op.alter_column("public_leads", "payments", server_default=None)
    op.alter_column("public_leads", "action_history", server_default=None)


def downgrade():
    op.drop_index("ix_public_leads_converted_tenant_id", table_name="public_leads")
    op.drop_constraint("fk_public_leads_converted_tenant_id_tenants", "public_leads", type_="foreignkey")
    op.drop_column("public_leads", "converted_tenant_id")
    op.drop_column("public_leads", "action_history")
    op.drop_column("public_leads", "payments")
    op.drop_column("public_leads", "contract_documents")
    op.drop_column("public_leads", "onboarding_details")
