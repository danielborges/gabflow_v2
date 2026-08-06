"""Add aliases and administrative geometry to operational territories.

Revision ID: c2a7e4f6b8d0
Revises: b1f9c7d3e5a2
"""

import sqlalchemy as sa
from alembic import op

revision = "c2a7e4f6b8d0"
down_revision = "b1f9c7d3e5a2"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("territories") as batch_op:
        batch_op.add_column(
            sa.Column("aliases", sa.JSON(), nullable=False, server_default=sa.text("'[]'"))
        )
        batch_op.add_column(sa.Column("geometry", sa.JSON()))


def downgrade():
    with op.batch_alter_table("territories") as batch_op:
        batch_op.drop_column("geometry")
        batch_op.drop_column("aliases")
