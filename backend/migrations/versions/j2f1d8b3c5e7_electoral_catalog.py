"""Add versioned electoral catalog and staging tables.

Revision ID: j2f1d8b3c5e7
Revises: i1e0c7a2b4d6
"""

import os

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "j2f1d8b3c5e7"
down_revision = "i1e0c7a2b4d6"
branch_labels = None
depends_on = None

DATASET_STATUSES = (
    "DISCOVERED",
    "DOWNLOADED",
    "PARSED",
    "VALIDATED",
    "PUBLISHED",
    "REJECTED",
    "SUPERSEDED",
)
TERRITORY_LEVELS = ("MUNICIPALITY", "ELECTORAL_ZONE")


def upgrade():
    bind = op.get_bind()
    dataset_status = sa.Enum(*DATASET_STATUSES, name="electoral_dataset_status")
    territory_level = sa.Enum(*TERRITORY_LEVELS, name="electoral_territory_level")
    dataset_status.create(bind, checkfirst=True)
    territory_level.create(bind, checkfirst=True)
    status_column = _enum_column(bind, "electoral_dataset_status", DATASET_STATUSES)
    level_column = _enum_column(bind, "electoral_territory_level", TERRITORY_LEVELS)

    op.create_table(
        "electoral_dataset_versions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("source_name", sa.String(160), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("source_hash", sa.String(64), nullable=False),
        sa.Column("source_format", sa.String(20), nullable=False),
        sa.Column("parser_version", sa.String(40), nullable=False),
        sa.Column("coverage_key", sa.String(64), nullable=False),
        sa.Column("election_year", sa.Integer(), nullable=False),
        sa.Column("election_scope", sa.String(20), nullable=False),
        sa.Column("uf", sa.String(2), nullable=False),
        sa.Column("office_code", sa.String(10)),
        sa.Column("coverage", sa.JSON(), nullable=False),
        sa.Column("source_metadata", sa.JSON(), nullable=False),
        sa.Column("validation_manifest", sa.JSON(), nullable=False),
        sa.Column("raw_storage_path", sa.Text(), nullable=False),
        sa.Column("status", status_column, nullable=False),
        sa.Column("row_count", sa.BigInteger(), nullable=False),
        sa.Column("invalid_rows", sa.BigInteger(), nullable=False),
        sa.Column("total_votes", sa.BigInteger(), nullable=False),
        sa.Column("quality_score", sa.Float()),
        sa.Column("discovered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("downloaded_at", sa.DateTime(timezone=True)),
        sa.Column("validated_at", sa.DateTime(timezone=True)),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "source_hash",
            "coverage_key",
            "parser_version",
            name="uq_electoral_dataset_hash_coverage",
        ),
    )
    _indexes(
        "electoral_dataset_versions",
        "source_hash",
        "election_year",
        "election_scope",
        "uf",
        "office_code",
        "status",
        "published_at",
    )

    op.create_table(
        "electoral_elections",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("dataset_version_id", sa.Uuid(), nullable=False),
        sa.Column("external_id", sa.String(30), nullable=False),
        sa.Column("name", sa.String(240), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("round", sa.Integer(), nullable=False),
        sa.Column("scope", sa.String(20), nullable=False),
        sa.Column("election_date", sa.Date()),
        sa.Column("uf", sa.String(2), nullable=False),
        sa.ForeignKeyConstraint(
            ["dataset_version_id"], ["electoral_dataset_versions.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "dataset_version_id",
            "external_id",
            name="uq_electoral_election_version_external",
        ),
    )
    _indexes("electoral_elections", "dataset_version_id", "year", "scope", "uf")

    op.create_table(
        "electoral_offices",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(10), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
    )
    op.create_index("ix_electoral_offices_code", "electoral_offices", ["code"], unique=True)

    op.create_table(
        "electoral_parties",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("dataset_version_id", sa.Uuid(), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("acronym", sa.String(30), nullable=False),
        sa.Column("name", sa.String(180), nullable=False),
        sa.ForeignKeyConstraint(
            ["dataset_version_id"], ["electoral_dataset_versions.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "dataset_version_id", "number", name="uq_electoral_party_version_number"
        ),
    )
    _indexes("electoral_parties", "dataset_version_id")

    op.create_table(
        "electoral_candidates",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("dataset_version_id", sa.Uuid(), nullable=False),
        sa.Column("external_id", sa.String(40), nullable=False),
        sa.Column("full_name", sa.String(240), nullable=False),
        sa.Column("ballot_name", sa.String(180), nullable=False),
        sa.ForeignKeyConstraint(
            ["dataset_version_id"], ["electoral_dataset_versions.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "dataset_version_id",
            "external_id",
            name="uq_electoral_candidate_version_external",
        ),
    )
    _indexes("electoral_candidates", "dataset_version_id")

    op.create_table(
        "electoral_territories",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("dataset_version_id", sa.Uuid(), nullable=False),
        sa.Column("level", level_column, nullable=False),
        sa.Column("uf", sa.String(2), nullable=False),
        sa.Column("municipality_code", sa.String(10), nullable=False),
        sa.Column("municipality_name", sa.String(180), nullable=False),
        sa.Column("zone", sa.Integer()),
        sa.Column("derived", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(
            ["dataset_version_id"], ["electoral_dataset_versions.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "dataset_version_id",
            "level",
            "uf",
            "municipality_code",
            "zone",
            name="uq_electoral_territory_version_place",
        ),
    )
    _indexes("electoral_territories", "dataset_version_id", "level", "uf", "municipality_code")

    op.create_table(
        "electoral_candidacies",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("dataset_version_id", sa.Uuid(), nullable=False),
        sa.Column("election_id", sa.Uuid(), nullable=False),
        sa.Column("office_id", sa.Uuid(), nullable=False),
        sa.Column("candidate_id", sa.Uuid(), nullable=False),
        sa.Column("party_id", sa.Uuid(), nullable=False),
        sa.Column("ballot_number", sa.String(20), nullable=False),
        sa.Column("status", sa.String(120)),
        sa.ForeignKeyConstraint(
            ["dataset_version_id"], ["electoral_dataset_versions.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["election_id"], ["electoral_elections.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["office_id"], ["electoral_offices.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["candidate_id"], ["electoral_candidates.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["party_id"], ["electoral_parties.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "dataset_version_id",
            "election_id",
            "candidate_id",
            "office_id",
            name="uq_electoral_candidacy_version_election_candidate_office",
        ),
    )
    _indexes(
        "electoral_candidacies",
        "dataset_version_id",
        "election_id",
        "office_id",
        "candidate_id",
        "party_id",
    )

    op.create_table(
        "electoral_results",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("dataset_version_id", sa.Uuid(), nullable=False),
        sa.Column("election_id", sa.Uuid(), nullable=False),
        sa.Column("candidacy_id", sa.Uuid(), nullable=False),
        sa.Column("territory_id", sa.Uuid(), nullable=False),
        sa.Column("votes", sa.Integer(), nullable=False),
        sa.Column("calculation_metadata", sa.JSON(), nullable=False),
        sa.CheckConstraint("votes >= 0", name="ck_electoral_results_votes_nonnegative"),
        sa.ForeignKeyConstraint(
            ["dataset_version_id"], ["electoral_dataset_versions.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["election_id"], ["electoral_elections.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["candidacy_id"], ["electoral_candidacies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["territory_id"], ["electoral_territories.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "dataset_version_id",
            "election_id",
            "candidacy_id",
            "territory_id",
            name="uq_electoral_result_version_candidacy_territory",
        ),
    )
    _indexes(
        "electoral_results",
        "dataset_version_id",
        "election_id",
        "candidacy_id",
        "territory_id",
    )

    op.create_table(
        "electoral_staging_results",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("dataset_version_id", sa.Uuid(), nullable=False),
        sa.Column("row_number", sa.BigInteger(), nullable=False),
        sa.Column("canonical_data", sa.JSON(), nullable=False),
        sa.Column("validation_error", sa.String(500)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["dataset_version_id"], ["electoral_dataset_versions.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "dataset_version_id", "row_number", name="uq_electoral_staging_version_row"
        ),
    )
    _indexes("electoral_staging_results", "dataset_version_id", "validation_error")

    if bind.dialect.name == "postgresql":
        _grant_runtime_access(bind)


def downgrade():
    bind = op.get_bind()
    for table in (
        "electoral_staging_results",
        "electoral_results",
        "electoral_candidacies",
        "electoral_territories",
        "electoral_candidates",
        "electoral_parties",
        "electoral_offices",
        "electoral_elections",
        "electoral_dataset_versions",
    ):
        op.drop_table(table)
    sa.Enum(name="electoral_territory_level").drop(bind, checkfirst=True)
    sa.Enum(name="electoral_dataset_status").drop(bind, checkfirst=True)


def _enum_column(bind, name: str, values: tuple[str, ...]):
    if bind.dialect.name == "postgresql":
        return postgresql.ENUM(*values, name=name, create_type=False)
    return sa.Enum(*values, name=name)


def _indexes(table: str, *columns: str) -> None:
    for column in columns:
        op.create_index(f"ix_{table}_{column}", table, [column])


def _grant_runtime_access(bind) -> None:
    app_role = os.getenv("APP_DB_USER", "gabflow_app")
    worker_role = os.getenv("WORKER_DB_USER", "gabflow_worker")
    requested = {app_role, worker_role}
    available = {
        row[0]
        for row in bind.execute(
            sa.text("SELECT rolname FROM pg_roles WHERE rolname = ANY(:roles)"),
            {"roles": list(requested)},
        )
    }
    catalog_tables = (
        "electoral_dataset_versions",
        "electoral_elections",
        "electoral_offices",
        "electoral_parties",
        "electoral_candidates",
        "electoral_candidacies",
        "electoral_territories",
        "electoral_results",
    )
    if app_role in available:
        for table in catalog_tables:
            op.execute(sa.text(f'GRANT SELECT ON TABLE {table} TO "{app_role}"'))
    if worker_role in available:
        for table in (*catalog_tables, "electoral_staging_results"):
            op.execute(
                sa.text(f'GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE {table} TO "{worker_role}"')
            )
