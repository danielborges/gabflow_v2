"""Add private electoral analysis and versioned official geometry.

Revision ID: l4b3f0d5e7a9
Revises: k3a2e9c4d6f8
"""

import os

import sqlalchemy as sa
from alembic import op

revision = "l4b3f0d5e7a9"
down_revision = "k3a2e9c4d6f8"
branch_labels = None
depends_on = None

PRIVATE_TABLES = (
    "electoral_identity_reviews",
    "electoral_favorites",
    "electoral_saved_comparisons",
)
GLOBAL_TABLES = (
    "electoral_geometry_versions",
    "electoral_geometry_features",
    "electoral_territory_crosswalks",
)


def upgrade():
    op.create_table(
        "electoral_identity_reviews",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("subject_candidate_id", sa.Uuid(), nullable=False),
        sa.Column("linked_candidate_id", sa.Uuid(), nullable=False),
        sa.Column("decision", sa.String(20), nullable=False),
        sa.Column("method", sa.String(40), nullable=False),
        sa.Column("notes", sa.String(500)),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "subject_candidate_id <> linked_candidate_id",
            name="ck_electoral_identity_review_distinct_candidates",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "user_id"],
            ["users.tenant_id", "users.id"],
            ondelete="CASCADE",
            name="fk_electoral_identity_reviews_tenant_user",
        ),
        sa.ForeignKeyConstraint(
            ["subject_candidate_id"], ["electoral_candidates.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["linked_candidate_id"], ["electoral_candidates.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "user_id",
            "subject_candidate_id",
            "linked_candidate_id",
            name="uq_electoral_identity_review_user_pair",
        ),
    )
    _indexes(
        "electoral_identity_reviews",
        "tenant_id",
        "user_id",
        "subject_candidate_id",
        "linked_candidate_id",
    )

    op.create_table(
        "electoral_favorites",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("target_type", sa.String(30), nullable=False),
        sa.Column("target_id", sa.String(80), nullable=False),
        sa.Column("label", sa.String(160), nullable=False),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id", "user_id"],
            ["users.tenant_id", "users.id"],
            ondelete="CASCADE",
            name="fk_electoral_favorites_tenant_user",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "user_id",
            "target_type",
            "target_id",
            name="uq_electoral_favorite_user_target",
        ),
    )
    _indexes("electoral_favorites", "tenant_id", "user_id")

    op.create_table(
        "electoral_saved_comparisons",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("election_id", sa.Uuid(), nullable=False),
        sa.Column("candidate_ids", sa.JSON(), nullable=False),
        sa.Column("level", sa.String(30), nullable=False),
        sa.Column("municipality_code", sa.String(10)),
        sa.Column("filters", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id", "user_id"],
            ["users.tenant_id", "users.id"],
            ondelete="CASCADE",
            name="fk_electoral_saved_comparisons_tenant_user",
        ),
        sa.ForeignKeyConstraint(["election_id"], ["electoral_elections.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    _indexes("electoral_saved_comparisons", "tenant_id", "user_id", "election_id")

    op.create_table(
        "electoral_geometry_versions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("source_name", sa.String(160), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("source_hash", sa.String(64), nullable=False),
        sa.Column("reference_year", sa.Integer(), nullable=False),
        sa.Column("uf", sa.String(2), nullable=False),
        sa.Column("level", sa.String(30), nullable=False),
        sa.Column("quality", sa.String(30), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("feature_count", sa.Integer(), nullable=False),
        sa.Column("raw_storage_path", sa.Text(), nullable=False),
        sa.Column("source_metadata", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "source_hash",
            "reference_year",
            "uf",
            "level",
            "quality",
            name="uq_electoral_geometry_source_coverage",
        ),
    )
    _indexes(
        "electoral_geometry_versions",
        "source_hash",
        "reference_year",
        "uf",
        "level",
        "status",
        "published_at",
    )

    op.create_table(
        "electoral_geometry_features",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("geometry_version_id", sa.Uuid(), nullable=False),
        sa.Column("official_code", sa.String(12), nullable=False),
        sa.Column("name", sa.String(180), nullable=False),
        sa.Column("normalized_name", sa.String(180), nullable=False),
        sa.Column("geometry_type", sa.String(30), nullable=False),
        sa.Column("geometry_geojson", sa.JSON(), nullable=False),
        sa.Column("bbox", sa.JSON(), nullable=False),
        sa.Column("derived", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(
            ["geometry_version_id"], ["electoral_geometry_versions.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "geometry_version_id",
            "official_code",
            name="uq_electoral_geometry_feature_version_code",
        ),
    )
    _indexes(
        "electoral_geometry_features",
        "geometry_version_id",
        "official_code",
        "normalized_name",
    )
    op.execute(
        "ALTER TABLE electoral_geometry_features "
        "ADD COLUMN geometry geometry(MultiPolygon, 4326)"
    )
    op.execute(
        "CREATE INDEX ix_electoral_geometry_features_geometry_gist "
        "ON electoral_geometry_features USING GIST (geometry)"
    )

    op.create_table(
        "electoral_territory_crosswalks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("geometry_version_id", sa.Uuid(), nullable=False),
        sa.Column("geometry_feature_id", sa.Uuid(), nullable=False),
        sa.Column("electoral_code", sa.String(10), nullable=False),
        sa.Column("official_code", sa.String(12), nullable=False),
        sa.Column("method", sa.String(40), nullable=False),
        sa.Column("reviewed", sa.Boolean(), nullable=False),
        sa.Column("review_notes", sa.String(500)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["geometry_version_id"], ["electoral_geometry_versions.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["geometry_feature_id"], ["electoral_geometry_features.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "geometry_version_id",
            "electoral_code",
            name="uq_electoral_crosswalk_version_electoral_code",
        ),
    )
    _indexes(
        "electoral_territory_crosswalks",
        "geometry_version_id",
        "geometry_feature_id",
        "electoral_code",
        "official_code",
    )
    _enable_private_rls()
    _grant_runtime_access()


def downgrade():
    for table in PRIVATE_TABLES:
        op.execute(f"DROP POLICY IF EXISTS {table}_private_isolation ON {table}")
    op.drop_table("electoral_territory_crosswalks")
    op.drop_index("ix_electoral_geometry_features_geometry_gist", table_name="electoral_geometry_features")
    op.drop_table("electoral_geometry_features")
    op.drop_table("electoral_geometry_versions")
    op.drop_table("electoral_saved_comparisons")
    op.drop_table("electoral_favorites")
    op.drop_table("electoral_identity_reviews")


def _indexes(table: str, *columns: str) -> None:
    for column in columns:
        op.create_index(f"ix_{table}_{column}", table, [column])


def _enable_private_rls() -> None:
    for table in PRIVATE_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"""
            CREATE POLICY {table}_private_isolation ON {table} FOR ALL
            USING (
                tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
                AND user_id = NULLIF(current_setting('app.user_id', true), '')::uuid
            )
            WITH CHECK (
                tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
                AND user_id = NULLIF(current_setting('app.user_id', true), '')::uuid
            )
            """
        )


def _grant_runtime_access() -> None:
    bind = op.get_bind()
    roles = {
        os.getenv("APP_DB_USER", "gabflow_app"),
        os.getenv("WORKER_DB_USER", "gabflow_worker"),
    }
    available = {
        row[0]
        for row in bind.execute(
            sa.text("SELECT rolname FROM pg_roles WHERE rolname = ANY(:roles)"),
            {"roles": list(roles)},
        )
    }
    for role in roles & available:
        for table in PRIVATE_TABLES:
            op.execute(sa.text(f'GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE {table} TO "{role}"'))
        for table in GLOBAL_TABLES:
            op.execute(sa.text(f'GRANT SELECT ON TABLE {table} TO "{role}"'))
