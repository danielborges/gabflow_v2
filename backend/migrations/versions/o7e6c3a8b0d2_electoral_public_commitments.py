"""Add public territorial commitments and operational map points.

Revision ID: o7e6c3a8b0d2
Revises: n6d5b2f7a9c1
"""

import os

import sqlalchemy as sa
from alembic import op

revision = "o7e6c3a8b0d2"
down_revision = "n6d5b2f7a9c1"
branch_labels = None
depends_on = None

TABLES = (
    "electoral_public_commitments",
    "electoral_commitment_evidence",
    "electoral_commitment_history",
)
APPEND_ONLY_TABLES = ("electoral_commitment_evidence", "electoral_commitment_history")


def upgrade():
    op.create_unique_constraint(
        "uq_territories_tenant_id_id", "territories", ["tenant_id", "id"]
    )
    op.create_table(
        "electoral_public_commitments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("mandate_id", sa.Uuid(), nullable=False),
        sa.Column("territory_id", sa.Uuid(), nullable=False),
        sa.Column("responsible_user_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(180), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("due_on", sa.Date(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("progress", sa.Integer(), nullable=False),
        sa.Column("public_location_name", sa.String(180)),
        sa.Column("latitude", sa.Float()),
        sa.Column("longitude", sa.Float()),
        sa.Column("location_is_public", sa.Boolean(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("created_by_id", sa.Uuid(), nullable=False),
        sa.Column("updated_by_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('PLANNED', 'IN_PROGRESS', 'COMPLETED', 'CANCELLED')",
            name="ck_electoral_commitment_status",
        ),
        sa.CheckConstraint(
            "progress >= 0 AND progress <= 100", name="ck_electoral_commitment_progress"
        ),
        sa.CheckConstraint(
            "(latitude IS NULL AND longitude IS NULL) OR "
            "(latitude BETWEEN -90 AND 90 AND longitude BETWEEN -180 AND 180 "
            "AND location_is_public = true)",
            name="ck_electoral_commitment_public_location",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "mandate_id"],
            ["mandates.tenant_id", "mandates.id"],
            ondelete="CASCADE",
            name="fk_electoral_commitments_tenant_mandate",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "territory_id"],
            ["territories.tenant_id", "territories.id"],
            ondelete="RESTRICT",
            name="fk_electoral_commitments_tenant_territory",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "responsible_user_id"],
            ["users.tenant_id", "users.id"],
            ondelete="RESTRICT",
            name="fk_electoral_commitments_tenant_responsible",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "created_by_id"],
            ["users.tenant_id", "users.id"],
            ondelete="RESTRICT",
            name="fk_electoral_commitments_tenant_creator",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "updated_by_id"],
            ["users.tenant_id", "users.id"],
            ondelete="RESTRICT",
            name="fk_electoral_commitments_tenant_updater",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id", "id", name="uq_electoral_public_commitments_tenant_id"
        ),
    )
    for column in (
        "tenant_id", "mandate_id", "territory_id", "responsible_user_id", "due_on",
        "status", "created_by_id", "updated_by_id", "created_at",
    ):
        op.create_index(
            f"ix_electoral_public_commitments_{column}",
            "electoral_public_commitments",
            [column],
        )

    op.create_table(
        "electoral_commitment_evidence",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("commitment_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(180), nullable=False),
        sa.Column("description", sa.String(500)),
        sa.Column("public_url", sa.Text(), nullable=False),
        sa.Column("evidence_date", sa.Date(), nullable=False),
        sa.Column("added_by_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id", "commitment_id"],
            ["electoral_public_commitments.tenant_id", "electoral_public_commitments.id"],
            ondelete="CASCADE",
            name="fk_electoral_commitment_evidence_tenant_commitment",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "added_by_id"],
            ["users.tenant_id", "users.id"],
            ondelete="RESTRICT",
            name="fk_electoral_commitment_evidence_tenant_adder",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ("tenant_id", "commitment_id", "added_by_id", "created_at"):
        op.create_index(
            f"ix_electoral_commitment_evidence_{column}",
            "electoral_commitment_evidence",
            [column],
        )

    op.create_table(
        "electoral_commitment_history",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("commitment_id", sa.Uuid(), nullable=False),
        sa.Column("action", sa.String(30), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("changed_by_id", sa.Uuid(), nullable=False),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "action IN ('CREATED', 'UPDATED', 'EVIDENCE_ADDED')",
            name="ck_electoral_commitment_history_action",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "commitment_id"],
            ["electoral_public_commitments.tenant_id", "electoral_public_commitments.id"],
            ondelete="CASCADE",
            name="fk_electoral_commitment_history_tenant_commitment",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "changed_by_id"],
            ["users.tenant_id", "users.id"],
            ondelete="RESTRICT",
            name="fk_electoral_commitment_history_tenant_changer",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "commitment_id",
            "version",
            name="uq_electoral_commitment_history_version",
        ),
    )
    for column in ("tenant_id", "commitment_id", "action", "changed_by_id", "created_at"):
        op.create_index(
            f"ix_electoral_commitment_history_{column}",
            "electoral_commitment_history",
            [column],
        )

    if op.get_bind().dialect.name == "postgresql":
        for table in TABLES:
            op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
            op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        for command in ("SELECT", "INSERT", "UPDATE"):
            operation = command.lower()
            using = (
                "USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)"
                if command in {"SELECT", "UPDATE"}
                else ""
            )
            check = (
                "WITH CHECK (tenant_id = "
                "NULLIF(current_setting('app.tenant_id', true), '')::uuid)"
                if command in {"INSERT", "UPDATE"}
                else ""
            )
            op.execute(
                f"CREATE POLICY electoral_public_commitments_tenant_{operation} "
                f"ON electoral_public_commitments FOR {command} {using} {check}"
            )
        for table in APPEND_ONLY_TABLES:
            op.execute(
                f"""
                CREATE POLICY {table}_tenant_select ON {table} FOR SELECT
                USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
                """
            )
            op.execute(
                f"""
                CREATE POLICY {table}_tenant_insert ON {table} FOR INSERT
                WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
                """
            )
        _grant_runtime_access()


def downgrade():
    if op.get_bind().dialect.name == "postgresql":
        for command in ("UPDATE", "INSERT", "SELECT"):
            op.execute(
                "DROP POLICY IF EXISTS electoral_public_commitments_tenant_"
                f"{command.lower()} ON electoral_public_commitments"
            )
        for table in reversed(APPEND_ONLY_TABLES):
            op.execute(f"DROP POLICY IF EXISTS {table}_tenant_insert ON {table}")
            op.execute(f"DROP POLICY IF EXISTS {table}_tenant_select ON {table}")
        for table in reversed(TABLES):
            op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
            op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
    op.drop_table("electoral_commitment_history")
    op.drop_table("electoral_commitment_evidence")
    op.drop_table("electoral_public_commitments")
    op.drop_constraint("uq_territories_tenant_id_id", "territories", type_="unique")


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
            privileges = (
                "SELECT, INSERT" if table in APPEND_ONLY_TABLES
                else "SELECT, INSERT, UPDATE"
            )
            op.execute(sa.text(f'GRANT {privileges} ON TABLE {table} TO "{role}"'))
