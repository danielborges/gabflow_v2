"""Add versioned polling-place and section electoral results.

Revision ID: w6a4e1b9c3d5
Revises: v5f3d0a8b2c4
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "w6a4e1b9c3d5"
down_revision = "v5f3d0a8b2c4"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "electoral_territorial_dataset_versions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("dataset_version_id", sa.Uuid(), nullable=False),
        sa.Column("section_source_url", sa.Text(), nullable=False),
        sa.Column("section_source_hash", sa.String(length=64), nullable=False),
        sa.Column("location_source_url", sa.Text(), nullable=False),
        sa.Column("location_source_hash", sa.String(length=64), nullable=False),
        sa.Column("parser_version", sa.String(length=40), nullable=False),
        sa.Column(
            "status",
            postgresql.ENUM(
                "DISCOVERED",
                "DOWNLOADED",
                "PARSED",
                "VALIDATED",
                "PUBLISHED",
                "REJECTED",
                "SUPERSEDED",
                name="electoral_dataset_status",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("validation_manifest", sa.JSON(), nullable=False),
        sa.Column("section_storage_path", sa.Text(), nullable=False),
        sa.Column("location_storage_path", sa.Text(), nullable=False),
        sa.Column("row_count", sa.BigInteger(), nullable=False),
        sa.Column("invalid_rows", sa.BigInteger(), nullable=False),
        sa.Column("total_votes", sa.BigInteger(), nullable=False),
        sa.Column("quality_score", sa.Float(), nullable=True),
        sa.Column("downloaded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("validated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["dataset_version_id"], ["electoral_dataset_versions.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "dataset_version_id",
            "section_source_hash",
            "location_source_hash",
            "parser_version",
            name="uq_electoral_territorial_dataset_sources",
        ),
    )
    for column in (
        "dataset_version_id",
        "section_source_hash",
        "location_source_hash",
        "status",
        "published_at",
    ):
        op.create_index(
            f"ix_electoral_territorial_dataset_versions_{column}",
            "electoral_territorial_dataset_versions",
            [column],
        )

    op.create_table(
        "electoral_territorial_units",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("territorial_dataset_version_id", sa.Uuid(), nullable=False),
        sa.Column("uf", sa.String(length=2), nullable=False),
        sa.Column("municipality_code", sa.String(length=10), nullable=False),
        sa.Column("municipality_name", sa.String(length=180), nullable=False),
        sa.Column("zone", sa.Integer(), nullable=False),
        sa.Column("section", sa.Integer(), nullable=False),
        sa.Column("polling_place_number", sa.Integer(), nullable=False),
        sa.Column("polling_place_name", sa.String(length=240), nullable=False),
        sa.Column("polling_place_address", sa.Text(), nullable=True),
        sa.Column("neighborhood", sa.String(length=180), nullable=True),
        sa.Column("latitude", sa.Float(), nullable=True),
        sa.Column("longitude", sa.Float(), nullable=True),
        sa.Column("mapping_type", sa.String(length=30), nullable=False),
        sa.Column("mapping_metadata", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(
            ["territorial_dataset_version_id"],
            ["electoral_territorial_dataset_versions.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "territorial_dataset_version_id",
            "municipality_code",
            "zone",
            "section",
            name="uq_electoral_territorial_unit_section",
        ),
    )
    for column in (
        "territorial_dataset_version_id",
        "uf",
        "municipality_code",
        "neighborhood",
    ):
        op.create_index(
            f"ix_electoral_territorial_units_{column}",
            "electoral_territorial_units",
            [column],
        )

    op.create_table(
        "electoral_section_results",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("territorial_dataset_version_id", sa.Uuid(), nullable=False),
        sa.Column("candidacy_id", sa.Uuid(), nullable=False),
        sa.Column("territory_id", sa.Uuid(), nullable=False),
        sa.Column("votes", sa.Integer(), nullable=False),
        sa.CheckConstraint("votes >= 0", name="ck_electoral_section_results_votes_nonnegative"),
        sa.ForeignKeyConstraint(
            ["candidacy_id"], ["electoral_candidacies.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["territorial_dataset_version_id"],
            ["electoral_territorial_dataset_versions.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["territory_id"], ["electoral_territorial_units.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "territorial_dataset_version_id",
            "candidacy_id",
            "territory_id",
            name="uq_electoral_section_result_candidacy_territory",
        ),
    )
    for column in ("territorial_dataset_version_id", "candidacy_id", "territory_id"):
        op.create_index(
            f"ix_electoral_section_results_{column}",
            "electoral_section_results",
            [column],
        )


def downgrade():
    op.drop_table("electoral_section_results")
    op.drop_table("electoral_territorial_units")
    op.drop_table("electoral_territorial_dataset_versions")
