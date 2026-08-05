"""Add synchronized official CPF fingerprints for electoral identity.

Revision ID: y8c6d3e0f2a4
Revises: x7b5f2c0d4e6
"""

import os

import sqlalchemy as sa
from alembic import op

revision = "y8c6d3e0f2a4"
down_revision = "x7b5f2c0d4e6"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "electoral_candidate_registry_syncs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("election_year", sa.Integer(), nullable=False),
        sa.Column("uf", sa.String(2), nullable=True),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("source_hash", sa.String(64), nullable=False),
        sa.Column("fingerprint_key_version", sa.Integer(), nullable=False),
        sa.Column("row_count", sa.BigInteger(), nullable=False),
        sa.Column("matched_candidacies", sa.BigInteger(), nullable=False),
        sa.Column("invalid_rows", sa.BigInteger(), nullable=False),
        sa.Column("manifest", sa.JSON(), nullable=False),
        sa.Column("synchronized_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "source_hash",
            "fingerprint_key_version",
            name="uq_electoral_candidate_registry_sync_source",
        ),
    )
    for column in ("election_year", "uf", "source_hash", "synchronized_at"):
        op.create_index(
            f"ix_electoral_candidate_registry_syncs_{column}",
            "electoral_candidate_registry_syncs",
            [column],
        )
    op.create_table(
        "electoral_candidacy_official_identities",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("candidacy_id", sa.Uuid(), nullable=False),
        sa.Column("registry_sync_id", sa.Uuid(), nullable=False),
        sa.Column("cpf_fingerprint", sa.String(64), nullable=False),
        sa.Column("fingerprint_key_version", sa.Integer(), nullable=False),
        sa.Column("synchronized_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["candidacy_id"], ["electoral_candidacies.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["registry_sync_id"],
            ["electoral_candidate_registry_syncs.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "candidacy_id", name="uq_electoral_candidacy_official_identity"
        ),
    )
    for column in ("candidacy_id", "registry_sync_id", "cpf_fingerprint"):
        op.create_index(
            f"ix_electoral_candidacy_official_identities_{column}",
            "electoral_candidacy_official_identities",
            [column],
        )
    if op.get_bind().dialect.name == "postgresql":
        app_user = os.getenv("APP_DB_USER", "gabflow_app")
        worker_user = os.getenv("WORKER_DB_USER", "gabflow_worker")
        for table in (
            "electoral_candidate_registry_syncs",
            "electoral_candidacy_official_identities",
        ):
            op.execute(
                f'GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE {table} '
                f'TO "{app_user}", "{worker_user}"'
            )


def downgrade():
    op.drop_table("electoral_candidacy_official_identities")
    op.drop_table("electoral_candidate_registry_syncs")
