"""Add electoral mandate intelligence snapshots.

Revision ID: n6d5b2f7a9c1
Revises: m5c4a1e6f8b0
"""

import os

import sqlalchemy as sa
from alembic import op

revision = "n6d5b2f7a9c1"
down_revision = "m5c4a1e6f8b0"
branch_labels = None
depends_on = None

TABLES = ("electoral_coverage_profiles", "electoral_mandate_snapshots")


def upgrade():
    op.create_table(
        "electoral_coverage_profiles",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("mandate_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("formula_code", sa.String(40), nullable=False),
        sa.Column("weights", sa.JSON(), nullable=False),
        sa.Column("targets", sa.JSON(), nullable=False),
        sa.Column("sensitive_categories", sa.JSON(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("explanation", sa.String(500), nullable=False),
        sa.Column("created_by_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("version >= 1", name="ck_electoral_coverage_profile_version"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "mandate_id"],
            ["mandates.tenant_id", "mandates.id"],
            ondelete="CASCADE",
            name="fk_electoral_coverage_profiles_tenant_mandate",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "created_by_id"],
            ["users.tenant_id", "users.id"],
            ondelete="RESTRICT",
            name="fk_electoral_coverage_profiles_tenant_creator",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id", "mandate_id", "version", name="uq_electoral_coverage_profile_version"
        ),
        sa.UniqueConstraint("tenant_id", "id", name="uq_electoral_coverage_profiles_tenant_id_id"),
    )
    for column in ("tenant_id", "mandate_id", "active", "created_by_id"):
        op.create_index(
            f"ix_electoral_coverage_profiles_{column}", "electoral_coverage_profiles", [column]
        )

    op.create_table(
        "electoral_mandate_snapshots",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("mandate_id", sa.Uuid(), nullable=False),
        sa.Column("coverage_profile_id", sa.Uuid(), nullable=False),
        sa.Column("created_by_id", sa.Uuid(), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("privacy_threshold", sa.Integer(), nullable=False),
        sa.Column("config_hash", sa.String(64), nullable=False),
        sa.Column("source_cutoff_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("electoral_context", sa.JSON(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("period_end >= period_start", name="ck_electoral_snapshot_period"),
        sa.CheckConstraint(
            "privacy_threshold >= 1", name="ck_electoral_snapshot_privacy_threshold"
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "mandate_id"],
            ["mandates.tenant_id", "mandates.id"],
            ondelete="CASCADE",
            name="fk_electoral_mandate_snapshots_tenant_mandate",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "coverage_profile_id"],
            ["electoral_coverage_profiles.tenant_id", "electoral_coverage_profiles.id"],
            ondelete="RESTRICT",
            name="fk_electoral_mandate_snapshots_tenant_profile",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "created_by_id"],
            ["users.tenant_id", "users.id"],
            ondelete="RESTRICT",
            name="fk_electoral_mandate_snapshots_tenant_creator",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_electoral_mandate_snapshots_tenant_id_id"),
    )
    for column in (
        "tenant_id", "mandate_id", "coverage_profile_id", "created_by_id",
        "period_start", "period_end", "config_hash", "created_at",
    ):
        op.create_index(
            f"ix_electoral_mandate_snapshots_{column}", "electoral_mandate_snapshots", [column]
        )

    if op.get_bind().dialect.name == "postgresql":
        for table in TABLES:
            op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
            op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
            op.execute(
                f"""
                CREATE POLICY {table}_tenant_isolation ON {table} FOR ALL
                USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
                WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
                """
            )
        _grant_runtime_access()


def downgrade():
    if op.get_bind().dialect.name == "postgresql":
        for table in reversed(TABLES):
            op.execute(f"DROP POLICY IF EXISTS {table}_tenant_isolation ON {table}")
            op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
            op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
    op.drop_table("electoral_mandate_snapshots")
    op.drop_table("electoral_coverage_profiles")


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
        for table in TABLES:
            op.execute(sa.text(f'GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE {table} TO "{role}"'))
