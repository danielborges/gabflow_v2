"""Add official territory provenance and neighborhood geodata.

Revision ID: a2c4e6f8b0d1
Revises: f1b2c3d4e5a6
"""

import sqlalchemy as sa
from alembic import op


revision = "a2c4e6f8b0d1"
down_revision = "f1b2c3d4e5a6"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("territories") as batch_op:
        batch_op.add_column(sa.Column("source_name", sa.String(80)))
        batch_op.add_column(sa.Column("source_ref", sa.String(160)))
        batch_op.add_column(sa.Column("source_url", sa.String(500)))
        batch_op.add_column(sa.Column("source_version", sa.String(80)))

    op.create_table(
        "territory_neighborhoods",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("territory_id", sa.Uuid()),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("normalized_name", sa.String(120), nullable=False),
        sa.Column("external_code", sa.String(80), nullable=False),
        sa.Column("geometry", sa.JSON()),
        sa.Column("source_name", sa.String(80), nullable=False),
        sa.Column("source_url", sa.String(500)),
        sa.Column("source_version", sa.String(80)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "territory_id"],
            ["territories.tenant_id", "territories.id"],
            ondelete="CASCADE",
            name="fk_territory_neighborhoods_tenant_territory",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "source_name",
            "external_code",
            name="uq_territory_neighborhoods_source_code",
        ),
    )
    op.create_index(
        "ix_territory_neighborhoods_tenant_id", "territory_neighborhoods", ["tenant_id"]
    )
    op.create_index(
        "ix_territory_neighborhoods_territory_id",
        "territory_neighborhoods",
        ["territory_id"],
    )
    op.create_index(
        "ix_territory_neighborhoods_normalized_name",
        "territory_neighborhoods",
        ["normalized_name"],
    )


def downgrade():
    op.drop_table("territory_neighborhoods")
    with op.batch_alter_table("territories") as batch_op:
        batch_op.drop_column("source_version")
        batch_op.drop_column("source_url")
        batch_op.drop_column("source_ref")
        batch_op.drop_column("source_name")
