"""Add territorial location provenance and quality.

Revision ID: a6e1c8d0f2b4
Revises: f5d0b7c9e1a3
"""

import sqlalchemy as sa
from alembic import op

revision = "a6e1c8d0f2b4"
down_revision = "f5d0b7c9e1a3"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("service_requests", sa.Column("geocode_source", sa.String(80)))
    op.add_column("service_requests", sa.Column("geocode_method", sa.String(40)))
    op.add_column("service_requests", sa.Column("geocode_confidence", sa.Float()))
    op.add_column(
        "service_requests",
        sa.Column("geocode_verified", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    op.add_column(
        "service_requests",
        sa.Column(
            "geocode_status",
            sa.String(30),
            server_default="UNRESOLVED",
            nullable=False,
        ),
    )
    op.add_column(
        "service_requests", sa.Column("geocoded_at", sa.DateTime(timezone=True))
    )
    op.create_index(
        "ix_service_requests_geocode_status", "service_requests", ["geocode_status"]
    )
    op.execute(
        """
        UPDATE service_requests
        SET geocode_source = CASE
                WHEN latitude IS NOT NULL AND longitude IS NOT NULL THEN 'LEGACY_IMPORT'
                ELSE NULL
            END,
            geocode_method = CASE
                WHEN latitude IS NOT NULL AND longitude IS NOT NULL THEN 'LEGACY'
                ELSE NULL
            END,
            geocode_status = CASE
                WHEN latitude IS NOT NULL AND longitude IS NOT NULL THEN 'APPROXIMATE'
                ELSE 'UNRESOLVED'
            END,
            geocode_confidence = CASE
                WHEN latitude IS NOT NULL AND longitude IS NOT NULL THEN 0.5
                ELSE NULL
            END
        """
    )


def downgrade():
    op.drop_index("ix_service_requests_geocode_status", table_name="service_requests")
    op.drop_column("service_requests", "geocoded_at")
    op.drop_column("service_requests", "geocode_status")
    op.drop_column("service_requests", "geocode_verified")
    op.drop_column("service_requests", "geocode_confidence")
    op.drop_column("service_requests", "geocode_method")
    op.drop_column("service_requests", "geocode_source")
