"""Add output validation state and tenant rollout profile.

Revision ID: g8c3e5f0b742
Revises: f7b2d4e9a631
"""

import os

import sqlalchemy as sa
from alembic import op

revision = "g8c3e5f0b742"
down_revision = "f7b2d4e9a631"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "rag_assistant_queries",
        sa.Column("output_validation", sa.JSON(), server_default="{}", nullable=False),
    )
    op.add_column(
        "rag_assistant_queries",
        sa.Column(
            "output_validation_enforced",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_rag_assistant_queries_output_validation_enforced",
        "rag_assistant_queries",
        ["output_validation_enforced"],
    )
    op.create_table(
        "rag_output_validation_profiles",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("policy_version", sa.String(80), nullable=False),
        sa.Column("validator_version", sa.String(80), nullable=False),
        sa.Column("rollout_state", sa.String(24), nullable=False),
        sa.Column("rollout_percentage", sa.Integer(), nullable=False),
        sa.Column("rollout_stage_index", sa.Integer(), nullable=False),
        sa.Column("rollout_stages", sa.JSON(), nullable=False),
        sa.Column("minimum_stage_samples", sa.Integer(), nullable=False),
        sa.Column("maximum_block_rate", sa.Float(), nullable=False),
        sa.Column("metrics", sa.JSON(), nullable=False),
        sa.Column("rollout_history", sa.JSON(), nullable=False),
        sa.Column("initiated_by_id", sa.Uuid(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "rollout_percentage >= 0 AND rollout_percentage <= 100",
            name="ck_rag_output_validation_rollout_percentage",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "initiated_by_id"],
            ["users.tenant_id", "users.id"],
            name="fk_rag_output_validation_profile_initiator",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("tenant_id"),
    )
    op.create_index(
        "ix_rag_output_validation_profiles_rollout_state",
        "rag_output_validation_profiles",
        ["rollout_state"],
    )
    op.create_index(
        "ix_rag_output_validation_profiles_initiated_by_id",
        "rag_output_validation_profiles",
        ["initiated_by_id"],
    )
    if op.get_bind().dialect.name == "postgresql":
        _enable_rls()
        _grant_runtime_access()


def downgrade():
    op.drop_table("rag_output_validation_profiles")
    op.drop_index(
        "ix_rag_assistant_queries_output_validation_enforced",
        table_name="rag_assistant_queries",
    )
    op.drop_column("rag_assistant_queries", "output_validation_enforced")
    op.drop_column("rag_assistant_queries", "output_validation")


def _enable_rls() -> None:
    op.execute("ALTER TABLE rag_output_validation_profiles ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE rag_output_validation_profiles FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY rag_output_validation_profiles_isolation
        ON rag_output_validation_profiles
        FOR ALL
        USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
        WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
        """
    )


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
        op.execute(
            sa.text(
                f'GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE rag_output_validation_profiles TO "{role}"'
            )
        )
