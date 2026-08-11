"""agenda google calendar

Revision ID: f4c8e2a6d0b1
Revises: f2b5d7e9a1c3
Create Date: 2026-08-11 10:40:00
"""

import sqlalchemy as sa
from alembic import op

revision = "f4c8e2a6d0b1"
down_revision = "f2b5d7e9a1c3"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "agenda_events",
        sa.Column(
            "representative_presence",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ),
    )


def downgrade():
    op.drop_column("agenda_events", "representative_presence")
