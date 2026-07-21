"""agenda oversight integrations

Revision ID: c5d6e7f8a903
Revises: b4c5d6e7f802
Create Date: 2026-07-21 11:30:00
"""

import sqlalchemy as sa
from alembic import op

revision = "c5d6e7f8a903"
down_revision = "b4c5d6e7f802"
branch_labels = None
depends_on = None


def upgrade():
    agenda_type = sa.Enum(
        "COMPROMISSO",
        "VISITA",
        "REUNIAO",
        "AUDIENCIA",
        name="agenda_event_type",
    )
    agenda_status = sa.Enum("AGENDADO", "REALIZADO", "CANCELADO", name="agenda_event_status")
    oversight_status = sa.Enum(
        "PLANEJADA",
        "EM_ANDAMENTO",
        "CONCLUIDA",
        "CANCELADA",
        name="oversight_action_status",
    )
    integration_type = sa.Enum(
        "WHATSAPP",
        "EMAIL",
        "FORMULARIO_PUBLICO",
        "REDE_SOCIAL",
        "SISTEMA_LEGISLATIVO",
        "PROTOCOLO_EXTERNO",
        name="integration_type",
    )
    integration_status = sa.Enum("RASCUNHO", "ATIVA", "INATIVA", name="integration_status")

    op.create_table(
        "agenda_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("event_type", agenda_type, nullable=False),
        sa.Column("status", agenda_status, nullable=False),
        sa.Column("title", sa.String(length=180), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("location", sa.String(length=500), nullable=True),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("citizen_id", sa.Uuid(), nullable=True),
        sa.Column("organization_id", sa.Uuid(), nullable=True),
        sa.Column("territory_id", sa.Uuid(), nullable=True),
        sa.Column("request_id", sa.Uuid(), nullable=True),
        sa.Column("minutes", sa.Text(), nullable=True),
        sa.Column("photos", sa.JSON(), nullable=False),
        sa.Column("participants", sa.JSON(), nullable=False),
        sa.Column("pending_items", sa.JSON(), nullable=False),
        sa.Column("created_by_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["citizen_id"], ["citizens.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["request_id"], ["service_requests.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["territory_id"], ["territories.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_agenda_events_tenant_id", "agenda_events", ["tenant_id"])
    op.create_index("ix_agenda_events_event_type", "agenda_events", ["event_type"])
    op.create_index("ix_agenda_events_status", "agenda_events", ["status"])
    op.create_index("ix_agenda_events_starts_at", "agenda_events", ["starts_at"])
    op.create_index("ix_agenda_events_citizen_id", "agenda_events", ["citizen_id"])
    op.create_index("ix_agenda_events_organization_id", "agenda_events", ["organization_id"])
    op.create_index("ix_agenda_events_territory_id", "agenda_events", ["territory_id"])
    op.create_index("ix_agenda_events_request_id", "agenda_events", ["request_id"])

    op.create_table(
        "oversight_actions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("status", oversight_status, nullable=False),
        sa.Column("title", sa.String(length=180), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("location", sa.String(length=500), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("agency_id", sa.Uuid(), nullable=True),
        sa.Column("request_id", sa.Uuid(), nullable=True),
        sa.Column("findings", sa.JSON(), nullable=False),
        sa.Column("photos", sa.JSON(), nullable=False),
        sa.Column("responsible_parties", sa.JSON(), nullable=False),
        sa.Column("report", sa.Text(), nullable=True),
        sa.Column("follow_up_actions", sa.JSON(), nullable=False),
        sa.Column("created_by_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["agency_id"], ["external_agencies.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["request_id"], ["service_requests.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_oversight_actions_tenant_id", "oversight_actions", ["tenant_id"])
    op.create_index("ix_oversight_actions_status", "oversight_actions", ["status"])
    op.create_index("ix_oversight_actions_occurred_at", "oversight_actions", ["occurred_at"])
    op.create_index("ix_oversight_actions_agency_id", "oversight_actions", ["agency_id"])
    op.create_index("ix_oversight_actions_request_id", "oversight_actions", ["request_id"])

    op.create_table(
        "integration_settings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("integration_type", integration_type, nullable=False),
        sa.Column("status", integration_status, nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("config", sa.JSON(), nullable=False),
        sa.Column("secrets_configured", sa.Boolean(), nullable=False),
        sa.Column("updated_by_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["updated_by_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "integration_type"),
    )
    op.create_index("ix_integration_settings_tenant_id", "integration_settings", ["tenant_id"])
    op.create_index(
        "ix_integration_settings_integration_type",
        "integration_settings",
        ["integration_type"],
    )
    op.create_index("ix_integration_settings_status", "integration_settings", ["status"])


def downgrade():
    op.drop_index("ix_integration_settings_status", table_name="integration_settings")
    op.drop_index("ix_integration_settings_integration_type", table_name="integration_settings")
    op.drop_index("ix_integration_settings_tenant_id", table_name="integration_settings")
    op.drop_table("integration_settings")

    op.drop_index("ix_oversight_actions_request_id", table_name="oversight_actions")
    op.drop_index("ix_oversight_actions_agency_id", table_name="oversight_actions")
    op.drop_index("ix_oversight_actions_occurred_at", table_name="oversight_actions")
    op.drop_index("ix_oversight_actions_status", table_name="oversight_actions")
    op.drop_index("ix_oversight_actions_tenant_id", table_name="oversight_actions")
    op.drop_table("oversight_actions")

    op.drop_index("ix_agenda_events_request_id", table_name="agenda_events")
    op.drop_index("ix_agenda_events_territory_id", table_name="agenda_events")
    op.drop_index("ix_agenda_events_organization_id", table_name="agenda_events")
    op.drop_index("ix_agenda_events_citizen_id", table_name="agenda_events")
    op.drop_index("ix_agenda_events_starts_at", table_name="agenda_events")
    op.drop_index("ix_agenda_events_status", table_name="agenda_events")
    op.drop_index("ix_agenda_events_event_type", table_name="agenda_events")
    op.drop_index("ix_agenda_events_tenant_id", table_name="agenda_events")
    op.drop_table("agenda_events")

    bind = op.get_bind()
    for name in (
        "integration_status",
        "integration_type",
        "oversight_action_status",
        "agenda_event_status",
        "agenda_event_type",
    ):
        sa.Enum(name=name).drop(bind, checkfirst=True)
