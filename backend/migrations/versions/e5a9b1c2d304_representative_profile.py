"""representative profile

Revision ID: e5a9b1c2d304
Revises: e4f6a8d0c307
Create Date: 2026-07-21 18:45:00
"""

from alembic import op

revision = "e5a9b1c2d304"
down_revision = "e4f6a8d0c307"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("ALTER TYPE user_role ADD VALUE IF NOT EXISTS 'REPRESENTATIVE'")


def downgrade():
    pass
