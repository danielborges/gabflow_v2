"""public landing leads

Revision ID: f6c1d2e3a4b5
Revises: e5a9b1c2d304
Create Date: 2026-07-21 17:25:00
"""

import sqlalchemy as sa
from alembic import op

revision = "f6c1d2e3a4b5"
down_revision = "e5a9b1c2d304"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "public_leads",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("plan", sa.String(length=40), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("organization", sa.String(length=180), nullable=False),
        sa.Column("email", sa.String(length=254), nullable=False),
        sa.Column("phone", sa.String(length=40), nullable=True),
        sa.Column("city", sa.String(length=120), nullable=True),
        sa.Column("state", sa.String(length=2), nullable=True),
        sa.Column("audience", sa.String(length=80), nullable=True),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=40), nullable=False, server_default="new"),
        sa.Column("source", sa.String(length=80), nullable=False, server_default="landing_page"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_public_leads_email", "public_leads", ["email"])
    op.create_index("ix_public_leads_plan", "public_leads", ["plan"])
    op.create_index("ix_public_leads_status", "public_leads", ["status"])


def downgrade():
    op.drop_index("ix_public_leads_status", table_name="public_leads")
    op.drop_index("ix_public_leads_plan", table_name="public_leads")
    op.drop_index("ix_public_leads_email", table_name="public_leads")
    op.drop_table("public_leads")
