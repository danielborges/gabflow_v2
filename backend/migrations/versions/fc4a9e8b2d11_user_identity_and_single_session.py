"""user identity and single session

Revision ID: fc4a9e8b2d11
Revises: fb36d8e1a904
Create Date: 2026-07-23 10:20:00
"""

import sqlalchemy as sa
from alembic import op

revision = "fc4a9e8b2d11"
down_revision = "fb36d8e1a904"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("users", sa.Column("cpf", sa.String(length=11), nullable=True))
    op.add_column("users", sa.Column("phone", sa.String(length=20), nullable=True))
    op.add_column("users", sa.Column("current_session_id", sa.String(length=64), nullable=True))
    op.create_unique_constraint("uq_users_email", "users", ["email"])
    op.create_unique_constraint("uq_users_cpf", "users", ["cpf"])
    op.create_index("ix_users_cpf", "users", ["cpf"])


def downgrade():
    op.drop_index("ix_users_cpf", table_name="users")
    op.drop_constraint("uq_users_cpf", "users", type_="unique")
    op.drop_constraint("uq_users_email", "users", type_="unique")
    op.drop_column("users", "current_session_id")
    op.drop_column("users", "phone")
    op.drop_column("users", "cpf")
