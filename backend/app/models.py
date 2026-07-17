import enum
import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db


def utc_now() -> datetime:
    return datetime.now(UTC)


class TenantStatus(str, enum.Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"


class UserStatus(str, enum.Enum):
    ACTIVE = "active"
    BLOCKED = "blocked"


class Role(str, enum.Enum):
    ADMIN = "admin"
    MANAGER = "manager"
    STAFF = "staff"


class RequestSource(str, enum.Enum):
    PRESENCIAL = "PRESENCIAL"
    TELEFONE = "TELEFONE"
    WHATSAPP = "WHATSAPP"
    EMAIL = "EMAIL"
    FORMULARIO = "FORMULARIO"
    REDE_SOCIAL = "REDE_SOCIAL"
    VISITA = "VISITA"


class RequestStatus(str, enum.Enum):
    NOVA = "NOVA"
    TRIAGEM = "TRIAGEM"
    EM_ATENDIMENTO = "EM_ATENDIMENTO"
    AGUARDANDO_ORGAO = "AGUARDANDO_ORGAO"
    AGUARDANDO_CIDADAO = "AGUARDANDO_CIDADAO"
    RESOLVIDA = "RESOLVIDA"
    ENCERRADA = "ENCERRADA"
    CANCELADA = "CANCELADA"


class RequestPriority(str, enum.Enum):
    BAIXA = "BAIXA"
    MEDIA = "MEDIA"
    ALTA = "ALTA"
    CRITICA = "CRITICA"


class InteractionDirection(str, enum.Enum):
    ENTRADA = "ENTRADA"
    SAIDA = "SAIDA"
    INTERNA = "INTERNA"


class InteractionVisibility(str, enum.Enum):
    INTERNA = "INTERNA"
    CIDADAO = "CIDADAO"


class TaskStatus(str, enum.Enum):
    PENDENTE = "PENDENTE"
    EM_ANDAMENTO = "EM_ANDAMENTO"
    CONCLUIDA = "CONCLUIDA"
    CANCELADA = "CANCELADA"


class AttachmentScanStatus(str, enum.Enum):
    PENDENTE = "PENDENTE"
    LIMPO = "LIMPO"
    BLOQUEADO = "BLOQUEADO"


class NotificationType(str, enum.Enum):
    ATRIBUICAO = "ATRIBUICAO"
    TAREFA = "TAREFA"
    SLA = "SLA"
    RETORNO = "RETORNO"
    SISTEMA = "SISTEMA"


class ScheduledReturnStatus(str, enum.Enum):
    AGENDADO = "AGENDADO"
    CONCLUIDO = "CONCLUIDO"
    CANCELADO = "CANCELADO"


class PrivacyRequestType(str, enum.Enum):
    ACESSO = "ACESSO"
    CORRECAO = "CORRECAO"
    ANONIMIZACAO = "ANONIMIZACAO"
    REVOGACAO_CONSENTIMENTO = "REVOGACAO_CONSENTIMENTO"


class PrivacyRequestStatus(str, enum.Enum):
    ABERTA = "ABERTA"
    EM_ANALISE = "EM_ANALISE"
    CONCLUIDA = "CONCLUIDA"
    REJEITADA = "REJEITADA"


class RetentionAction(str, enum.Enum):
    REVISAR = "REVISAR"
    ANONIMIZAR = "ANONIMIZAR"


class ContactAttemptOutcome(str, enum.Enum):
    REALIZADO = "REALIZADO"
    SEM_RESPOSTA = "SEM_RESPOSTA"
    FALHOU = "FALHOU"
    AGENDADO = "AGENDADO"


class ForwardingStatus(str, enum.Enum):
    ENCAMINHADO = "ENCAMINHADO"
    AGUARDANDO_RETORNO = "AGUARDANDO_RETORNO"
    RESPONDIDO = "RESPONDIDO"
    ENCERRADO = "ENCERRADO"


class AIExecutionStatus(str, enum.Enum):
    PENDENTE = "PENDENTE"
    PROCESSANDO = "PROCESSANDO"
    CONCLUIDA = "CONCLUIDA"
    FALHOU = "FALHOU"


class AIReviewStatus(str, enum.Enum):
    PENDENTE = "PENDENTE"
    ACEITA = "ACEITA"
    EDITADA = "EDITADA"
    REJEITADA = "REJEITADA"


class Tenant(db.Model):
    __tablename__ = "tenants"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    slug: Mapped[str] = mapped_column(String(80), unique=True, nullable=False, index=True)
    timezone: Mapped[str] = mapped_column(String(50), default="America/Sao_Paulo")
    status: Mapped[TenantStatus] = mapped_column(
        Enum(TenantStatus, name="tenant_status"), default=TenantStatus.ACTIVE
    )
    protocol_sequence: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    users: Mapped[list["User"]] = relationship(back_populates="tenant")


class User(db.Model):
    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("tenant_id", "email"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    email: Mapped[str] = mapped_column(String(254), nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[Role] = mapped_column(Enum(Role, name="user_role"), default=Role.STAFF)
    status: Mapped[UserStatus] = mapped_column(
        Enum(UserStatus, name="user_status"), default=UserStatus.ACTIVE
    )
    mfa_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    tenant: Mapped[Tenant] = relationship(back_populates="users")


class AuditLog(db.Model):
    __tablename__ = "audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    action: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    entity_type: Mapped[str] = mapped_column(String(80), nullable=False)
    entity_id: Mapped[str | None] = mapped_column(String(64))
    before: Mapped[dict | None] = mapped_column(JSON)
    after: Mapped[dict | None] = mapped_column(JSON)
    ip_address: Mapped[str | None] = mapped_column(String(45))
    user_agent: Mapped[str | None] = mapped_column(String(512))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False, index=True
    )


class Citizen(db.Model):
    __tablename__ = "citizens"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(180), nullable=False, index=True)
    social_name: Mapped[str | None] = mapped_column(String(180))
    contacts: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    addresses: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    preferred_channel: Mapped[str | None] = mapped_column(String(30))
    contact_consent: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    publication_consent: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    legal_basis: Mapped[str] = mapped_column(String(120), nullable=False)
    privacy_flags: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    anonymized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )

    consent_records: Mapped[list["ConsentRecord"]] = relationship(
        back_populates="citizen",
        cascade="all, delete-orphan",
        order_by="ConsentRecord.recorded_at",
    )
    privacy_requests: Mapped[list["PrivacyRequest"]] = relationship(
        back_populates="citizen",
        cascade="all, delete-orphan",
        order_by="PrivacyRequest.created_at",
    )


class ConsentRecord(db.Model):
    __tablename__ = "consent_records"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    citizen_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("citizens.id", ondelete="CASCADE"), nullable=False, index=True
    )
    purpose: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    granted: Mapped[bool] = mapped_column(Boolean, nullable=False)
    legal_basis: Mapped[str] = mapped_column(String(120), nullable=False)
    source: Mapped[str] = mapped_column(String(50), nullable=False)
    evidence: Mapped[str | None] = mapped_column(Text)
    recorded_by_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False, index=True
    )

    citizen: Mapped[Citizen] = relationship(back_populates="consent_records")
    recorded_by: Mapped[User] = relationship()


class PrivacyRequest(db.Model):
    __tablename__ = "privacy_requests"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    citizen_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("citizens.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    request_type: Mapped[PrivacyRequestType] = mapped_column(
        Enum(PrivacyRequestType, name="privacy_request_type"), nullable=False, index=True
    )
    status: Mapped[PrivacyRequestStatus] = mapped_column(
        Enum(PrivacyRequestStatus, name="privacy_request_status"),
        default=PrivacyRequestStatus.ABERTA,
        nullable=False,
        index=True,
    )
    identity_validated: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    details: Mapped[str] = mapped_column(Text, nullable=False)
    resolution: Mapped[str | None] = mapped_column(Text)
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    assigned_to_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )

    citizen: Mapped[Citizen] = relationship(back_populates="privacy_requests")
    assigned_to: Mapped[User | None] = relationship(foreign_keys=[assigned_to_id])


class RetentionPolicy(db.Model):
    __tablename__ = "retention_policies"
    __table_args__ = (UniqueConstraint("tenant_id", "data_type"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    data_type: Mapped[str] = mapped_column(String(50), nullable=False)
    retention_days: Mapped[int] = mapped_column(Integer, nullable=False)
    action: Mapped[RetentionAction] = mapped_column(
        Enum(RetentionAction, name="retention_action"), nullable=False
    )
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    updated_by_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )


class Organization(db.Model):
    __tablename__ = "organizations"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    organization_type: Mapped[str] = mapped_column(String(80), nullable=False)
    name: Mapped[str] = mapped_column(String(180), nullable=False, index=True)
    contacts: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    addresses: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    territory: Mapped[str | None] = mapped_column(String(120))
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )


class RequestCategory(db.Model):
    __tablename__ = "request_categories"
    __table_args__ = (UniqueConstraint("tenant_id", "name", "parent_id"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("request_categories.id", ondelete="RESTRICT"), index=True
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    sla_hours: Mapped[int] = mapped_column(Integer, default=72, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )


class Territory(db.Model):
    __tablename__ = "territories"
    __table_args__ = (UniqueConstraint("tenant_id", "name"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )


class ExternalAgency(db.Model):
    __tablename__ = "external_agencies"
    __table_args__ = (UniqueConstraint("tenant_id", "name"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(180), nullable=False)
    contact_email: Mapped[str | None] = mapped_column(String(254))
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )


class DuplicateGroup(db.Model):
    __tablename__ = "duplicate_groups"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    reason: Mapped[str] = mapped_column(String(500), nullable=False)
    created_by_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )


class ServiceRequest(db.Model):
    __tablename__ = "service_requests"
    __table_args__ = (UniqueConstraint("tenant_id", "protocol"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    protocol: Mapped[str] = mapped_column(String(30), nullable=False)
    source: Mapped[RequestSource] = mapped_column(
        Enum(RequestSource, name="request_source"), nullable=False
    )
    title: Mapped[str | None] = mapped_column(String(180))
    description: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[RequestStatus] = mapped_column(
        Enum(RequestStatus, name="request_status"),
        default=RequestStatus.NOVA,
        nullable=False,
        index=True,
    )
    priority: Mapped[RequestPriority] = mapped_column(
        Enum(RequestPriority, name="request_priority"),
        default=RequestPriority.MEDIA,
        nullable=False,
        index=True,
    )
    address: Mapped[str | None] = mapped_column(String(500))
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    category: Mapped[str | None] = mapped_column(String(100), index=True)
    category_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("request_categories.id", ondelete="SET NULL"), index=True
    )
    subcategory: Mapped[str | None] = mapped_column(String(120))
    theme: Mapped[str | None] = mapped_column(String(120), index=True)
    territory_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("territories.id", ondelete="SET NULL"), index=True
    )
    agency_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("external_agencies.id", ondelete="SET NULL"), index=True
    )
    impact: Mapped[str | None] = mapped_column(String(20))
    urgency: Mapped[str | None] = mapped_column(String(20))
    citizen_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("citizens.id", ondelete="SET NULL"), index=True
    )
    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="SET NULL"), index=True
    )
    responsible_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    duplicate_group_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("duplicate_groups.id", ondelete="SET NULL"), index=True
    )
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    closing_reason: Mapped[str | None] = mapped_column(Text)
    closing_evidence: Mapped[str | None] = mapped_column(Text)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    public_access_key_hash: Mapped[str | None] = mapped_column(String(64), unique=True)
    created_by_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False, index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )

    interactions: Mapped[list["RequestInteraction"]] = relationship(
        back_populates="request",
        cascade="all, delete-orphan",
        order_by="RequestInteraction.created_at",
    )
    history: Mapped[list["RequestHistory"]] = relationship(
        back_populates="request", cascade="all, delete-orphan", order_by="RequestHistory.created_at"
    )
    tasks: Mapped[list["RequestTask"]] = relationship(
        back_populates="request", cascade="all, delete-orphan", order_by="RequestTask.created_at"
    )
    attachments: Mapped[list["Attachment"]] = relationship(
        back_populates="request", cascade="all, delete-orphan", order_by="Attachment.created_at"
    )
    forwardings: Mapped[list["RequestForwarding"]] = relationship(
        back_populates="request",
        cascade="all, delete-orphan",
        order_by="RequestForwarding.created_at",
    )
    contact_attempts: Mapped[list["ContactAttempt"]] = relationship(
        back_populates="request",
        cascade="all, delete-orphan",
        order_by="ContactAttempt.attempted_at",
    )
    scheduled_returns: Mapped[list["ScheduledReturn"]] = relationship(
        back_populates="request",
        cascade="all, delete-orphan",
        order_by="ScheduledReturn.scheduled_at",
    )


class RequestInteraction(db.Model):
    __tablename__ = "request_interactions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    request_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("service_requests.id", ondelete="CASCADE"), nullable=False, index=True
    )
    interaction_type: Mapped[str] = mapped_column(String(80), nullable=False)
    channel: Mapped[str] = mapped_column(String(50), nullable=False)
    direction: Mapped[InteractionDirection] = mapped_column(
        Enum(InteractionDirection, name="interaction_direction"), nullable=False
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    visibility: Mapped[InteractionVisibility] = mapped_column(
        Enum(InteractionVisibility, name="interaction_visibility"),
        default=InteractionVisibility.INTERNA,
        nullable=False,
    )
    author_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False, index=True
    )

    request: Mapped[ServiceRequest] = relationship(back_populates="interactions")


class RequestHistory(db.Model):
    __tablename__ = "request_history"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    request_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("service_requests.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    changes: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False, index=True
    )

    request: Mapped[ServiceRequest] = relationship(back_populates="history")


class RequestTask(db.Model):
    __tablename__ = "request_tasks"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    request_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("service_requests.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(180), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    assignee_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    status: Mapped[TaskStatus] = mapped_column(
        Enum(TaskStatus, name="task_status"),
        default=TaskStatus.PENDENTE,
        nullable=False,
        index=True,
    )
    priority: Mapped[RequestPriority] = mapped_column(
        Enum(RequestPriority, name="task_priority"),
        default=RequestPriority.MEDIA,
        nullable=False,
    )
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )

    request: Mapped[ServiceRequest] = relationship(back_populates="tasks")


class RequestForwarding(db.Model):
    __tablename__ = "request_forwardings"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    request_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("service_requests.id", ondelete="CASCADE"), nullable=False, index=True
    )
    agency_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("external_agencies.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    external_protocol: Mapped[str | None] = mapped_column(String(120))
    notes: Mapped[str | None] = mapped_column(Text)
    status: Mapped[ForwardingStatus] = mapped_column(
        Enum(ForwardingStatus, name="forwarding_status"),
        default=ForwardingStatus.ENCAMINHADO,
        nullable=False,
        index=True,
    )
    response: Mapped[str | None] = mapped_column(Text)
    response_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    created_by_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )

    request: Mapped[ServiceRequest] = relationship(back_populates="forwardings")


class ContactAttempt(db.Model):
    __tablename__ = "contact_attempts"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    request_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("service_requests.id", ondelete="CASCADE"), nullable=False, index=True
    )
    citizen_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("citizens.id", ondelete="SET NULL"), index=True
    )
    channel: Mapped[str] = mapped_column(String(30), nullable=False)
    destination: Mapped[str] = mapped_column(String(254), nullable=False)
    outcome: Mapped[ContactAttemptOutcome] = mapped_column(
        Enum(ContactAttemptOutcome, name="contact_attempt_outcome"),
        nullable=False,
        index=True,
    )
    notes: Mapped[str | None] = mapped_column(Text)
    channel_override_reason: Mapped[str | None] = mapped_column(Text)
    attempted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False, index=True
    )
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    created_by_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    source_event_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("outbox_events.id", ondelete="SET NULL"), unique=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    request: Mapped[ServiceRequest] = relationship(back_populates="contact_attempts")


class ResponseTemplate(db.Model):
    __tablename__ = "response_templates"
    __table_args__ = (UniqueConstraint("tenant_id", "name"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    category_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("request_categories.id", ondelete="SET NULL"), index=True
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    channel: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    subject: Mapped[str | None] = mapped_column(String(180))
    body: Mapped[str] = mapped_column(Text, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_by_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )

    category: Mapped[RequestCategory | None] = relationship()


class ScheduledReturn(db.Model):
    __tablename__ = "scheduled_returns"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    request_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("service_requests.id", ondelete="CASCADE"), nullable=False, index=True
    )
    assignee_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    scheduled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    status: Mapped[ScheduledReturnStatus] = mapped_column(
        Enum(ScheduledReturnStatus, name="scheduled_return_status"),
        default=ScheduledReturnStatus.AGENDADO,
        nullable=False,
        index=True,
    )
    notes: Mapped[str | None] = mapped_column(Text)
    reminder_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    reminder_minutes: Mapped[int] = mapped_column(Integer, default=60, nullable=False)
    reminder_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )

    request: Mapped[ServiceRequest] = relationship(back_populates="scheduled_returns")
    assignee: Mapped[User] = relationship(foreign_keys=[assignee_id])


class Attachment(db.Model):
    __tablename__ = "attachments"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    request_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("service_requests.id", ondelete="CASCADE"), nullable=False, index=True
    )
    storage_key: Mapped[str] = mapped_column(String(300), unique=True, nullable=False)
    original_name: Mapped[str] = mapped_column(String(255), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(120), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    scan_status: Mapped[AttachmentScanStatus] = mapped_column(
        Enum(AttachmentScanStatus, name="attachment_scan_status"),
        nullable=False,
    )
    uploaded_by_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    request: Mapped[ServiceRequest] = relationship(back_populates="attachments")


class Notification(db.Model):
    __tablename__ = "notifications"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    notification_type: Mapped[NotificationType] = mapped_column(
        Enum(NotificationType, name="notification_type"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(180), nullable=False)
    message: Mapped[str] = mapped_column(String(500), nullable=False)
    entity_type: Mapped[str | None] = mapped_column(String(80))
    entity_id: Mapped[str | None] = mapped_column(String(64))
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False, index=True
    )


class NotificationPreference(db.Model):
    __tablename__ = "notification_preferences"
    __table_args__ = (UniqueConstraint("tenant_id", "user_id", "notification_type"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    notification_type: Mapped[NotificationType] = mapped_column(
        Enum(NotificationType, name="notification_type", create_type=False),
        nullable=False,
    )
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )


class OutboxEvent(db.Model):
    __tablename__ = "outbox_events"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    event_type: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    aggregate_type: Mapped[str] = mapped_column(String(80), nullable=False)
    aggregate_id: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False, index=True
    )
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    locked_by: Mapped[str | None] = mapped_column(String(120))
    last_error: Mapped[str | None] = mapped_column(Text)
    failed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)


class AIExecution(db.Model):
    __tablename__ = "ai_executions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    request_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("service_requests.id", ondelete="CASCADE"), nullable=False, index=True
    )
    case_use: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(80), nullable=False)
    model: Mapped[str] = mapped_column(String(120), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(40), nullable=False)
    input_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    output: Mapped[dict | None] = mapped_column(JSON)
    confidence: Mapped[float | None] = mapped_column(Float)
    status: Mapped[AIExecutionStatus] = mapped_column(
        Enum(AIExecutionStatus, name="ai_execution_status"),
        default=AIExecutionStatus.PENDENTE,
        nullable=False,
        index=True,
    )
    review_status: Mapped[AIReviewStatus] = mapped_column(
        Enum(AIReviewStatus, name="ai_review_status"),
        default=AIReviewStatus.PENDENTE,
        nullable=False,
        index=True,
    )
    requested_by_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    reviewed_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    error: Mapped[str | None] = mapped_column(Text)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    estimated_cost: Mapped[float | None] = mapped_column(Float)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False, index=True
    )
