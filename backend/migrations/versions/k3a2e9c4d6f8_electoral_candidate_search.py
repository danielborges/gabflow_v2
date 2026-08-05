"""Add accent-insensitive electoral candidate search key.

Revision ID: k3a2e9c4d6f8
Revises: j2f1d8b3c5e7
"""

from alembic import op
import sqlalchemy as sa

revision = "k3a2e9c4d6f8"
down_revision = "j2f1d8b3c5e7"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "electoral_candidates",
        sa.Column("normalized_name", sa.String(length=430), nullable=True),
    )
    op.execute(
        """
        UPDATE electoral_candidates
        SET normalized_name = lower(translate(
            full_name || ' ' || ballot_name,
            'ÁÀÃÂÄÉÈÊËÍÌÎÏÓÒÕÔÖÚÙÛÜÇáàãâäéèêëíìîïóòõôöúùûüç',
            'AAAAAEEEEIIIIOOOOOUUUUCaaaaaeeeeiiiiooooouuuuc'
        ))
        """
    )
    op.alter_column("electoral_candidates", "normalized_name", nullable=False)
    op.create_index(
        "ix_electoral_candidates_normalized_name",
        "electoral_candidates",
        ["normalized_name"],
    )


def downgrade():
    op.drop_index(
        "ix_electoral_candidates_normalized_name",
        table_name="electoral_candidates",
    )
    op.drop_column("electoral_candidates", "normalized_name")
