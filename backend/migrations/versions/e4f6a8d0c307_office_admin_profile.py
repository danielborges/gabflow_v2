"""office admin profile

Revision ID: e4f6a8d0c307
Revises: e3f5a7c9d206
Create Date: 2026-07-21 16:15:00
"""

import sqlalchemy as sa
from alembic import op

revision = "e4f6a8d0c307"
down_revision = "e3f5a7c9d206"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "tenants",
        sa.Column("representative_info", sa.JSON(), nullable=False, server_default="{}"),
    )
    op.add_column("tenants", sa.Column("mandate_info", sa.JSON(), nullable=False, server_default="{}"))
    op.add_column(
        "tenants",
        sa.Column("visual_identity", sa.JSON(), nullable=False, server_default="{}"),
    )
    op.add_column("tenants", sa.Column("chief_of_staff_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_tenants_chief_of_staff_id_users",
        "tenants",
        "users",
        ["chief_of_staff_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_tenants_chief_of_staff_id", "tenants", ["chief_of_staff_id"])


def downgrade():
    op.drop_index("ix_tenants_chief_of_staff_id", table_name="tenants")
    op.drop_constraint("fk_tenants_chief_of_staff_id_users", "tenants", type_="foreignkey")
    op.drop_column("tenants", "chief_of_staff_id")
    op.drop_column("tenants", "visual_identity")
    op.drop_column("tenants", "mandate_info")
    op.drop_column("tenants", "representative_info")
