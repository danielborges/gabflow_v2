"""Add grounded electoral questions, refusals and human review.

Revision ID: r1b9f6d1e3a5
Revises: q9a8e5c0d2f4
"""

import os

import sqlalchemy as sa
from alembic import op

revision = "r1b9f6d1e3a5"
down_revision = "q9a8e5c0d2f4"
branch_labels = None
depends_on = None

TABLE = "electoral_insights"


def upgrade():
    op.add_column(TABLE, sa.Column("safety_classification", sa.JSON(), nullable=True))
    op.add_column(TABLE, sa.Column("output_validation", sa.JSON(), nullable=True))
    op.add_column(TABLE, sa.Column("review_status", sa.String(20), nullable=True))
    op.add_column(TABLE, sa.Column("reviewed_by_id", sa.Uuid(), nullable=True))
    op.add_column(TABLE, sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(TABLE, sa.Column("review_notes", sa.String(1000), nullable=True))
    op.add_column(TABLE, sa.Column("review_revision", sa.JSON(), nullable=True))
    op.execute(
        sa.text(
            """
            UPDATE electoral_insights
            SET safety_classification = CAST('{}' AS JSON),
                output_validation = CAST('{}' AS JSON),
                review_status = CASE WHEN status = 'REFUSED' THEN 'NOT_REQUIRED' ELSE 'PENDING' END,
                review_revision = CAST('{}' AS JSON)
            """
        )
    )
    for column in (
        "safety_classification",
        "output_validation",
        "review_status",
        "review_revision",
    ):
        op.alter_column(TABLE, column, nullable=False)
    op.create_check_constraint(
        "ck_electoral_insights_review_status",
        TABLE,
        "review_status IN ('PENDING', 'APPROVED', 'REJECTED', 'NOT_REQUIRED')",
    )
    op.create_foreign_key(
        "fk_electoral_insights_tenant_reviewer",
        TABLE,
        "users",
        ["tenant_id", "reviewed_by_id"],
        ["tenant_id", "id"],
        ondelete="RESTRICT",
    )
    op.create_index(f"ix_{TABLE}_review_status", TABLE, ["review_status"])
    op.create_index(f"ix_{TABLE}_reviewed_by_id", TABLE, ["reviewed_by_id"])
    if op.get_bind().dialect.name == "postgresql":
        _grant_runtime_access()


def downgrade():
    op.drop_index(f"ix_{TABLE}_reviewed_by_id", table_name=TABLE)
    op.drop_index(f"ix_{TABLE}_review_status", table_name=TABLE)
    op.drop_constraint("fk_electoral_insights_tenant_reviewer", TABLE, type_="foreignkey")
    op.drop_constraint("ck_electoral_insights_review_status", TABLE, type_="check")
    for column in (
        "review_revision",
        "review_notes",
        "reviewed_at",
        "reviewed_by_id",
        "review_status",
        "output_validation",
        "safety_classification",
    ):
        op.drop_column(TABLE, column)


def _grant_runtime_access() -> None:
    bind = op.get_bind()
    app_role = os.getenv("APP_DB_USER", "gabflow_app")
    worker_role = os.getenv("WORKER_DB_USER", "gabflow_worker")
    available = {
        row[0]
        for row in bind.execute(
            sa.text("SELECT rolname FROM pg_roles WHERE rolname = ANY(:roles)"),
            {"roles": [app_role, worker_role]},
        )
    }
    for role in (app_role, worker_role):
        if role in available:
            op.execute(sa.text(f'GRANT SELECT, UPDATE ON TABLE {TABLE} TO "{role}"'))
