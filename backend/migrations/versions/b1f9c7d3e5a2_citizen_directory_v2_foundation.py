"""Add citizen directory v2 foundation.

Revision ID: b1f9c7d3e5a2
Revises: a0e8f5a2b4c6
"""

import os

import sqlalchemy as sa
from alembic import op

revision = "b1f9c7d3e5a2"
down_revision = "a0e8f5a2b4c6"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("citizens") as batch_op:
        batch_op.add_column(sa.Column("profession", sa.String(180)))
        batch_op.add_column(sa.Column("birth_date", sa.Date()))
        batch_op.add_column(sa.Column("cpf_ciphertext", sa.Text()))
        batch_op.add_column(sa.Column("cpf_fingerprint", sa.String(64)))
        batch_op.add_column(sa.Column("cpf_final", sa.String(2)))
        batch_op.add_column(sa.Column("cpf_key_version", sa.Integer()))
        batch_op.add_column(sa.Column("electoral_title_ciphertext", sa.Text()))
        batch_op.add_column(sa.Column("photo_storage_key", sa.String(300)))
        batch_op.add_column(
            sa.Column("vip", sa.Boolean(), nullable=False, server_default=sa.false())
        )
        batch_op.add_column(sa.Column("created_by_id", sa.Uuid()))
        batch_op.add_column(
            sa.Column("version", sa.Integer(), nullable=False, server_default="1")
        )
        batch_op.create_foreign_key(
            "fk_citizens_created_by_id_users",
            "users",
            ["created_by_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_unique_constraint(
            "uq_citizens_tenant_id_id", ["tenant_id", "id"]
        )
        batch_op.create_unique_constraint(
            "uq_citizens_tenant_cpf_fingerprint", ["tenant_id", "cpf_fingerprint"]
        )
        batch_op.create_index("ix_citizens_cpf_fingerprint", ["cpf_fingerprint"])
        batch_op.create_index("ix_citizens_vip", ["vip"])
        batch_op.create_index("ix_citizens_created_by_id", ["created_by_id"])

    with op.batch_alter_table("organizations") as batch_op:
        batch_op.create_unique_constraint(
            "uq_organizations_tenant_id_id", ["tenant_id", "id"]
        )

    op.create_table(
        "citizen_organization_links",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("citizen_id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("role", sa.String(40), nullable=False, server_default="RESPONSAVEL"),
        sa.Column("created_by_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id", "citizen_id"],
            ["citizens.tenant_id", "citizens.id"],
            name="fk_citizen_org_links_tenant_citizen",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "organization_id"],
            ["organizations.tenant_id", "organizations.id"],
            name="fk_citizen_org_links_tenant_organization",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "created_by_id"],
            ["users.tenant_id", "users.id"],
            name="fk_citizen_org_links_tenant_creator",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "citizen_id",
            "organization_id",
            "role",
            name="uq_citizen_org_links_scope",
        ),
    )
    for column in ("tenant_id", "citizen_id", "organization_id", "created_by_id"):
        op.create_index(
            f"ix_citizen_organization_links_{column}",
            "citizen_organization_links",
            [column],
        )

    if op.get_bind().dialect.name == "postgresql":
        tenant = "current_setting('app.tenant_id', true)::uuid"
        op.execute("ALTER TABLE citizen_organization_links ENABLE ROW LEVEL SECURITY")
        op.execute("ALTER TABLE citizen_organization_links FORCE ROW LEVEL SECURITY")
        op.execute(
            "CREATE POLICY citizen_organization_links_tenant_isolation "
            "ON citizen_organization_links FOR ALL "
            f"USING (tenant_id = {tenant}) WITH CHECK (tenant_id = {tenant})"
        )
        roles = {
            os.getenv("APP_DB_USER", "gabflow_app"),
            os.getenv("WORKER_DB_USER", "gabflow_worker"),
        }
        available = {
            row[0]
            for row in op.get_bind().execute(
                sa.text("SELECT rolname FROM pg_roles WHERE rolname = ANY(:roles)"),
                {"roles": list(roles)},
            )
        }
        for role in roles & available:
            op.execute(
                sa.text(
                    "GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE "
                    f'citizen_organization_links TO "{role}"'
                )
            )


def downgrade():
    op.drop_table("citizen_organization_links")
    with op.batch_alter_table("organizations") as batch_op:
        batch_op.drop_constraint("uq_organizations_tenant_id_id", type_="unique")
    with op.batch_alter_table("citizens") as batch_op:
        batch_op.drop_index("ix_citizens_created_by_id")
        batch_op.drop_index("ix_citizens_vip")
        batch_op.drop_index("ix_citizens_cpf_fingerprint")
        batch_op.drop_constraint("uq_citizens_tenant_cpf_fingerprint", type_="unique")
        batch_op.drop_constraint("uq_citizens_tenant_id_id", type_="unique")
        batch_op.drop_constraint("fk_citizens_created_by_id_users", type_="foreignkey")
        for column in (
            "version",
            "created_by_id",
            "vip",
            "photo_storage_key",
            "electoral_title_ciphertext",
            "cpf_key_version",
            "cpf_final",
            "cpf_fingerprint",
            "cpf_ciphertext",
            "birth_date",
            "profession",
        ):
            batch_op.drop_column(column)
