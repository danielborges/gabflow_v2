"""hybrid normative sources

Revision ID: f1b2c3d4e5a6
Revises: e0a1b2c3d4e5
"""

import os

import sqlalchemy as sa
from alembic import op


revision = "f1b2c3d4e5a6"
down_revision = "e0a1b2c3d4e5"
branch_labels = None
depends_on = None


candidate_status = sa.Enum(
    "PENDENTE", "APROVADA", "REJEITADA", name="normative_candidate_status"
)


def upgrade():
    with op.batch_alter_table("normative_sources") as batch_op:
        batch_op.add_column(sa.Column("origin", sa.String(length=20), nullable=False, server_default="MANUAL"))
        batch_op.add_column(sa.Column("provider", sa.String(length=40)))
        batch_op.add_column(sa.Column("external_id", sa.String(length=500)))
        batch_op.add_column(sa.Column("official_source_url", sa.String(length=1000)))
        batch_op.add_column(sa.Column("imported_at", sa.DateTime(timezone=True)))
        batch_op.add_column(sa.Column("reviewed_by_id", sa.Uuid()))
        batch_op.add_column(sa.Column("reviewed_at", sa.DateTime(timezone=True)))
        batch_op.add_column(sa.Column("supersedes_source_id", sa.Uuid()))
        batch_op.create_foreign_key(
            "fk_normative_sources_reviewed_by_id_users", "users", ["reviewed_by_id"], ["id"], ondelete="SET NULL"
        )
        batch_op.create_foreign_key(
            "fk_normative_sources_supersedes_source_id", "normative_sources", ["supersedes_source_id"], ["id"], ondelete="SET NULL"
        )
        for column in ("origin", "provider", "external_id", "reviewed_by_id", "supersedes_source_id"):
            batch_op.create_index(f"ix_normative_sources_{column}", [column])

    op.create_table(
        "normative_source_connectors",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("search_query", sa.String(length=500), nullable=False),
        sa.Column("jurisdiction", sa.String(length=120)),
        sa.Column("sync_frequency_hours", sa.Integer(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("next_sync_at", sa.DateTime(timezone=True)),
        sa.Column("last_sync_at", sa.DateTime(timezone=True)),
        sa.Column("last_status", sa.String(length=30), nullable=False),
        sa.Column("last_error", sa.String(length=1000)),
        sa.Column("created_by_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "name"),
    )
    for column in ("tenant_id", "provider", "enabled", "next_sync_at"):
        op.create_index(f"ix_normative_source_connectors_{column}", "normative_source_connectors", [column])

    op.create_table(
        "normative_source_sync_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("connector_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("discovered_count", sa.Integer(), nullable=False),
        sa.Column("candidate_count", sa.Integer(), nullable=False),
        sa.Column("unchanged_count", sa.Integer(), nullable=False),
        sa.Column("error", sa.String(length=1000)),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["connector_id"], ["normative_source_connectors.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ("tenant_id", "connector_id", "status", "started_at"):
        op.create_index(f"ix_normative_source_sync_runs_{column}", "normative_source_sync_runs", [column])

    op.create_table(
        "normative_source_candidates",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("connector_id", sa.Uuid(), nullable=False),
        sa.Column("sync_run_id", sa.Uuid(), nullable=False),
        sa.Column("status", candidate_status, nullable=False),
        sa.Column("external_id", sa.String(length=500), nullable=False),
        sa.Column("source_type", sa.String(length=50), nullable=False),
        sa.Column("title", sa.String(length=240), nullable=False),
        sa.Column("reference", sa.String(length=240), nullable=False),
        sa.Column("excerpt", sa.Text(), nullable=False),
        sa.Column("jurisdiction", sa.String(length=120)),
        sa.Column("source_url", sa.String(length=1000)),
        sa.Column("version", sa.String(length=80), nullable=False),
        sa.Column("checksum", sa.String(length=64), nullable=False),
        sa.Column("valid_from", sa.Date()),
        sa.Column("valid_until", sa.Date()),
        sa.Column("existing_source_id", sa.Uuid()),
        sa.Column("review_reason", sa.String(length=500)),
        sa.Column("reviewed_by_id", sa.Uuid()),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["connector_id"], ["normative_source_connectors.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["sync_run_id"], ["normative_source_sync_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["existing_source_id"], ["normative_sources.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["reviewed_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("connector_id", "external_id", "checksum"),
    )
    for column in ("tenant_id", "connector_id", "sync_run_id", "status", "existing_source_id", "reviewed_by_id", "created_at"):
        op.create_index(f"ix_normative_source_candidates_{column}", "normative_source_candidates", [column])

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        app_user = os.getenv("APP_DB_USER", "gabflow_app")
        worker_user = os.getenv("WORKER_DB_USER", "gabflow_worker")
        for table in (
            "normative_source_connectors",
            "normative_source_sync_runs",
            "normative_source_candidates",
        ):
            op.execute(
                f'GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE {table} '
                f'TO "{app_user}", "{worker_user}"'
            )
            op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
            op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
            op.execute(
                f"CREATE POLICY {table}_tenant_isolation ON {table} FOR ALL "
                "USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid) "
                "WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)"
            )


def downgrade():
    op.drop_table("normative_source_candidates")
    candidate_status.drop(op.get_bind(), checkfirst=True)
    op.drop_table("normative_source_sync_runs")
    op.drop_table("normative_source_connectors")
    with op.batch_alter_table("normative_sources") as batch_op:
        for column in ("supersedes_source_id", "reviewed_by_id", "external_id", "provider", "origin"):
            batch_op.drop_index(f"ix_normative_sources_{column}")
        batch_op.drop_constraint("fk_normative_sources_supersedes_source_id", type_="foreignkey")
        batch_op.drop_constraint("fk_normative_sources_reviewed_by_id_users", type_="foreignkey")
        for column in ("supersedes_source_id", "reviewed_at", "reviewed_by_id", "imported_at", "official_source_url", "external_id", "provider", "origin"):
            batch_op.drop_column(column)
