import enum
import uuid
from datetime import UTC, date, datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
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
    SUSPENDED = "suspended"
    CANCELLED = "cancelled"


class UserStatus(str, enum.Enum):
    ACTIVE = "active"
    BLOCKED = "blocked"


class Role(str, enum.Enum):
    PLATFORM_ADMIN = "platform_admin"
    GLOBAL_KNOWLEDGE_ADMIN = "global_knowledge_admin"
    ADMIN = "admin"
    MANAGER = "manager"
    REPRESENTATIVE = "representative"
    STAFF = "staff"


class ContractStatus(str, enum.Enum):
    TRIAL = "trial"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    CANCELLED = "cancelled"


class PlatformSettingType(str, enum.Enum):
    PARAMETER = "PARAMETER"
    GLOBAL_TEMPLATE = "GLOBAL_TEMPLATE"
    INTEGRATION_PROVIDER = "INTEGRATION_PROVIDER"
    FEATURE_FLAG = "FEATURE_FLAG"
    SECURITY_POLICY = "SECURITY_POLICY"


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


class AudioTranscriptionStatus(str, enum.Enum):
    PENDENTE = "PENDENTE"
    PROCESSANDO = "PROCESSANDO"
    CONCLUIDA = "CONCLUIDA"
    FALHOU = "FALHOU"


class AudioTranscriptionReviewStatus(str, enum.Enum):
    PENDENTE = "PENDENTE"
    ACEITA = "ACEITA"
    EDITADA = "EDITADA"
    REJEITADA = "REJEITADA"


class DocumentOcrStatus(str, enum.Enum):
    PENDENTE = "PENDENTE"
    PROCESSANDO = "PROCESSANDO"
    CONCLUIDO = "CONCLUIDO"
    FALHOU = "FALHOU"


class DocumentOcrReviewStatus(str, enum.Enum):
    PENDENTE = "PENDENTE"
    ACEITO = "ACEITO"
    EDITADO = "EDITADO"
    REJEITADO = "REJEITADO"


class RagDocumentAccess(str, enum.Enum):
    INTERNO = "INTERNO"
    RESTRITO = "RESTRITO"


class RagDocumentLifecycle(str, enum.Enum):
    RASCUNHO = "RASCUNHO"
    VIGENTE = "VIGENTE"
    HISTORICO = "HISTORICO"
    REVOGADO = "REVOGADO"


class RagIngestionStatus(str, enum.Enum):
    PENDENTE = "PENDENTE"
    PROCESSANDO = "PROCESSANDO"
    INDEXADO = "INDEXADO"
    FALHOU = "FALHOU"


class RagKnowledgeSourceStatus(str, enum.Enum):
    PENDENTE = "PENDENTE"
    ATIVA = "ATIVA"
    QUARENTENA = "QUARENTENA"
    INELEGIVEL = "INELEGIVEL"
    EXPIRADA = "EXPIRADA"
    ERRO = "ERRO"
    EXCLUIDA = "EXCLUIDA"


class RagQueryFeedbackRating(str, enum.Enum):
    POSITIVA = "POSITIVA"
    NEGATIVA = "NEGATIVA"
    CORRIGIDA = "CORRIGIDA"


class RagFeedbackStatus(str, enum.Enum):
    PENDENTE_REVISAO = "PENDENTE_REVISAO"
    APROVADO = "APROVADO"
    QUARENTENA = "QUARENTENA"
    REJEITADO = "REJEITADO"
    REVOGADO = "REVOGADO"
    SUPERADO = "SUPERADO"


class RagFeedbackReason(str, enum.Enum):
    FONTES_IRRELEVANTES = "FONTES_IRRELEVANTES"
    FONTE_AUSENTE = "FONTE_AUSENTE"
    RESPOSTA_INCORRETA = "RESPOSTA_INCORRETA"
    CITACAO_INCORRETA = "CITACAO_INCORRETA"
    FONTE_DESATUALIZADA = "FONTE_DESATUALIZADA"
    JURISDICAO_INCORRETA = "JURISDICAO_INCORRETA"
    ROTEAMENTO_INCORRETO = "ROTEAMENTO_INCORRETO"
    FILTROS_INCORRETOS = "FILTROS_INCORRETOS"
    RECUSA_INDEVIDA = "RECUSA_INDEVIDA"
    DEVERIA_RECUSAR = "DEVERIA_RECUSAR"
    PROBLEMA_DE_ESTILO = "PROBLEMA_DE_ESTILO"


class RagFeedbackSourceJudgmentValue(str, enum.Enum):
    RELEVANTE = "RELEVANTE"
    IRRELEVANTE = "IRRELEVANTE"
    AUSENTE = "AUSENTE"


class RagFeedbackModerationMode(str, enum.Enum):
    AUTOMATICA = "AUTOMATICA"
    HUMANA = "HUMANA"


class RagLearningRunStatus(str, enum.Enum):
    PENDENTE = "PENDENTE"
    PROCESSANDO = "PROCESSANDO"
    CONCLUIDA = "CONCLUIDA"
    ERRO = "ERRO"


class RagLearningArtifactType(str, enum.Enum):
    RERANK_PROFILE = "RERANK_PROFILE"
    ROUTING_EXAMPLES = "ROUTING_EXAMPLES"
    EVALUATION_CASES = "EVALUATION_CASES"
    ANSWER_EXEMPLARS = "ANSWER_EXEMPLARS"


class RagLearningArtifactStatus(str, enum.Enum):
    CANDIDATO = "CANDIDATO"
    EM_AVALIACAO = "EM_AVALIACAO"
    REJEITADO = "REJEITADO"
    APROVADO = "APROVADO"
    ATIVO = "ATIVO"
    SUBSTITUIDO = "SUBSTITUIDO"
    REVOGADO = "REVOGADO"


class GlobalDistributionPolicy(str, enum.Enum):
    OBRIGATORIA = "OBRIGATORIA"
    PADRAO = "PADRAO"
    OPCIONAL = "OPCIONAL"
    DIRECIONADA = "DIRECIONADA"
    RESTRITA_JURISDICAO = "RESTRITA_JURISDICAO"
    PRIVADA_PLATAFORMA = "PRIVADA_PLATAFORMA"


class GlobalCatalogStatus(str, enum.Enum):
    RASCUNHO = "RASCUNHO"
    PUBLICADA = "PUBLICADA"
    SUSPENSA = "SUSPENSA"
    ARQUIVADA = "ARQUIVADA"


class GlobalVersionStatus(str, enum.Enum):
    RASCUNHO = "RASCUNHO"
    PUBLICADA = "PUBLICADA"
    SUSPENSA = "SUSPENSA"
    SUBSTITUIDA = "SUBSTITUIDA"
    REVOGADA = "REVOGADA"


class GlobalEntitlementStatus(str, enum.Enum):
    ATIVA = "ATIVA"
    DESATIVADA = "DESATIVADA"
    REVOGADA = "REVOGADA"


class GlobalUpdateMode(str, enum.Enum):
    AUTOMATICA = "AUTOMATICA"
    FIXADA = "FIXADA"


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


class LegislativeDocumentType(str, enum.Enum):
    INDICACAO = "INDICACAO"
    REQUERIMENTO = "REQUERIMENTO"
    OFICIO = "OFICIO"
    MOCAO = "MOCAO"
    PEDIDO_INFORMACAO = "PEDIDO_INFORMACAO"
    PROJETO_LEI = "PROJETO_LEI"


class LegislativeDraftStatus(str, enum.Enum):
    RASCUNHO = "RASCUNHO"
    EM_REVISAO = "EM_REVISAO"
    APROVADA = "APROVADA"
    REJEITADA = "REJEITADA"


class LegislativeGenerationStatus(str, enum.Enum):
    PENDENTE = "PENDENTE"
    PROCESSANDO = "PROCESSANDO"
    CONCLUIDA = "CONCLUIDA"
    FALHOU = "FALHOU"


class LegislativeTramitationStatus(str, enum.Enum):
    PROTOCOLADA = "PROTOCOLADA"
    DISTRIBUIDA = "DISTRIBUIDA"
    EM_COMISSAO = "EM_COMISSAO"
    EM_PAUTA = "EM_PAUTA"
    APROVADA = "APROVADA"
    REJEITADA = "REJEITADA"
    SANCIONADA = "SANCIONADA"
    VETADA = "VETADA"
    ARQUIVADA = "ARQUIVADA"
    RETIRADA = "RETIRADA"


class AgendaEventType(str, enum.Enum):
    COMPROMISSO = "COMPROMISSO"
    VISITA = "VISITA"
    REUNIAO = "REUNIAO"
    AUDIENCIA = "AUDIENCIA"


class AgendaEventStatus(str, enum.Enum):
    AGENDADO = "AGENDADO"
    REALIZADO = "REALIZADO"
    CANCELADO = "CANCELADO"


class OversightActionStatus(str, enum.Enum):
    PLANEJADA = "PLANEJADA"
    EM_ANDAMENTO = "EM_ANDAMENTO"
    CONCLUIDA = "CONCLUIDA"
    CANCELADA = "CANCELADA"


class IntegrationType(str, enum.Enum):
    WHATSAPP = "WHATSAPP"
    EMAIL = "EMAIL"
    FORMULARIO_PUBLICO = "FORMULARIO_PUBLICO"
    REDE_SOCIAL = "REDE_SOCIAL"
    SISTEMA_LEGISLATIVO = "SISTEMA_LEGISLATIVO"
    PROTOCOLO_EXTERNO = "PROTOCOLO_EXTERNO"


class IntegrationStatus(str, enum.Enum):
    RASCUNHO = "RASCUNHO"
    ATIVA = "ATIVA"
    INATIVA = "INATIVA"


class ChannelMessageStatus(str, enum.Enum):
    RECEBIDA = "RECEBIDA"
    CONVERTIDA = "CONVERTIDA"
    IGNORADA = "IGNORADA"


class Tenant(db.Model):
    __tablename__ = "tenants"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    slug: Mapped[str] = mapped_column(String(80), unique=True, nullable=False, index=True)
    timezone: Mapped[str] = mapped_column(String(50), default="America/Sao_Paulo")
    chamber_type: Mapped[str | None] = mapped_column(String(40))
    jurisdiction_name: Mapped[str | None] = mapped_column(String(160))
    jurisdiction_city: Mapped[str | None] = mapped_column(String(120))
    jurisdiction_state: Mapped[str | None] = mapped_column(String(2))
    jurisdiction_ibge_code: Mapped[str | None] = mapped_column(String(20))
    jurisdiction_center_latitude: Mapped[float | None] = mapped_column(Float)
    jurisdiction_center_longitude: Mapped[float | None] = mapped_column(Float)
    jurisdiction_bounds: Mapped[dict | None] = mapped_column(JSON)
    jurisdiction_geojson: Mapped[dict | None] = mapped_column(JSON)
    plan: Mapped[str] = mapped_column(String(80), default="starter", nullable=False)
    contract_status: Mapped[ContractStatus] = mapped_column(
        Enum(ContractStatus, name="contract_status"), default=ContractStatus.TRIAL, nullable=False
    )
    user_limit: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    storage_limit_mb: Mapped[int] = mapped_column(Integer, default=1024, nullable=False)
    enabled_modules: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    contract_notes: Mapped[str | None] = mapped_column(Text)
    representative_info: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    mandate_info: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    visual_identity: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    chief_of_staff_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    status: Mapped[TenantStatus] = mapped_column(
        Enum(TenantStatus, name="tenant_status"), default=TenantStatus.ACTIVE
    )
    protocol_sequence: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    users: Mapped[list["User"]] = relationship(
        back_populates="tenant", foreign_keys="User.tenant_id"
    )


class PoliticalParty(db.Model):
    __tablename__ = "political_parties"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    acronym: Mapped[str] = mapped_column(String(20), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(180), nullable=False)
    ballot_number: Mapped[int] = mapped_column(Integer, unique=True, nullable=False)
    registration_date: Mapped[str | None] = mapped_column(String(20))
    national_president: Mapped[str | None] = mapped_column(String(180))
    logo_url: Mapped[str | None] = mapped_column(Text)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class User(db.Model):
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("email"),
        UniqueConstraint("cpf"),
        UniqueConstraint("tenant_id", "email"),
        UniqueConstraint("tenant_id", "id", name="uq_users_tenant_id_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    email: Mapped[str] = mapped_column(String(254), nullable=False)
    cpf: Mapped[str | None] = mapped_column(String(11), index=True)
    phone: Mapped[str | None] = mapped_column(String(20))
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[Role] = mapped_column(Enum(Role, name="user_role"), default=Role.STAFF)
    status: Mapped[UserStatus] = mapped_column(
        Enum(UserStatus, name="user_status"), default=UserStatus.ACTIVE
    )
    mfa_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    current_session_id: Mapped[str | None] = mapped_column(String(64))
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    tenant: Mapped[Tenant | None] = relationship(back_populates="users", foreign_keys=[tenant_id])


class AuditLog(db.Model):
    __tablename__ = "audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=True, index=True
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


class PlatformSetting(db.Model):
    __tablename__ = "platform_settings"
    __table_args__ = (UniqueConstraint("setting_type", "key"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    setting_type: Mapped[PlatformSettingType] = mapped_column(
        Enum(PlatformSettingType, name="platform_setting_type"), nullable=False, index=True
    )
    key: Mapped[str] = mapped_column(String(120), nullable=False)
    name: Mapped[str] = mapped_column(String(180), nullable=False)
    value: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    updated_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False, index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )


class PlatformSupportAccess(db.Model):
    __tablename__ = "platform_support_accesses"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    requested_by: Mapped[str] = mapped_column(String(180), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    authorized_by: Mapped[str | None] = mapped_column(String(180))
    scope: Mapped[str] = mapped_column(String(180), nullable=False)
    status: Mapped[str] = mapped_column(String(40), default="REGISTRADO", nullable=False)
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False, index=True
    )

    tenant: Mapped[Tenant] = relationship()


class PlatformContractEvent(db.Model):
    __tablename__ = "platform_contract_events"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    previous_status: Mapped[ContractStatus | None] = mapped_column(
        Enum(ContractStatus, name="contract_status", create_type=False)
    )
    new_status: Mapped[ContractStatus] = mapped_column(
        Enum(ContractStatus, name="contract_status", create_type=False), nullable=False
    )
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    effective_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False, index=True
    )

    tenant: Mapped[Tenant] = relationship()


class PublicLead(db.Model):
    __tablename__ = "public_leads"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    plan: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    organization: Mapped[str] = mapped_column(String(180), nullable=False)
    admin_name: Mapped[str | None] = mapped_column(String(160))
    email: Mapped[str] = mapped_column(String(254), nullable=False, index=True)
    phone: Mapped[str | None] = mapped_column(String(40))
    whatsapp: Mapped[str | None] = mapped_column(String(40))
    city: Mapped[str | None] = mapped_column(String(120))
    state: Mapped[str | None] = mapped_column(String(2))
    municipality_ibge_id: Mapped[int | None] = mapped_column(Integer)
    audience: Mapped[str | None] = mapped_column(String(80))
    preferred_contact: Mapped[str | None] = mapped_column(String(30))
    discovery_source: Mapped[str | None] = mapped_column(String(80))
    message: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(40), default="new", nullable=False, index=True)
    payment_status: Mapped[str | None] = mapped_column(String(40))
    onboarding_date: Mapped[date | None] = mapped_column(Date)
    onboarding_details: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    contact_attempts: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    contract_documents: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    payments: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    action_history: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    converted_tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("tenants.id", ondelete="SET NULL"), index=True
    )
    contract_notes: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(80), default="landing_page", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
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
    responsible: Mapped[str | None] = mapped_column(String(160))
    phone: Mapped[str | None] = mapped_column(String(40))
    source: Mapped[str | None] = mapped_column(String(80))
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
    transcription: Mapped["AudioTranscription | None"] = relationship(
        back_populates="attachment",
        cascade="all, delete-orphan",
        uselist=False,
    )
    ocr: Mapped["DocumentOcr | None"] = relationship(
        back_populates="attachment",
        cascade="all, delete-orphan",
        uselist=False,
    )


class AudioTranscription(db.Model):
    __tablename__ = "audio_transcriptions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    attachment_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("attachments.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    request_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("service_requests.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[AudioTranscriptionStatus] = mapped_column(
        Enum(AudioTranscriptionStatus, name="audio_transcription_status"),
        default=AudioTranscriptionStatus.PENDENTE,
        nullable=False,
        index=True,
    )
    review_status: Mapped[AudioTranscriptionReviewStatus] = mapped_column(
        Enum(AudioTranscriptionReviewStatus, name="audio_transcription_review_status"),
        default=AudioTranscriptionReviewStatus.PENDENTE,
        nullable=False,
        index=True,
    )
    provider: Mapped[str] = mapped_column(String(80), nullable=False)
    model: Mapped[str] = mapped_column(String(120), nullable=False)
    language: Mapped[str | None] = mapped_column(String(20))
    language_probability: Mapped[float | None] = mapped_column(Float)
    duration_seconds: Mapped[float | None] = mapped_column(Float)
    transcript: Mapped[str | None] = mapped_column(Text)
    reviewed_transcript: Mapped[str | None] = mapped_column(Text)
    segments: Mapped[list | None] = mapped_column(JSON)
    requested_by_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    reviewed_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    error: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False, index=True
    )

    attachment: Mapped[Attachment] = relationship(back_populates="transcription")


class DocumentOcr(db.Model):
    __tablename__ = "document_ocrs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    attachment_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("attachments.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    request_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("service_requests.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[DocumentOcrStatus] = mapped_column(
        Enum(DocumentOcrStatus, name="document_ocr_status"),
        default=DocumentOcrStatus.PENDENTE,
        nullable=False,
        index=True,
    )
    review_status: Mapped[DocumentOcrReviewStatus] = mapped_column(
        Enum(DocumentOcrReviewStatus, name="document_ocr_review_status"),
        default=DocumentOcrReviewStatus.PENDENTE,
        nullable=False,
        index=True,
    )
    provider: Mapped[str] = mapped_column(String(80), nullable=False)
    model: Mapped[str] = mapped_column(String(120), nullable=False)
    language: Mapped[str] = mapped_column(String(20), nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float)
    page_count: Mapped[int | None] = mapped_column(Integer)
    extracted_text: Mapped[str | None] = mapped_column(Text)
    reviewed_text: Mapped[str | None] = mapped_column(Text)
    pages: Mapped[list | None] = mapped_column(JSON)
    requested_by_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    reviewed_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    error: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False, index=True
    )

    attachment: Mapped[Attachment] = relationship(back_populates="ocr")


class LegislativeTemplate(db.Model):
    __tablename__ = "legislative_templates"
    __table_args__ = (UniqueConstraint("tenant_id", "name"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    document_type: Mapped[LegislativeDocumentType] = mapped_column(
        Enum(LegislativeDocumentType, name="legislative_document_type"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    structure: Mapped[str] = mapped_column(Text, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_by_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )


class NormativeSource(db.Model):
    __tablename__ = "normative_sources"
    __table_args__ = (UniqueConstraint("tenant_id", "title", "reference", "version"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    source_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    reference: Mapped[str] = mapped_column(String(240), nullable=False)
    excerpt: Mapped[str] = mapped_column(Text, nullable=False)
    jurisdiction: Mapped[str | None] = mapped_column(String(120))
    source_url: Mapped[str | None] = mapped_column(String(1000))
    version: Mapped[str] = mapped_column(String(80), default="1", nullable=False)
    checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    valid_from: Mapped[date | None] = mapped_column(Date)
    valid_until: Mapped[date | None] = mapped_column(Date)
    rag_collection: Mapped[str] = mapped_column(
        String(80), default="legislacao", nullable=False, index=True
    )
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    created_by_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False, index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )


class RagDocument(db.Model):
    __tablename__ = "rag_documents"
    __table_args__ = (
        UniqueConstraint("tenant_id", "title"),
        UniqueConstraint("tenant_id", "id", name="uq_rag_documents_tenant_id_id"),
        ForeignKeyConstraint(
            ["tenant_id", "created_by_id"],
            ["users.tenant_id", "users.id"],
            name="fk_rag_documents_tenant_creator",
            ondelete="RESTRICT",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    document_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    agency: Mapped[str | None] = mapped_column(String(180), index=True)
    access_level: Mapped[RagDocumentAccess] = mapped_column(
        Enum(RagDocumentAccess, name="rag_document_access"), nullable=False, index=True
    )
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    created_by_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False, index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )

    versions: Mapped[list["RagDocumentVersion"]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )


class RagDocumentVersion(db.Model):
    __tablename__ = "rag_document_versions"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_rag_document_versions_tenant_id_id"),
        UniqueConstraint("tenant_id", "document_id", "version_number"),
        UniqueConstraint("tenant_id", "document_id", "version_label"),
        ForeignKeyConstraint(
            ["tenant_id", "document_id"],
            ["rag_documents.tenant_id", "rag_documents.id"],
            name="fk_rag_document_versions_tenant_document",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "created_by_id"],
            ["users.tenant_id", "users.id"],
            name="fk_rag_document_versions_tenant_creator",
            ondelete="RESTRICT",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    document_id: Mapped[uuid.UUID] = mapped_column(nullable=False, index=True)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    version_label: Mapped[str] = mapped_column(String(80), nullable=False)
    lifecycle_status: Mapped[RagDocumentLifecycle] = mapped_column(
        Enum(RagDocumentLifecycle, name="rag_document_lifecycle"),
        default=RagDocumentLifecycle.RASCUNHO,
        nullable=False,
        index=True,
    )
    ingestion_status: Mapped[RagIngestionStatus] = mapped_column(
        Enum(RagIngestionStatus, name="rag_ingestion_status"),
        default=RagIngestionStatus.PENDENTE,
        nullable=False,
        index=True,
    )
    valid_from: Mapped[date | None] = mapped_column(Date)
    valid_until: Mapped[date | None] = mapped_column(Date)
    source_url: Mapped[str | None] = mapped_column(String(1000))
    storage_key: Mapped[str] = mapped_column(String(400), unique=True, nullable=False)
    original_name: Mapped[str] = mapped_column(String(255), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(120), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    checksum: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    extracted_text: Mapped[str | None] = mapped_column(Text)
    page_count: Mapped[int | None] = mapped_column(Integer)
    language: Mapped[str] = mapped_column(String(20), default="pt", nullable=False)
    embedding_model: Mapped[str | None] = mapped_column(String(120))
    chunk_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error: Mapped[str | None] = mapped_column(Text)
    created_by_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    indexed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False, index=True
    )

    document: Mapped[RagDocument] = relationship(back_populates="versions")
    chunks: Mapped[list["RagChunk"]] = relationship(
        back_populates="version", cascade="all, delete-orphan"
    )


class RagChunk(db.Model):
    __tablename__ = "rag_chunks"
    __table_args__ = (
        UniqueConstraint("tenant_id", "version_id", "position"),
        ForeignKeyConstraint(
            ["tenant_id", "version_id"],
            ["rag_document_versions.tenant_id", "rag_document_versions.id"],
            name="fk_rag_chunks_tenant_version",
            ondelete="CASCADE",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    version_id: Mapped[uuid.UUID] = mapped_column(nullable=False, index=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_checksum: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    page_start: Mapped[int | None] = mapped_column(Integer)
    page_end: Mapped[int | None] = mapped_column(Integer)
    section: Mapped[str | None] = mapped_column(String(240))
    embedding: Mapped[list] = mapped_column(JSON, nullable=False)
    embedding_model: Mapped[str] = mapped_column(String(120), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    version: Mapped[RagDocumentVersion] = relationship(back_populates="chunks")


class RagKnowledgeSource(db.Model):
    __tablename__ = "rag_knowledge_sources"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "source_module",
            "entity_type",
            "entity_id",
            name="uq_rag_knowledge_sources_origin",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "document_id"],
            ["rag_documents.tenant_id", "rag_documents.id"],
            name="fk_rag_knowledge_sources_tenant_document",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "latest_version_id"],
            ["rag_document_versions.tenant_id", "rag_document_versions.id"],
            name="fk_rag_knowledge_sources_tenant_version",
            ondelete="RESTRICT",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source_module: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    entity_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    entity_id: Mapped[uuid.UUID] = mapped_column(nullable=False, index=True)
    projector_version: Mapped[str] = mapped_column(
        String(32), default="1.0.0", nullable=False
    )
    source_revision: Mapped[int] = mapped_column(
        BigInteger, default=0, nullable=False
    )
    purpose: Mapped[str] = mapped_column(String(120), nullable=False)
    legal_basis: Mapped[str] = mapped_column(String(160), nullable=False)
    access_level: Mapped[RagDocumentAccess] = mapped_column(
        Enum(RagDocumentAccess, name="rag_document_access", create_type=False),
        nullable=False,
    )
    retention_until: Mapped[date | None] = mapped_column(Date)
    status: Mapped[RagKnowledgeSourceStatus] = mapped_column(
        Enum(RagKnowledgeSourceStatus, name="rag_knowledge_source_status"),
        default=RagKnowledgeSourceStatus.PENDENTE,
        nullable=False,
        index=True,
    )
    eligibility_reason: Mapped[str | None] = mapped_column(String(120))
    error_code: Mapped[str | None] = mapped_column(String(80))
    error_message: Mapped[str | None] = mapped_column(Text)
    sync_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    content_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    source_version: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    document_id: Mapped[uuid.UUID | None] = mapped_column(index=True)
    latest_version_id: Mapped[uuid.UUID | None] = mapped_column(index=True)
    last_projected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    quarantined_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    purge_completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    tombstone_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )


class RagAssistantQuery(db.Model):
    __tablename__ = "rag_assistant_queries"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "id",
            name="uq_rag_assistant_queries_tenant_id_id",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "user_id"],
            ["users.tenant_id", "users.id"],
            name="fk_rag_assistant_queries_tenant_user",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "reviewed_by_id"],
            ["users.tenant_id", "users.id"],
            name="fk_rag_assistant_queries_tenant_reviewer",
            ondelete="RESTRICT",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(nullable=False, index=True)
    query_text: Mapped[str] = mapped_column(Text, nullable=False)
    query_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    response: Mapped[str] = mapped_column(Text, nullable=False)
    sources: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    safety_flags: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    grounded: Mapped[bool] = mapped_column(Boolean, nullable=False, index=True)
    refused: Mapped[bool] = mapped_column(Boolean, nullable=False, index=True)
    evidence_threshold: Mapped[float] = mapped_column(Float, nullable=False)
    embedding_model: Mapped[str] = mapped_column(String(120), nullable=False)
    fallback_used: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    method: Mapped[str] = mapped_column(
        String(20), default="DOCUMENTAL", nullable=False, index=True
    )
    routing_reasons: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    applied_filters: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    structured_result: Mapped[dict | None] = mapped_column(JSON)
    learning_artifacts: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    feedback_rating: Mapped[RagQueryFeedbackRating | None] = mapped_column(
        Enum(RagQueryFeedbackRating, name="rag_query_feedback_rating"), index=True
    )
    feedback_comment: Mapped[str | None] = mapped_column(Text)
    corrected_response: Mapped[str | None] = mapped_column(Text)
    reviewed_by_id: Mapped[uuid.UUID | None] = mapped_column(index=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False, index=True
    )


class RagQueryFeedback(db.Model):
    __tablename__ = "rag_query_feedback"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "id",
            name="uq_rag_query_feedback_tenant_id_id",
        ),
        UniqueConstraint(
            "tenant_id",
            "query_id",
            "revision",
            name="uq_rag_query_feedback_revision",
        ),
        UniqueConstraint(
            "tenant_id",
            "query_id",
            "idempotency_key",
            name="uq_rag_query_feedback_idempotency",
        ),
        CheckConstraint(
            "revision > 0",
            name="ck_rag_query_feedback_revision_positive",
        ),
        CheckConstraint(
            "expected_method IS NULL OR expected_method IN "
            "('DOCUMENTAL', 'ESTRUTURADO', 'HIBRIDO')",
            name="ck_rag_query_feedback_expected_method",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "query_id"],
            ["rag_assistant_queries.tenant_id", "rag_assistant_queries.id"],
            name="fk_rag_query_feedback_tenant_query",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "previous_feedback_id"],
            ["rag_query_feedback.tenant_id", "rag_query_feedback.id"],
            name="fk_rag_query_feedback_tenant_previous",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "created_by_id"],
            ["users.tenant_id", "users.id"],
            name="fk_rag_query_feedback_tenant_creator",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "moderated_by_id"],
            ["users.tenant_id", "users.id"],
            name="fk_rag_query_feedback_tenant_moderator",
            ondelete="RESTRICT",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    query_id: Mapped[uuid.UUID] = mapped_column(nullable=False, index=True)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    previous_feedback_id: Mapped[uuid.UUID | None] = mapped_column(index=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(120))
    rating: Mapped[RagQueryFeedbackRating] = mapped_column(
        Enum(RagQueryFeedbackRating, name="rag_query_feedback_rating"),
        nullable=False,
        index=True,
    )
    reasons: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    comment: Mapped[str | None] = mapped_column(Text)
    corrected_response: Mapped[str | None] = mapped_column(Text)
    expected_method: Mapped[str | None] = mapped_column(String(20))
    expected_filters: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    status: Mapped[RagFeedbackStatus] = mapped_column(
        Enum(RagFeedbackStatus, name="rag_feedback_status"),
        nullable=False,
        index=True,
    )
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    created_by_id: Mapped[uuid.UUID] = mapped_column(nullable=False, index=True)
    moderation_mode: Mapped[RagFeedbackModerationMode | None] = mapped_column(
        Enum(RagFeedbackModerationMode, name="rag_feedback_moderation_mode")
    )
    moderation_rule: Mapped[str | None] = mapped_column(String(120))
    moderated_by_id: Mapped[uuid.UUID | None] = mapped_column(index=True)
    moderated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    moderation_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False, index=True
    )


class RagFeedbackSourceJudgment(db.Model):
    __tablename__ = "rag_feedback_source_judgments"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "feedback_id",
            "document_id",
            "version_id",
            name="uq_rag_feedback_source_judgment",
        ),
        CheckConstraint(
            "source_scope IN ('GLOBAL', 'PRIVADO')",
            name="ck_rag_feedback_source_scope",
        ),
        CheckConstraint(
            "original_position IS NULL OR original_position >= 0",
            name="ck_rag_feedback_source_position",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "feedback_id"],
            ["rag_query_feedback.tenant_id", "rag_query_feedback.id"],
            name="fk_rag_feedback_source_judgments_tenant_feedback",
            ondelete="CASCADE",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    feedback_id: Mapped[uuid.UUID] = mapped_column(nullable=False, index=True)
    document_id: Mapped[uuid.UUID] = mapped_column(nullable=False, index=True)
    version_id: Mapped[uuid.UUID] = mapped_column(nullable=False, index=True)
    chunk_id: Mapped[uuid.UUID | None] = mapped_column(index=True)
    source_scope: Mapped[str] = mapped_column(String(10), nullable=False)
    judgment: Mapped[RagFeedbackSourceJudgmentValue] = mapped_column(
        Enum(
            RagFeedbackSourceJudgmentValue,
            name="rag_feedback_source_judgment",
        ),
        nullable=False,
        index=True,
    )
    reason: Mapped[RagFeedbackReason] = mapped_column(
        Enum(RagFeedbackReason, name="rag_feedback_reason"),
        nullable=False,
        index=True,
    )
    original_position: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )


class RagLearningRun(db.Model):
    __tablename__ = "rag_learning_runs"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "id",
            name="uq_rag_learning_runs_tenant_id_id",
        ),
        UniqueConstraint(
            "tenant_id",
            "window_start",
            "window_end",
            "configuration_hash",
            name="uq_rag_learning_runs_idempotency",
        ),
        CheckConstraint(
            "window_start < window_end",
            name="ck_rag_learning_runs_window",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "initiated_by_id"],
            ["users.tenant_id", "users.id"],
            name="fk_rag_learning_runs_tenant_initiator",
            ondelete="RESTRICT",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    window_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    window_end: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    configuration: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    configuration_hash: Mapped[str] = mapped_column(
        String(64), nullable=False, index=True
    )
    baseline: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    total_feedbacks: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_approved: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_quarantine: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    metrics: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    status: Mapped[RagLearningRunStatus] = mapped_column(
        Enum(RagLearningRunStatus, name="rag_learning_run_status"),
        default=RagLearningRunStatus.PENDENTE,
        nullable=False,
        index=True,
    )
    error: Mapped[str | None] = mapped_column(Text)
    initiated_by_id: Mapped[uuid.UUID] = mapped_column(nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False, index=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class RagLearningArtifact(db.Model):
    __tablename__ = "rag_learning_artifacts"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "id",
            name="uq_rag_learning_artifacts_tenant_id_id",
        ),
        UniqueConstraint(
            "tenant_id",
            "artifact_type",
            "version",
            name="uq_rag_learning_artifacts_version",
        ),
        CheckConstraint(
            "version > 0",
            name="ck_rag_learning_artifacts_version_positive",
        ),
        CheckConstraint(
            "rollout_percentage >= 0 AND rollout_percentage <= 100",
            name="ck_rag_learning_artifacts_rollout_percentage",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "run_id"],
            ["rag_learning_runs.tenant_id", "rag_learning_runs.id"],
            name="fk_rag_learning_artifacts_tenant_run",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "approved_by_id"],
            ["users.tenant_id", "users.id"],
            name="fk_rag_learning_artifacts_tenant_approver",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "activated_by_id"],
            ["users.tenant_id", "users.id"],
            name="fk_rag_learning_artifacts_tenant_activator",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "replaced_by_id"],
            ["rag_learning_artifacts.tenant_id", "rag_learning_artifacts.id"],
            name="fk_rag_learning_artifacts_tenant_replacement",
            ondelete="RESTRICT",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    run_id: Mapped[uuid.UUID] = mapped_column(nullable=False, index=True)
    artifact_type: Mapped[RagLearningArtifactType] = mapped_column(
        Enum(RagLearningArtifactType, name="rag_learning_artifact_type"),
        nullable=False,
        index=True,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    source_feedback_ids: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    baseline: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    metrics_before: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    metrics_after: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    evaluation_details: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    status: Mapped[RagLearningArtifactStatus] = mapped_column(
        Enum(RagLearningArtifactStatus, name="rag_learning_artifact_status"),
        default=RagLearningArtifactStatus.CANDIDATO,
        nullable=False,
        index=True,
    )
    approved_by_id: Mapped[uuid.UUID | None] = mapped_column(index=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    activated_by_id: Mapped[uuid.UUID | None] = mapped_column(index=True)
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    activation_mode: Mapped[str | None] = mapped_column(String(20))
    rollout_percentage: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    online_metrics: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    replaced_by_id: Mapped[uuid.UUID | None] = mapped_column(index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revocation_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False, index=True
    )


class RagLearningArtifactFeedback(db.Model):
    __tablename__ = "rag_learning_artifact_feedback"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "artifact_id",
            "feedback_id",
            name="uq_rag_learning_artifact_feedback",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "artifact_id"],
            ["rag_learning_artifacts.tenant_id", "rag_learning_artifacts.id"],
            name="fk_rag_learning_artifact_feedback_tenant_artifact",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "feedback_id"],
            ["rag_query_feedback.tenant_id", "rag_query_feedback.id"],
            name="fk_rag_learning_artifact_feedback_tenant_feedback",
            ondelete="RESTRICT",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    artifact_id: Mapped[uuid.UUID] = mapped_column(nullable=False, index=True)
    feedback_id: Mapped[uuid.UUID] = mapped_column(nullable=False, index=True)
    contribution: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )


class RagThematicMemory(db.Model):
    __tablename__ = "rag_thematic_memories"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "generated_by_id"],
            ["users.tenant_id", "users.id"],
            name="fk_rag_thematic_memories_tenant_generator",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "tenant_id",
            "theme",
            "territory",
            "period_start",
            "period_end",
            name="uq_rag_thematic_memory_scope",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    theme: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    territory: Mapped[str] = mapped_column(String(160), default="", nullable=False, index=True)
    period_start: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    period_end: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    request_count: Mapped[int] = mapped_column(Integer, nullable=False)
    resolved_count: Mapped[int] = mapped_column(Integer, nullable=False)
    high_priority_count: Mapped[int] = mapped_column(Integer, nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    generated_by_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )


class RagEvaluationQuestion(db.Model):
    __tablename__ = "rag_evaluation_questions"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "source_feedback_id",
            name="uq_rag_evaluation_questions_source_feedback",
        ),
        UniqueConstraint(
            "tenant_id",
            "source_query_id",
            name="uq_rag_evaluation_questions_source_query",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "created_by_id"],
            ["users.tenant_id", "users.id"],
            name="fk_rag_evaluation_questions_tenant_creator",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "curated_by_id"],
            ["users.tenant_id", "users.id"],
            name="fk_rag_evaluation_questions_tenant_curator",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "source_feedback_id"],
            ["rag_query_feedback.tenant_id", "rag_query_feedback.id"],
            name="fk_rag_evaluation_questions_tenant_feedback",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "source_query_id"],
            ["rag_assistant_queries.tenant_id", "rag_assistant_queries.id"],
            name="fk_rag_evaluation_questions_tenant_query",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "case_origin IN ('MANUAL', 'FEEDBACK', 'REGRESSAO')",
            name="ck_rag_evaluation_questions_origin",
        ),
        CheckConstraint(
            "severity IN ('BAIXA', 'MEDIA', 'ALTA', 'CRITICA')",
            name="ck_rag_evaluation_questions_severity",
        ),
        CheckConstraint(
            "expected_method IS NULL OR expected_method IN "
            "('DOCUMENTAL', 'ESTRUTURADO', 'HIBRIDO')",
            name="ck_rag_evaluation_questions_expected_method",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    question: Mapped[str] = mapped_column(Text, nullable=False)
    expected_document_ids: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    expected_source_refs: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    hard_negative_source_refs: Mapped[list] = mapped_column(
        JSON, default=list, nullable=False
    )
    expected_refusal: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    expected_method: Mapped[str | None] = mapped_column(String(20), index=True)
    expected_filters: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    case_origin: Mapped[str] = mapped_column(
        String(20), default="MANUAL", nullable=False, index=True
    )
    failure_reasons: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    severity: Mapped[str] = mapped_column(
        String(10), default="MEDIA", nullable=False, index=True
    )
    tags: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    baseline_snapshot: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    baseline_captured_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    source_query_id: Mapped[uuid.UUID | None] = mapped_column(index=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    source_feedback_id: Mapped[uuid.UUID | None] = mapped_column(index=True)
    curated_by_id: Mapped[uuid.UUID | None] = mapped_column(index=True)
    curated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deactivation_reason: Mapped[str | None] = mapped_column(String(120))
    created_by_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False, index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )


class RagEvaluationRun(db.Model):
    __tablename__ = "rag_evaluation_runs"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "created_by_id"],
            ["users.tenant_id", "users.id"],
            name="fk_rag_evaluation_runs_tenant_creator",
            ondelete="RESTRICT",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    k: Mapped[int] = mapped_column(Integer, nullable=False)
    question_count: Mapped[int] = mapped_column(Integer, nullable=False)
    precision_at_k: Mapped[float] = mapped_column(Float, nullable=False)
    recall_at_k: Mapped[float] = mapped_column(Float, nullable=False)
    groundedness: Mapped[float] = mapped_column(Float, nullable=False)
    citation_precision: Mapped[float] = mapped_column(Float, nullable=False)
    disconnected_source_rate: Mapped[float] = mapped_column(Float, nullable=False)
    refusal_accuracy: Mapped[float] = mapped_column(Float, nullable=False)
    routing_accuracy: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    filter_accuracy: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    hard_negative_rate: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    results: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    created_by_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False, index=True
    )


class GlobalKnowledgeCollection(db.Model):
    __tablename__ = "collections"
    __table_args__ = (
        UniqueConstraint("name", name="uq_rag_global_collections_name"),
        {"schema": "rag_global"},
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(180), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    distribution_policy: Mapped[GlobalDistributionPolicy] = mapped_column(
        Enum(GlobalDistributionPolicy, name="rag_global_distribution_policy"),
        nullable=False,
        index=True,
    )
    jurisdiction: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    status: Mapped[GlobalCatalogStatus] = mapped_column(
        Enum(GlobalCatalogStatus, name="rag_global_catalog_status"),
        default=GlobalCatalogStatus.RASCUNHO,
        nullable=False,
        index=True,
    )
    created_by_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False, index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )

    documents: Mapped[list["GlobalKnowledgeDocument"]] = relationship(
        back_populates="collection", cascade="all, delete-orphan"
    )


class GlobalKnowledgeDocument(db.Model):
    __tablename__ = "documents"
    __table_args__ = (
        UniqueConstraint(
            "collection_id",
            "title",
            name="uq_rag_global_documents_collection_title",
        ),
        {"schema": "rag_global"},
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    collection_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("rag_global.collections.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    document_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    agency: Mapped[str | None] = mapped_column(String(180), index=True)
    jurisdiction: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    provenance: Mapped[str] = mapped_column(Text, nullable=False)
    confidence_level: Mapped[float | None] = mapped_column(Float)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    created_by_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False, index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )

    collection: Mapped[GlobalKnowledgeCollection] = relationship(back_populates="documents")
    versions: Mapped[list["GlobalKnowledgeDocumentVersion"]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )


class GlobalKnowledgeDocumentVersion(db.Model):
    __tablename__ = "document_versions"
    __table_args__ = (
        UniqueConstraint(
            "document_id",
            "version_number",
            name="uq_rag_global_document_versions_number",
        ),
        UniqueConstraint(
            "document_id",
            "version_label",
            name="uq_rag_global_document_versions_label",
        ),
        {"schema": "rag_global"},
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("rag_global.documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    version_label: Mapped[str] = mapped_column(String(80), nullable=False)
    valid_from: Mapped[date | None] = mapped_column(Date)
    valid_until: Mapped[date | None] = mapped_column(Date)
    source_url: Mapped[str | None] = mapped_column(String(1000))
    storage_key: Mapped[str] = mapped_column(String(400), unique=True, nullable=False)
    original_name: Mapped[str] = mapped_column(String(255), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(120), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    checksum: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    extracted_text: Mapped[str | None] = mapped_column(Text)
    page_count: Mapped[int | None] = mapped_column(Integer)
    language: Mapped[str] = mapped_column(String(20), default="pt", nullable=False)
    embedding_model: Mapped[str | None] = mapped_column(String(120))
    chunk_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    ingestion_status: Mapped[RagIngestionStatus] = mapped_column(
        Enum(RagIngestionStatus, name="rag_ingestion_status", create_type=False),
        default=RagIngestionStatus.PENDENTE,
        nullable=False,
        index=True,
    )
    publication_status: Mapped[GlobalVersionStatus] = mapped_column(
        Enum(GlobalVersionStatus, name="rag_global_version_status"),
        default=GlobalVersionStatus.RASCUNHO,
        nullable=False,
        index=True,
    )
    error: Mapped[str | None] = mapped_column(Text)
    created_by_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    published_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    indexed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False, index=True
    )

    document: Mapped[GlobalKnowledgeDocument] = relationship(back_populates="versions")
    chunks: Mapped[list["GlobalKnowledgeChunk"]] = relationship(
        back_populates="version", cascade="all, delete-orphan"
    )


class GlobalKnowledgeChunk(db.Model):
    __tablename__ = "chunks"
    __table_args__ = (
        UniqueConstraint(
            "version_id",
            "position",
            name="uq_rag_global_chunks_version_position",
        ),
        {"schema": "rag_global"},
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("rag_global.document_versions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_checksum: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    page_start: Mapped[int | None] = mapped_column(Integer)
    page_end: Mapped[int | None] = mapped_column(Integer)
    section: Mapped[str | None] = mapped_column(String(240))
    embedding: Mapped[list] = mapped_column(JSON, nullable=False)
    embedding_model: Mapped[str] = mapped_column(String(120), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    version: Mapped[GlobalKnowledgeDocumentVersion] = relationship(back_populates="chunks")


class GlobalKnowledgeEntitlement(db.Model):
    __tablename__ = "rag_global_entitlements"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "collection_id",
            name="uq_rag_global_entitlements_tenant_collection",
        ),
        CheckConstraint(
            "(update_mode = 'AUTOMATICA' AND pinned_version_id IS NULL) "
            "OR (update_mode = 'FIXADA' AND pinned_version_id IS NOT NULL)",
            name="ck_rag_global_entitlements_update_mode",
        ),
        CheckConstraint(
            "valid_until IS NULL OR valid_from IS NULL OR valid_until >= valid_from",
            name="ck_rag_global_entitlements_validity",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    collection_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("rag_global.collections.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status: Mapped[GlobalEntitlementStatus] = mapped_column(
        Enum(GlobalEntitlementStatus, name="rag_global_entitlement_status"),
        nullable=False,
        default=GlobalEntitlementStatus.ATIVA,
        index=True,
    )
    update_mode: Mapped[GlobalUpdateMode] = mapped_column(
        Enum(GlobalUpdateMode, name="rag_global_update_mode"),
        nullable=False,
        default=GlobalUpdateMode.AUTOMATICA,
    )
    pinned_version_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("rag_global.document_versions.id", ondelete="RESTRICT"),
        index=True,
    )
    grant_source: Mapped[str] = mapped_column(String(40), nullable=False)
    justification: Mapped[str | None] = mapped_column(Text)
    granted_by_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    valid_from: Mapped[date | None] = mapped_column(Date)
    valid_until: Mapped[date | None] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False, index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )

    tenant: Mapped[Tenant] = relationship()
    collection: Mapped[GlobalKnowledgeCollection] = relationship()
    pinned_version: Mapped[GlobalKnowledgeDocumentVersion | None] = relationship()


class LegislativeDraft(db.Model):
    __tablename__ = "legislative_drafts"
    __table_args__ = (UniqueConstraint("tenant_id", "protocol_number"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    document_type: Mapped[LegislativeDocumentType] = mapped_column(
        Enum(LegislativeDocumentType, name="legislative_document_type", create_type=False),
        nullable=False,
        index=True,
    )
    status: Mapped[LegislativeDraftStatus] = mapped_column(
        Enum(LegislativeDraftStatus, name="legislative_draft_status"),
        default=LegislativeDraftStatus.RASCUNHO,
        nullable=False,
        index=True,
    )
    generation_status: Mapped[LegislativeGenerationStatus] = mapped_column(
        Enum(LegislativeGenerationStatus, name="legislative_generation_status"),
        default=LegislativeGenerationStatus.PENDENTE,
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    content: Mapped[str | None] = mapped_column(Text)
    justification: Mapped[str | None] = mapped_column(Text)
    legal_basis: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    sources: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    unsupported_passages: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    similar_proposals: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    generation_metadata: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    template_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("legislative_templates.id", ondelete="SET NULL"), index=True
    )
    ai_execution_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("ai_executions.id", ondelete="SET NULL"), unique=True, index=True
    )
    current_version: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    protocol_number: Mapped[str | None] = mapped_column(String(100))
    protocolled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    current_tramitation_status: Mapped[LegislativeTramitationStatus | None] = mapped_column(
        Enum(LegislativeTramitationStatus, name="legislative_tramitation_status"),
        index=True,
    )
    created_by_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    reviewed_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    approved_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False, index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )


class LegislativeDraftRequest(db.Model):
    __tablename__ = "legislative_draft_requests"
    __table_args__ = (UniqueConstraint("draft_id", "request_id"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    draft_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("legislative_drafts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    request_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("service_requests.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )


class LegislativeDraftVersion(db.Model):
    __tablename__ = "legislative_draft_versions"
    __table_args__ = (UniqueConstraint("draft_id", "version_number"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    draft_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("legislative_drafts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    justification: Mapped[str | None] = mapped_column(Text)
    legal_basis: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    unsupported_passages: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    change_reason: Mapped[str] = mapped_column(String(500), nullable=False)
    created_by_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False, index=True
    )


class LegislativeTramitation(db.Model):
    __tablename__ = "legislative_tramitations"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    draft_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("legislative_drafts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[LegislativeTramitationStatus] = mapped_column(
        Enum(
            LegislativeTramitationStatus,
            name="legislative_tramitation_status",
            create_type=False,
        ),
        nullable=False,
        index=True,
    )
    stage: Mapped[str] = mapped_column(String(160), nullable=False)
    destination: Mapped[str | None] = mapped_column(String(180))
    external_reference: Mapped[str | None] = mapped_column(String(180))
    notes: Mapped[str | None] = mapped_column(Text)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    created_by_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False, index=True
    )


class AgendaEvent(db.Model):
    __tablename__ = "agenda_events"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    event_type: Mapped[AgendaEventType] = mapped_column(
        Enum(AgendaEventType, name="agenda_event_type"), nullable=False, index=True
    )
    status: Mapped[AgendaEventStatus] = mapped_column(
        Enum(AgendaEventStatus, name="agenda_event_status"),
        default=AgendaEventStatus.AGENDADO,
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(180), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    location: Mapped[str | None] = mapped_column(String(500))
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    citizen_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("citizens.id", ondelete="SET NULL"), index=True
    )
    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="SET NULL"), index=True
    )
    territory_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("territories.id", ondelete="SET NULL"), index=True
    )
    request_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("service_requests.id", ondelete="SET NULL"), index=True
    )
    minutes: Mapped[str | None] = mapped_column(Text)
    photos: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    participants: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    pending_items: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    created_by_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False, index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )


class OversightAction(db.Model):
    __tablename__ = "oversight_actions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    status: Mapped[OversightActionStatus] = mapped_column(
        Enum(OversightActionStatus, name="oversight_action_status"),
        default=OversightActionStatus.PLANEJADA,
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(180), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    location: Mapped[str | None] = mapped_column(String(500))
    occurred_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    agency_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("external_agencies.id", ondelete="SET NULL"), index=True
    )
    request_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("service_requests.id", ondelete="SET NULL"), index=True
    )
    findings: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    photos: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    responsible_parties: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    report: Mapped[str | None] = mapped_column(Text)
    follow_up_actions: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    created_by_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False, index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )


class IntegrationSetting(db.Model):
    __tablename__ = "integration_settings"
    __table_args__ = (UniqueConstraint("tenant_id", "integration_type"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    integration_type: Mapped[IntegrationType] = mapped_column(
        Enum(IntegrationType, name="integration_type"), nullable=False, index=True
    )
    status: Mapped[IntegrationStatus] = mapped_column(
        Enum(IntegrationStatus, name="integration_status"),
        default=IntegrationStatus.RASCUNHO,
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    config: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    secrets_configured: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    updated_by_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False, index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )


class ChannelMessage(db.Model):
    __tablename__ = "channel_messages"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    channel: Mapped[RequestSource] = mapped_column(
        Enum(RequestSource, name="request_source", create_type=False),
        nullable=False,
        index=True,
    )
    status: Mapped[ChannelMessageStatus] = mapped_column(
        Enum(ChannelMessageStatus, name="channel_message_status"),
        default=ChannelMessageStatus.RECEBIDA,
        nullable=False,
        index=True,
    )
    sender_name: Mapped[str | None] = mapped_column(String(180))
    sender_contact: Mapped[str | None] = mapped_column(String(254))
    subject: Mapped[str | None] = mapped_column(String(180))
    content: Mapped[str] = mapped_column(Text, nullable=False)
    external_id: Mapped[str | None] = mapped_column(String(160), index=True)
    metadata_data: Mapped[dict] = mapped_column("metadata", JSON, default=dict, nullable=False)
    request_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("service_requests.id", ondelete="SET NULL"), index=True
    )
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False, index=True
    )
    reviewed_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


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
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=True, index=True
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
    processing_duration_ms: Mapped[int | None] = mapped_column(Integer)


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
