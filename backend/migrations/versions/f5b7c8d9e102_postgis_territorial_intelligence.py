"""postgis territorial intelligence

Revision ID: f5b7c8d9e102
Revises: e7b6d9c2a8f1
Create Date: 2026-07-20 15:35:00
"""

from alembic import op

revision = "f5b7c8d9e102"
down_revision = "e7b6d9c2a8f1"
branch_labels = None
depends_on = None


def upgrade():
    if op.get_bind().dialect.name != "postgresql":
        return

    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")
    op.execute(
        """
        ALTER TABLE service_requests
        ADD COLUMN location_geography geography(Point, 4326)
        GENERATED ALWAYS AS (
            CASE
                WHEN latitude IS NOT NULL AND longitude IS NOT NULL
                THEN ST_SetSRID(ST_MakePoint(longitude, latitude), 4326)::geography
                ELSE NULL
            END
        ) STORED
        """
    )
    op.execute(
        """
        CREATE INDEX ix_service_requests_location_geography
        ON service_requests
        USING GIST (location_geography)
        WHERE location_geography IS NOT NULL
        """
    )


def downgrade():
    if op.get_bind().dialect.name != "postgresql":
        return

    op.execute("DROP INDEX IF EXISTS ix_service_requests_location_geography")
    op.execute("ALTER TABLE service_requests DROP COLUMN IF EXISTS location_geography")
