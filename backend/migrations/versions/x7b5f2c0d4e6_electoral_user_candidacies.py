"""Add confirmed electoral candidacies owned by the representative.

Revision ID: x7b5f2c0d4e6
Revises: w6a4e1b9c3d5
"""

import os

import sqlalchemy as sa
from alembic import op

revision = "x7b5f2c0d4e6"
down_revision = "w6a4e1b9c3d5"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "electoral_user_candidacies",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("candidacy_id", sa.Uuid(), nullable=False),
        sa.Column("method", sa.String(40), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id", "user_id"],
            ["users.tenant_id", "users.id"],
            ondelete="CASCADE",
            name="fk_electoral_user_candidacies_tenant_user",
        ),
        sa.ForeignKeyConstraint(
            ["candidacy_id"], ["electoral_candidacies.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id", "user_id", "candidacy_id", name="uq_electoral_user_candidacy"
        ),
    )
    for column in ("tenant_id", "user_id", "candidacy_id"):
        op.create_index(
            f"ix_electoral_user_candidacies_{column}",
            "electoral_user_candidacies",
            [column],
        )
    if op.get_bind().dialect.name == "postgresql":
        op.execute("ALTER TABLE electoral_user_candidacies ENABLE ROW LEVEL SECURITY")
        op.execute("ALTER TABLE electoral_user_candidacies FORCE ROW LEVEL SECURITY")
        op.execute(
            "CREATE POLICY electoral_user_candidacies_tenant_isolation "
            "ON electoral_user_candidacies USING "
            "(tenant_id = current_setting('app.tenant_id', true)::uuid) "
            "WITH CHECK (tenant_id = current_setting('app.tenant_id', true)::uuid)"
        )
        app_user = os.getenv("APP_DB_USER", "gabflow_app")
        worker_user = os.getenv("WORKER_DB_USER", "gabflow_worker")
        op.execute(
            f'GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE '
            f'electoral_user_candidacies TO "{app_user}", "{worker_user}"'
        )


def downgrade():
    op.drop_table("electoral_user_candidacies")
