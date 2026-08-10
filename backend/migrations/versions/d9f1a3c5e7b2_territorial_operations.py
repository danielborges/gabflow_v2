"""Add integrated territorial operations.

Revision ID: d9f1a3c5e7b2
Revises: c8a3e0f2b4d6
"""

import os

import sqlalchemy as sa
from alembic import op

revision = "d9f1a3c5e7b2"
down_revision = "c8a3e0f2b4d6"
branch_labels = None
depends_on = None


def upgrade():
    action_type = sa.Enum(
        "TAREFA", "AGENDA", "VISITA", "ROTEIRO", "ENCAMINHAMENTO",
        name="territorial_action_type",
    )
    action_status = sa.Enum(
        "PENDENTE", "EM_ANDAMENTO", "CONCLUIDA", "CANCELADA",
        name="territorial_action_status",
    )
    op.create_table(
        "territorial_actions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("territory_id", sa.Uuid(), nullable=False),
        sa.Column("action_type", action_type, nullable=False),
        sa.Column("status", action_status, nullable=False),
        sa.Column("title", sa.String(180), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("assignee_id", sa.Uuid(), nullable=True),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source_key", sa.String(160), nullable=False),
        sa.Column("source_context", sa.JSON(), nullable=False),
        sa.Column("filters", sa.JSON(), nullable=False),
        sa.Column("request_ids", sa.JSON(), nullable=False),
        sa.Column("result", sa.Text(), nullable=True),
        sa.Column("evidence", sa.JSON(), nullable=False),
        sa.Column("agenda_event_id", sa.Uuid(), nullable=True),
        sa.Column("created_by_id", sa.Uuid(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["territory_id"], ["territories.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["assignee_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["agenda_event_id"], ["agenda_events.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_territorial_actions_tenant_id_id"),
    )
    for column in (
        "tenant_id", "territory_id", "action_type", "status", "assignee_id", "due_at",
        "source_key", "agenda_event_id", "created_at",
    ):
        op.create_index(f"ix_territorial_actions_{column}", "territorial_actions", [column])
    if op.get_bind().dialect.name == "postgresql":
        app_user = os.getenv("APP_DB_USER", "gabflow_app")
        worker_user = os.getenv("WORKER_DB_USER", "gabflow_worker")
        op.execute(
            f'GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE territorial_actions '
            f'TO "{app_user}", "{worker_user}"'
        )
        op.execute("ALTER TABLE territorial_actions ENABLE ROW LEVEL SECURITY")
        op.execute("ALTER TABLE territorial_actions FORCE ROW LEVEL SECURITY")
        op.execute(
            """
            CREATE POLICY territorial_actions_tenant_isolation ON territorial_actions FOR ALL
            USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
            WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
            """
        )


def downgrade():
    op.drop_table("territorial_actions")
    if op.get_bind().dialect.name == "postgresql":
        sa.Enum(name="territorial_action_status").drop(op.get_bind(), checkfirst=True)
        sa.Enum(name="territorial_action_type").drop(op.get_bind(), checkfirst=True)
