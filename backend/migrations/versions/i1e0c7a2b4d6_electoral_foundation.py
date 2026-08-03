"""Add the electoral intelligence access foundation.

Revision ID: i1e0c7a2b4d6
Revises: h9d4f6a1c853
"""

import os
import uuid
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "i1e0c7a2b4d6"
down_revision = "h9d4f6a1c853"
branch_labels = None
depends_on = None


mandate_status = sa.Enum("ACTIVE", "INACTIVE", "ENDED", name="mandate_status")


def upgrade():
    bind = op.get_bind()
    mandate_status.create(bind, checkfirst=True)
    status_column = (
        postgresql.ENUM("ACTIVE", "INACTIVE", "ENDED", name="mandate_status", create_type=False)
        if bind.dialect.name == "postgresql"
        else sa.Enum("ACTIVE", "INACTIVE", "ENDED", name="mandate_status")
    )
    op.create_table(
        "mandates",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("representative_user_id", sa.Uuid(), nullable=False),
        sa.Column("status", status_column, nullable=False),
        sa.Column("office", sa.String(120)),
        sa.Column("jurisdiction", sa.String(160)),
        sa.Column("starts_on", sa.Date()),
        sa.Column("ends_on", sa.Date()),
        sa.Column("source_metadata", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["representative_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_mandates_tenant_id_id"),
    )
    op.create_index("ix_mandates_tenant_id", "mandates", ["tenant_id"])
    op.create_index("ix_mandates_representative_user_id", "mandates", ["representative_user_id"])
    op.create_index("ix_mandates_status", "mandates", ["status"])
    if bind.dialect.name == "postgresql":
        op.create_index(
            "uq_mandates_active_tenant",
            "mandates",
            ["tenant_id"],
            unique=True,
            postgresql_where=sa.text("status = 'ACTIVE'"),
        )

    op.create_table(
        "electoral_module_settings",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("privacy_threshold", sa.Integer(), nullable=False),
        sa.Column("feature_flags", sa.JSON(), nullable=False),
        sa.Column("updated_by_id", sa.Uuid()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "privacy_threshold >= 1", name="ck_electoral_settings_privacy_threshold"
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["updated_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("tenant_id"),
    )
    op.create_index(
        "ix_electoral_module_settings_updated_by_id",
        "electoral_module_settings",
        ["updated_by_id"],
    )

    op.create_table(
        "electoral_access_delegations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("mandate_id", sa.Uuid(), nullable=False),
        sa.Column("grantor_user_id", sa.Uuid(), nullable=False),
        sa.Column("grantee_user_id", sa.Uuid(), nullable=False),
        sa.Column("capabilities", sa.JSON(), nullable=False),
        sa.Column("reason", sa.String(500), nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_until", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("revoked_by_id", sa.Uuid()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("valid_until > valid_from", name="ck_electoral_delegation_window"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "mandate_id"],
            ["mandates.tenant_id", "mandates.id"],
            ondelete="CASCADE",
            name="fk_electoral_delegations_tenant_mandate",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "grantor_user_id"],
            ["users.tenant_id", "users.id"],
            ondelete="RESTRICT",
            name="fk_electoral_delegations_tenant_grantor",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "grantee_user_id"],
            ["users.tenant_id", "users.id"],
            ondelete="CASCADE",
            name="fk_electoral_delegations_tenant_grantee",
        ),
        sa.ForeignKeyConstraint(["revoked_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in (
        "tenant_id",
        "mandate_id",
        "grantor_user_id",
        "grantee_user_id",
        "revoked_at",
        "revoked_by_id",
    ):
        op.create_index(
            f"ix_electoral_access_delegations_{column}",
            "electoral_access_delegations",
            [column],
        )

    _backfill_active_mandates(bind)
    if bind.dialect.name == "postgresql":
        _enable_rls()
        _grant_runtime_access(bind)


def downgrade():
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        for table in (
            "electoral_access_delegations",
            "electoral_module_settings",
            "mandates",
        ):
            op.execute(f"DROP POLICY IF EXISTS {table}_tenant_isolation ON {table}")
            op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
            op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
    op.drop_table("electoral_access_delegations")
    op.drop_table("electoral_module_settings")
    if bind.dialect.name == "postgresql":
        op.drop_index("uq_mandates_active_tenant", table_name="mandates")
    op.drop_table("mandates")
    mandate_status.drop(bind, checkfirst=True)


def _backfill_active_mandates(bind) -> None:
    users = sa.table(
        "users",
        sa.column("id", sa.Uuid()),
        sa.column("tenant_id", sa.Uuid()),
        sa.column("role", sa.String()),
        sa.column("status", sa.String()),
    )
    tenants = sa.table(
        "tenants",
        sa.column("id", sa.Uuid()),
        sa.column("chamber_type", sa.String()),
        sa.column("jurisdiction_name", sa.String()),
    )
    status_type = (
        postgresql.ENUM("ACTIVE", "INACTIVE", "ENDED", name="mandate_status", create_type=False)
        if bind.dialect.name == "postgresql"
        else sa.Enum("ACTIVE", "INACTIVE", "ENDED", name="mandate_status")
    )
    mandates = sa.table(
        "mandates",
        sa.column("id", sa.Uuid()),
        sa.column("tenant_id", sa.Uuid()),
        sa.column("representative_user_id", sa.Uuid()),
        sa.column("status", status_type),
        sa.column("office", sa.String()),
        sa.column("jurisdiction", sa.String()),
        sa.column("source_metadata", sa.JSON()),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    statement = (
        sa.select(
            users.c.id,
            users.c.tenant_id,
            tenants.c.chamber_type,
            tenants.c.jurisdiction_name,
        )
        .select_from(users.join(tenants, users.c.tenant_id == tenants.c.id))
        .where(
            sa.cast(users.c.role, sa.String) == "REPRESENTATIVE",
            sa.cast(users.c.status, sa.String) == "ACTIVE",
        )
    )
    now = datetime.now(UTC)
    for row in bind.execute(statement).mappings():
        bind.execute(
            mandates.insert().values(
                id=uuid.uuid4(),
                tenant_id=row["tenant_id"],
                representative_user_id=row["id"],
                status="ACTIVE",
                office=row["chamber_type"],
                jurisdiction=row["jurisdiction_name"],
                source_metadata={"origin": "migration_backfill"},
                created_at=now,
                updated_at=now,
            )
        )


def _enable_rls() -> None:
    for table in (
        "mandates",
        "electoral_module_settings",
        "electoral_access_delegations",
    ):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"""
            CREATE POLICY {table}_tenant_isolation ON {table} FOR ALL
            USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
            WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
            """
        )


def _grant_runtime_access(bind) -> None:
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
        for table in (
            "mandates",
            "electoral_module_settings",
            "electoral_access_delegations",
        ):
            op.execute(
                sa.text(f'GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE {table} TO "{role}"')
            )
