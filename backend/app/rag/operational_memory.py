import hashlib
import json
import re
import time
import uuid
from datetime import UTC, date, datetime, timedelta

from flask import current_app, has_app_context
from sqlalchemy import event, inspect, select
from sqlalchemy.orm import Session

from app.extensions import db
from app.models import (
    AgendaEvent,
    AgendaEventStatus,
    AudioTranscription,
    AudioTranscriptionReviewStatus,
    AudioTranscriptionStatus,
    AuditLog,
    Citizen,
    DocumentOcr,
    DocumentOcrReviewStatus,
    DocumentOcrStatus,
    ExternalAgency,
    ForwardingStatus,
    LegislativeDraft,
    LegislativeDraftStatus,
    LegislativeDraftVersion,
    LegislativeGenerationStatus,
    LegislativeTramitation,
    OutboxEvent,
    OversightAction,
    OversightActionStatus,
    RagDocument,
    RagDocumentAccess,
    RagDocumentLifecycle,
    RagDocumentVersion,
    RagIngestionStatus,
    RagKnowledgeSource,
    RagKnowledgeSourceStatus,
    RagThematicMemory,
    RequestForwarding,
    RequestInteraction,
    RequestStatus,
    RetentionPolicy,
    ServiceRequest,
)
from app.rag.content_security import has_prompt_injection
from app.rag.projectors import (
    OperationalMemoryProjector,
    Projection,
    ProjectorAction,
    ProjectorDefinition,
    ProjectorRegistry,
)
from app.rag.service import RAG_INGESTION_EVENT, enqueue_ingestion
from app.rag.storage import delete_rag_object, store_generated_rag_text

OPERATIONAL_MEMORY_EVENT = "SincronizacaoMemoriaOperacional"
OPERATIONAL_MEMORY_EVENT_SCHEMA_VERSION = 2
SERVICE_REQUEST_ENTITY = "SERVICE_REQUEST"
REQUEST_FORWARDING_ENTITY = "REQUEST_FORWARDING"
LEGISLATIVE_DRAFT_ENTITY = "LEGISLATIVE_DRAFT"
LEGISLATIVE_TRAMITATION_ENTITY = "LEGISLATIVE_TRAMITATION"
DOCUMENT_OCR_ENTITY = "DOCUMENT_OCR"
AUDIO_TRANSCRIPTION_ENTITY = "AUDIO_TRANSCRIPTION"
AGENDA_EVENT_ENTITY = "AGENDA_EVENT"
OVERSIGHT_ACTION_ENTITY = "OVERSIGHT_ACTION"
THEMATIC_MEMORY_ENTITY = "THEMATIC_MEMORY"
_REGISTERED = False
_REDACTED = "[DADO_PESSOAL_REMOVIDO]"


class ServiceRequestProjector:
    definition = ProjectorDefinition(
        module="SOLICITACOES",
        entity_type=SERVICE_REQUEST_ENTITY,
        version="1.0.0",
        owner="Módulo de Solicitações",
        supported_actions=frozenset(
            {
                ProjectorAction.CREATE,
                ProjectorAction.UPDATE,
                ProjectorAction.CANCEL,
                ProjectorAction.DELETE,
                ProjectorAction.ANONYMIZE,
                ProjectorAction.RETENTION_EXPIRED,
                ProjectorAction.RECONCILE,
            }
        ),
        field_allowlist=frozenset(
            {
                "protocol",
                "title",
                "description",
                "status",
                "priority",
                "category",
                "subcategory",
                "theme",
                "impact",
                "urgency",
                "closing_reason",
                "closing_evidence",
                "citizen.legal_basis",
                "interactions.interaction_type",
                "interactions.channel",
                "interactions.direction",
                "interactions.content",
            }
        ),
        purpose="ATENDIMENTO_E_PLANEJAMENTO_LEGISLATIVO",
        default_legal_basis="EXERCICIO_REGULAR_DE_DIREITOS",
        access_level=RagDocumentAccess.INTERNO,
        retention_data_type="SOLICITACAO",
        quarantine_policy="SANITIZE_PII_AND_REJECT_INSTRUCTION_ONLY_CONTENT",
        purge_policy="PURGE_DERIVED_CONTENT_ON_SOURCE_DELETION",
    )

    def project(self, tenant_id: uuid.UUID, entity_id: uuid.UUID) -> Projection:
        item = db.session.get(ServiceRequest, entity_id)
        if item is None or item.tenant_id != tenant_id:
            return _ineligible(self.definition, "ENTITY_NOT_FOUND")
        retention_until = _retention_until(
            tenant_id, self.definition.retention_data_type, item.created_at
        )
        if retention_until and retention_until < datetime.now(UTC).date():
            return _ineligible(
                self.definition, "RETENTION_EXPIRED", retention_until
            )
        if item.status == RequestStatus.CANCELADA:
            return _ineligible(
                self.definition, "ENTITY_CANCELLED", retention_until
            )
        citizen = db.session.get(Citizen, item.citizen_id) if item.citizen_id else None
        legal_basis = (
            citizen.legal_basis
            if citizen is not None and citizen.tenant_id == tenant_id
            else self.definition.default_legal_basis
        )
        return Projection(
            True,
            None,
            f"Solicitação {item.protocol}: {item.title or 'sem título'}",
            "MEMORIA_SOLICITACAO",
            self.definition.purpose,
            legal_basis,
            self.definition.access_level,
            retention_until,
            _render_request(item),
        )

    def created_by(
        self, tenant_id: uuid.UUID, entity_id: uuid.UUID
    ) -> uuid.UUID:
        item = db.session.get(ServiceRequest, entity_id)
        if item is None or item.tenant_id != tenant_id:
            raise ValueError("Entidade de memória operacional não encontrada.")
        return item.created_by_id

    def entity_ids(self, tenant_id: uuid.UUID):
        return db.session.scalars(
            select(ServiceRequest.id).where(ServiceRequest.tenant_id == tenant_id)
        )


class RequestForwardingProjector:
    definition = ProjectorDefinition(
        module="SOLICITACOES",
        entity_type=REQUEST_FORWARDING_ENTITY,
        version="1.0.0",
        owner="Módulo de Solicitações",
        supported_actions=frozenset(
            {
                ProjectorAction.CREATE,
                ProjectorAction.UPDATE,
                ProjectorAction.CANCEL,
                ProjectorAction.DELETE,
                ProjectorAction.ANONYMIZE,
                ProjectorAction.RETENTION_EXPIRED,
                ProjectorAction.RECONCILE,
            }
        ),
        field_allowlist=frozenset(
            {
                "request.protocol",
                "request.title",
                "agency.name",
                "external_protocol",
                "notes",
                "status",
                "response",
                "response_at",
                "due_at",
            }
        ),
        purpose="ACOMPANHAMENTO_DE_ENCAMINHAMENTOS_E_RESPOSTAS_OFICIAIS",
        default_legal_basis="EXERCICIO_REGULAR_DE_DIREITOS",
        access_level=RagDocumentAccess.INTERNO,
        retention_data_type="SOLICITACAO",
        quarantine_policy="SANITIZE_PII_AND_QUARANTINE_SUSPICIOUS_OFFICIAL_CONTENT",
        purge_policy="PURGE_DERIVED_CONTENT_WITH_REQUEST_OR_FORWARDING",
    )

    def project(self, tenant_id: uuid.UUID, entity_id: uuid.UUID) -> Projection:
        item = db.session.get(RequestForwarding, entity_id)
        if item is None or item.tenant_id != tenant_id:
            return _ineligible(self.definition, "ENTITY_NOT_FOUND")
        service_request = item.request
        if service_request is None or service_request.tenant_id != tenant_id:
            return _ineligible(self.definition, "PARENT_ENTITY_NOT_FOUND")
        retention_until = _retention_until(
            tenant_id, self.definition.retention_data_type, service_request.created_at
        )
        if retention_until and retention_until < datetime.now(UTC).date():
            return _ineligible(
                self.definition, "RETENTION_EXPIRED", retention_until
            )
        if service_request.status == RequestStatus.CANCELADA:
            return _ineligible(
                self.definition, "PARENT_ENTITY_CANCELLED", retention_until
            )
        agency = db.session.get(ExternalAgency, item.agency_id)
        agency_name = (
            agency.name
            if agency is not None and agency.tenant_id == tenant_id
            else "Órgão externo"
        )
        is_official_response = (
            item.status == ForwardingStatus.RESPONDIDO
            and bool((item.response or "").strip())
        )
        return Projection(
            True,
            None,
            (
                f"Resposta de {agency_name} à solicitação {service_request.protocol}"
                if is_official_response
                else (
                    f"Encaminhamento da solicitação {service_request.protocol} "
                    f"para {agency_name}"
                )
            ),
            (
                "MEMORIA_RESPOSTA_ORGAO"
                if is_official_response
                else "MEMORIA_ENCAMINHAMENTO"
            ),
            self.definition.purpose,
            self.definition.default_legal_basis,
            self.definition.access_level,
            retention_until,
            _render_forwarding(item, service_request, agency_name),
        )

    def created_by(
        self, tenant_id: uuid.UUID, entity_id: uuid.UUID
    ) -> uuid.UUID:
        item = db.session.get(RequestForwarding, entity_id)
        if item is None or item.tenant_id != tenant_id:
            raise ValueError("Entidade de memória operacional não encontrada.")
        return item.created_by_id

    def entity_ids(self, tenant_id: uuid.UUID):
        return db.session.scalars(
            select(RequestForwarding.id).where(
                RequestForwarding.tenant_id == tenant_id
            )
        )


class LegislativeTramitationProjector:
    definition = ProjectorDefinition(
        module="LEGISLATIVO",
        entity_type=LEGISLATIVE_TRAMITATION_ENTITY,
        version="1.0.0",
        owner="Módulo Legislativo",
        supported_actions=frozenset(ProjectorAction),
        field_allowlist=frozenset(
            {
                "draft.document_type",
                "draft.title",
                "draft.protocol_number",
                "status",
                "stage",
                "destination",
                "external_reference",
                "notes",
                "occurred_at",
            }
        ),
        purpose="ACOMPANHAMENTO_DA_TRAMITACAO_LEGISLATIVA",
        default_legal_basis="EXERCICIO_DA_FUNCAO_LEGISLATIVA",
        access_level=RagDocumentAccess.INTERNO,
        retention_data_type="DOCUMENTO_LEGISLATIVO",
        quarantine_policy="SANITIZE_PII_AND_QUARANTINE_SUSPICIOUS_NOTES",
        purge_policy="PURGE_DERIVED_CONTENT_WITH_DRAFT_OR_TRAMITATION",
    )

    def project(self, tenant_id: uuid.UUID, entity_id: uuid.UUID) -> Projection:
        item = db.session.get(LegislativeTramitation, entity_id)
        if item is None or item.tenant_id != tenant_id:
            return _ineligible(self.definition, "ENTITY_NOT_FOUND")
        draft = db.session.get(LegislativeDraft, item.draft_id)
        if draft is None or draft.tenant_id != tenant_id:
            return _ineligible(self.definition, "PARENT_ENTITY_NOT_FOUND")
        retention_until = _retention_until(
            tenant_id, self.definition.retention_data_type, draft.created_at
        )
        if retention_until and retention_until < datetime.now(UTC).date():
            return _ineligible(
                self.definition, "RETENTION_EXPIRED", retention_until
            )
        if (
            draft.status != LegislativeDraftStatus.APROVADA
            or not draft.protocol_number
        ):
            return _ineligible(
                self.definition, "DRAFT_NOT_APPROVED_OR_PROTOCOLLED", retention_until
            )
        return Projection(
            True,
            None,
            f"Tramitação {draft.protocol_number}: {item.stage}",
            "MEMORIA_TRAMITACAO_LEGISLATIVA",
            self.definition.purpose,
            self.definition.default_legal_basis,
            self.definition.access_level,
            retention_until,
            _render_tramitation(item, draft),
        )

    def created_by(self, tenant_id: uuid.UUID, entity_id: uuid.UUID) -> uuid.UUID:
        item = db.session.get(LegislativeTramitation, entity_id)
        if item is None or item.tenant_id != tenant_id:
            raise ValueError("Entidade de memória operacional não encontrada.")
        return item.created_by_id

    def entity_ids(self, tenant_id: uuid.UUID):
        return db.session.scalars(
            select(LegislativeTramitation.id).where(
                LegislativeTramitation.tenant_id == tenant_id
            )
        )


class DocumentOcrProjector:
    definition = ProjectorDefinition(
        module="SOLICITACOES",
        entity_type=DOCUMENT_OCR_ENTITY,
        version="1.0.0",
        owner="Módulo de Solicitações",
        supported_actions=frozenset(ProjectorAction),
        field_allowlist=frozenset(
            {
                "request.protocol",
                "request.title",
                "attachment.original_name",
                "language",
                "review_status",
                "reviewed_text",
                "reviewed_at",
            }
        ),
        purpose="EVIDENCIA_DOCUMENTAL_REVISADA_DE_ATENDIMENTO",
        default_legal_basis="EXERCICIO_REGULAR_DE_DIREITOS",
        access_level=RagDocumentAccess.RESTRITO,
        retention_data_type="SOLICITACAO",
        quarantine_policy="REQUIRE_HUMAN_REVIEW_AND_QUARANTINE_SUSPICIOUS_CONTENT",
        purge_policy="PURGE_DERIVED_CONTENT_WITH_ATTACHMENT_OR_REQUEST",
    )

    def project(self, tenant_id: uuid.UUID, entity_id: uuid.UUID) -> Projection:
        item = db.session.get(DocumentOcr, entity_id)
        if item is None or item.tenant_id != tenant_id:
            return _ineligible(self.definition, "ENTITY_NOT_FOUND")
        service_request = db.session.get(ServiceRequest, item.request_id)
        if service_request is None or service_request.tenant_id != tenant_id:
            return _ineligible(self.definition, "PARENT_ENTITY_NOT_FOUND")
        retention_until = _retention_until(
            tenant_id, self.definition.retention_data_type, service_request.created_at
        )
        if retention_until and retention_until < datetime.now(UTC).date():
            return _ineligible(
                self.definition, "RETENTION_EXPIRED", retention_until
            )
        if service_request.status == RequestStatus.CANCELADA:
            return _ineligible(
                self.definition, "PARENT_ENTITY_CANCELLED", retention_until
            )
        accepted = {
            DocumentOcrReviewStatus.ACEITO,
            DocumentOcrReviewStatus.EDITADO,
        }
        if (
            item.status != DocumentOcrStatus.CONCLUIDO
            or item.review_status not in accepted
            or not (item.reviewed_text or "").strip()
        ):
            return _ineligible(self.definition, "CONTENT_NOT_REVIEWED", retention_until)
        attachment = item.attachment
        return Projection(
            True,
            None,
            (
                f"OCR revisado de "
                f"{attachment.original_name if attachment else service_request.protocol}"
            ),
            "MEMORIA_OCR_REVISADO",
            self.definition.purpose,
            self.definition.default_legal_basis,
            self.definition.access_level,
            retention_until,
            _render_reviewed_content(
                service_request,
                attachment.original_name if attachment else None,
                item.language,
                item.review_status.value,
                item.reviewed_text,
                item.reviewed_at,
            ),
        )

    def created_by(self, tenant_id: uuid.UUID, entity_id: uuid.UUID) -> uuid.UUID:
        item = db.session.get(DocumentOcr, entity_id)
        if item is None or item.tenant_id != tenant_id:
            raise ValueError("Entidade de memória operacional não encontrada.")
        return item.reviewed_by_id or item.requested_by_id

    def entity_ids(self, tenant_id: uuid.UUID):
        return db.session.scalars(
            select(DocumentOcr.id).where(DocumentOcr.tenant_id == tenant_id)
        )


class AudioTranscriptionProjector:
    definition = ProjectorDefinition(
        module="SOLICITACOES",
        entity_type=AUDIO_TRANSCRIPTION_ENTITY,
        version="1.0.0",
        owner="Módulo de Solicitações",
        supported_actions=frozenset(ProjectorAction),
        field_allowlist=frozenset(
            {
                "request.protocol",
                "request.title",
                "attachment.original_name",
                "language",
                "review_status",
                "reviewed_transcript",
                "reviewed_at",
            }
        ),
        purpose="EVIDENCIA_DE_AUDIO_REVISADA_DE_ATENDIMENTO",
        default_legal_basis="EXERCICIO_REGULAR_DE_DIREITOS",
        access_level=RagDocumentAccess.RESTRITO,
        retention_data_type="SOLICITACAO",
        quarantine_policy="REQUIRE_HUMAN_REVIEW_AND_QUARANTINE_SUSPICIOUS_CONTENT",
        purge_policy="PURGE_DERIVED_CONTENT_WITH_ATTACHMENT_OR_REQUEST",
    )

    def project(self, tenant_id: uuid.UUID, entity_id: uuid.UUID) -> Projection:
        item = db.session.get(AudioTranscription, entity_id)
        if item is None or item.tenant_id != tenant_id:
            return _ineligible(self.definition, "ENTITY_NOT_FOUND")
        service_request = db.session.get(ServiceRequest, item.request_id)
        if service_request is None or service_request.tenant_id != tenant_id:
            return _ineligible(self.definition, "PARENT_ENTITY_NOT_FOUND")
        retention_until = _retention_until(
            tenant_id, self.definition.retention_data_type, service_request.created_at
        )
        if retention_until and retention_until < datetime.now(UTC).date():
            return _ineligible(
                self.definition, "RETENTION_EXPIRED", retention_until
            )
        if service_request.status == RequestStatus.CANCELADA:
            return _ineligible(
                self.definition, "PARENT_ENTITY_CANCELLED", retention_until
            )
        accepted = {
            AudioTranscriptionReviewStatus.ACEITA,
            AudioTranscriptionReviewStatus.EDITADA,
        }
        if (
            item.status != AudioTranscriptionStatus.CONCLUIDA
            or item.review_status not in accepted
            or not (item.reviewed_transcript or "").strip()
        ):
            return _ineligible(self.definition, "CONTENT_NOT_REVIEWED", retention_until)
        attachment = item.attachment
        return Projection(
            True,
            None,
            (
                f"Transcrição revisada de "
                f"{attachment.original_name if attachment else service_request.protocol}"
            ),
            "MEMORIA_TRANSCRICAO_REVISADA",
            self.definition.purpose,
            self.definition.default_legal_basis,
            self.definition.access_level,
            retention_until,
            _render_reviewed_content(
                service_request,
                attachment.original_name if attachment else None,
                item.language,
                item.review_status.value,
                item.reviewed_transcript,
                item.reviewed_at,
            ),
        )

    def created_by(self, tenant_id: uuid.UUID, entity_id: uuid.UUID) -> uuid.UUID:
        item = db.session.get(AudioTranscription, entity_id)
        if item is None or item.tenant_id != tenant_id:
            raise ValueError("Entidade de memória operacional não encontrada.")
        return item.reviewed_by_id or item.requested_by_id

    def entity_ids(self, tenant_id: uuid.UUID):
        return db.session.scalars(
            select(AudioTranscription.id).where(
                AudioTranscription.tenant_id == tenant_id
            )
        )


class AgendaEventProjector:
    definition = ProjectorDefinition(
        module="AGENDA",
        entity_type=AGENDA_EVENT_ENTITY,
        version="1.0.0",
        owner="Módulo de Agenda",
        supported_actions=frozenset(ProjectorAction),
        field_allowlist=frozenset(
            {
                "event_type",
                "title",
                "description",
                "starts_at",
                "ends_at",
                "minutes",
                "pending_items",
            }
        ),
        purpose="MEMORIA_DE_COMPROMISSOS_E_VISITAS_REALIZADOS",
        default_legal_basis="EXECUCAO_DE_POLITICA_PUBLICA",
        access_level=RagDocumentAccess.INTERNO,
        retention_data_type="AGENDA",
        quarantine_policy="REQUIRE_COMPLETED_MINUTES_AND_SANITIZE_PII",
        purge_policy="PURGE_DERIVED_CONTENT_ON_EVENT_DELETION",
    )

    def project(self, tenant_id: uuid.UUID, entity_id: uuid.UUID) -> Projection:
        item = db.session.get(AgendaEvent, entity_id)
        if item is None or item.tenant_id != tenant_id:
            return _ineligible(self.definition, "ENTITY_NOT_FOUND")
        retention_until = _retention_until(
            tenant_id, self.definition.retention_data_type, item.created_at
        )
        if retention_until and retention_until < datetime.now(UTC).date():
            return _ineligible(
                self.definition, "RETENTION_EXPIRED", retention_until
            )
        if item.status != AgendaEventStatus.REALIZADO or not (item.minutes or "").strip():
            return _ineligible(self.definition, "MINUTES_NOT_APPROVED", retention_until)
        return Projection(
            True,
            None,
            f"Registro de agenda: {item.title}",
            "MEMORIA_ATA_AGENDA",
            self.definition.purpose,
            self.definition.default_legal_basis,
            self.definition.access_level,
            retention_until,
            _render_agenda_event(item),
        )

    def created_by(self, tenant_id: uuid.UUID, entity_id: uuid.UUID) -> uuid.UUID:
        item = db.session.get(AgendaEvent, entity_id)
        if item is None or item.tenant_id != tenant_id:
            raise ValueError("Entidade de memória operacional não encontrada.")
        return item.created_by_id

    def entity_ids(self, tenant_id: uuid.UUID):
        return db.session.scalars(
            select(AgendaEvent.id).where(AgendaEvent.tenant_id == tenant_id)
        )


class OversightActionProjector:
    definition = ProjectorDefinition(
        module="FISCALIZACAO",
        entity_type=OVERSIGHT_ACTION_ENTITY,
        version="1.0.0",
        owner="Módulo de Fiscalização",
        supported_actions=frozenset(ProjectorAction),
        field_allowlist=frozenset(
            {
                "title",
                "description",
                "occurred_at",
                "agency.name",
                "findings",
                "report",
                "follow_up_actions",
            }
        ),
        purpose="MEMORIA_DE_FISCALIZACAO_E_CONTROLE",
        default_legal_basis="EXERCICIO_DA_FUNCAO_FISCALIZADORA",
        access_level=RagDocumentAccess.INTERNO,
        retention_data_type="FISCALIZACAO",
        quarantine_policy="REQUIRE_COMPLETED_REPORT_AND_SANITIZE_PII",
        purge_policy="PURGE_DERIVED_CONTENT_ON_ACTION_DELETION",
    )

    def project(self, tenant_id: uuid.UUID, entity_id: uuid.UUID) -> Projection:
        item = db.session.get(OversightAction, entity_id)
        if item is None or item.tenant_id != tenant_id:
            return _ineligible(self.definition, "ENTITY_NOT_FOUND")
        retention_until = _retention_until(
            tenant_id, self.definition.retention_data_type, item.created_at
        )
        if retention_until and retention_until < datetime.now(UTC).date():
            return _ineligible(
                self.definition, "RETENTION_EXPIRED", retention_until
            )
        if item.status != OversightActionStatus.CONCLUIDA or not (item.report or "").strip():
            return _ineligible(self.definition, "REPORT_NOT_APPROVED", retention_until)
        agency = db.session.get(ExternalAgency, item.agency_id) if item.agency_id else None
        agency_name = (
            agency.name
            if agency is not None and agency.tenant_id == tenant_id
            else None
        )
        return Projection(
            True,
            None,
            f"Relatório de fiscalização: {item.title}",
            "MEMORIA_RELATORIO_FISCALIZACAO",
            self.definition.purpose,
            self.definition.default_legal_basis,
            self.definition.access_level,
            retention_until,
            _render_oversight_action(item, agency_name),
        )

    def created_by(self, tenant_id: uuid.UUID, entity_id: uuid.UUID) -> uuid.UUID:
        item = db.session.get(OversightAction, entity_id)
        if item is None or item.tenant_id != tenant_id:
            raise ValueError("Entidade de memória operacional não encontrada.")
        return item.created_by_id

    def entity_ids(self, tenant_id: uuid.UUID):
        return db.session.scalars(
            select(OversightAction.id).where(OversightAction.tenant_id == tenant_id)
        )


class ThematicMemoryProjector:
    definition = ProjectorDefinition(
        module="ANALITICA",
        entity_type=THEMATIC_MEMORY_ENTITY,
        version="1.0.0",
        owner="Núcleo de Inteligência do Gabinete",
        supported_actions=frozenset(ProjectorAction),
        field_allowlist=frozenset(
            {
                "theme",
                "territory",
                "period_start",
                "period_end",
                "request_count",
                "resolved_count",
                "high_priority_count",
                "summary",
            }
        ),
        purpose="PLANEJAMENTO_TEMATICO_AGREGADO",
        default_legal_basis="EXECUCAO_DE_POLITICA_PUBLICA",
        access_level=RagDocumentAccess.INTERNO,
        retention_data_type="MEMORIA_TEMATICA",
        quarantine_policy="AGGREGATED_CONTENT_ONLY_AND_MINIMUM_GROUP_SIZE",
        purge_policy="PURGE_DERIVED_CONTENT_ON_AGGREGATE_REBUILD",
    )

    def project(self, tenant_id: uuid.UUID, entity_id: uuid.UUID) -> Projection:
        item = db.session.get(RagThematicMemory, entity_id)
        if item is None or item.tenant_id != tenant_id:
            return _ineligible(self.definition, "ENTITY_NOT_FOUND")
        retention_until = _retention_until(
            tenant_id, self.definition.retention_data_type, item.generated_at
        )
        if retention_until and retention_until < datetime.now(UTC).date():
            return _ineligible(
                self.definition, "RETENTION_EXPIRED", retention_until
            )
        if item.request_count < _thematic_min_group_size():
            return _ineligible(
                self.definition, "INSUFFICIENT_AGGREGATION", retention_until
            )
        return Projection(
            True,
            None,
            f"Memória temática: {item.theme} — {item.territory or 'todos os territórios'}",
            "MEMORIA_TEMATICA_AGREGADA",
            self.definition.purpose,
            self.definition.default_legal_basis,
            self.definition.access_level,
            retention_until,
            _render_thematic_memory(item),
        )

    def created_by(self, tenant_id: uuid.UUID, entity_id: uuid.UUID) -> uuid.UUID:
        item = db.session.get(RagThematicMemory, entity_id)
        if item is None or item.tenant_id != tenant_id:
            raise ValueError("Entidade de memória operacional não encontrada.")
        return item.generated_by_id

    def entity_ids(self, tenant_id: uuid.UUID):
        return db.session.scalars(
            select(RagThematicMemory.id).where(
                RagThematicMemory.tenant_id == tenant_id
            )
        )


class LegislativeDraftProjector:
    definition = ProjectorDefinition(
        module="LEGISLATIVO",
        entity_type=LEGISLATIVE_DRAFT_ENTITY,
        version="1.0.0",
        owner="Módulo Legislativo",
        supported_actions=frozenset(
            {
                ProjectorAction.CREATE,
                ProjectorAction.UPDATE,
                ProjectorAction.DELETE,
                ProjectorAction.ANONYMIZE,
                ProjectorAction.RETENTION_EXPIRED,
                ProjectorAction.RECONCILE,
            }
        ),
        field_allowlist=frozenset(
            {
                "document_type",
                "title",
                "content",
                "justification",
                "legal_basis",
                "status",
                "protocol_number",
                "generation_status",
            }
        ),
        purpose="MEMORIA_E_PRODUCAO_LEGISLATIVA",
        default_legal_basis="EXERCICIO_DA_FUNCAO_LEGISLATIVA",
        access_level=RagDocumentAccess.INTERNO,
        retention_data_type="DOCUMENTO_LEGISLATIVO",
        quarantine_policy="REQUIRE_APPROVED_CONTENT_AND_SANITIZE_INSTRUCTIONS",
        purge_policy="PURGE_DERIVED_CONTENT_ON_SOURCE_DELETION",
    )

    def project(self, tenant_id: uuid.UUID, entity_id: uuid.UUID) -> Projection:
        item = db.session.get(LegislativeDraft, entity_id)
        if item is None or item.tenant_id != tenant_id:
            return _ineligible(self.definition, "ENTITY_NOT_FOUND")
        retention_until = _retention_until(
            tenant_id, self.definition.retention_data_type, item.created_at
        )
        if retention_until and retention_until < datetime.now(UTC).date():
            return _ineligible(
                self.definition, "RETENTION_EXPIRED", retention_until
            )
        if (
            item.generation_status != LegislativeGenerationStatus.CONCLUIDA
            or not (item.content or "").strip()
        ):
            return _ineligible(
                self.definition, "CONTENT_NOT_APPROVED", retention_until
            )
        return Projection(
            True,
            None,
            item.title,
            f"MEMORIA_{item.document_type.value}",
            self.definition.purpose,
            self.definition.default_legal_basis,
            self.definition.access_level,
            retention_until,
            _render_draft(item),
        )

    def created_by(
        self, tenant_id: uuid.UUID, entity_id: uuid.UUID
    ) -> uuid.UUID:
        item = db.session.get(LegislativeDraft, entity_id)
        if item is None or item.tenant_id != tenant_id:
            raise ValueError("Entidade de memória operacional não encontrada.")
        return item.created_by_id

    def entity_ids(self, tenant_id: uuid.UUID):
        return db.session.scalars(
            select(LegislativeDraft.id).where(LegislativeDraft.tenant_id == tenant_id)
        )


projector_registry = ProjectorRegistry()
projector_registry.register(ServiceRequestProjector())
projector_registry.register(RequestForwardingProjector())
projector_registry.register(LegislativeDraftProjector())
projector_registry.register(LegislativeTramitationProjector())
projector_registry.register(DocumentOcrProjector())
projector_registry.register(AudioTranscriptionProjector())
projector_registry.register(AgendaEventProjector())
projector_registry.register(OversightActionProjector())
projector_registry.register(ThematicMemoryProjector())


def register_operational_memory_events() -> None:
    global _REGISTERED
    if _REGISTERED:
        return
    event.listen(Session, "before_flush", _collect_changed_entities)
    event.listen(Session, "after_flush_postexec", _enqueue_changed_entities)
    _REGISTERED = True


def enqueue_operational_memory(
    tenant_id: uuid.UUID,
    entity_type: str,
    entity_id: uuid.UUID,
    *,
    action: ProjectorAction = ProjectorAction.RECONCILE,
    revision: int | None = None,
) -> None:
    db.session.add(
        _operational_memory_event(
            tenant_id,
            entity_type,
            entity_id,
            action=action,
            revision=revision,
        )
    )


def execute_operational_memory_sync(
    tenant_id: uuid.UUID,
    entity_type: str,
    entity_id: uuid.UUID,
    *,
    action: ProjectorAction = ProjectorAction.RECONCILE,
    revision: int = 1,
    source_module: str | None = None,
) -> None:
    action = _projector_action(action)
    projector = projector_registry.require(entity_type, action)
    module = projector.definition.module
    if source_module is not None and source_module != module:
        raise ValueError(
            f"Módulo {source_module} não corresponde ao projetor {entity_type}."
        )
    if revision < 1:
        raise ValueError("A revisão do evento deve ser maior ou igual a 1.")
    source = db.session.execute(
        select(RagKnowledgeSource)
        .where(
            RagKnowledgeSource.tenant_id == tenant_id,
            RagKnowledgeSource.source_module == module,
            RagKnowledgeSource.entity_type == entity_type,
            RagKnowledgeSource.entity_id == entity_id,
        )
        .with_for_update()
    ).scalar_one_or_none()
    if source is not None and revision <= source.source_revision:
        return
    if (
        source is not None
        and source.status == RagKnowledgeSourceStatus.EXCLUIDA
        and action != ProjectorAction.CREATE
    ):
        source.source_revision = revision
        return

    if action in {
        ProjectorAction.DELETE,
        ProjectorAction.ANONYMIZE,
        ProjectorAction.RETENTION_EXPIRED,
    }:
        if source is None:
            projection = _ineligible(
                projector.definition,
                _destructive_reason(action),
            )
            source = _create_operational_source(
                tenant_id,
                projector,
                entity_id,
                projection,
                revision,
            )
        _purge_operational_source(source, action, revision)
        return

    projection = projector_registry.project(tenant_id, entity_type, entity_id)
    if source is None:
        source = _create_operational_source(
            tenant_id,
            projector,
            entity_id,
            projection,
            revision,
        )

    source.projector_version = projector.definition.version
    source.source_revision = revision
    source.purpose = projection.purpose
    source.legal_basis = projection.legal_basis
    source.access_level = projection.access_level
    source.retention_until = projection.retention_until
    source.last_projected_at = datetime.now(UTC)

    if not projection.eligible:
        source.status = (
            RagKnowledgeSourceStatus.EXPIRADA
            if projection.reason == "RETENTION_EXPIRED"
            else RagKnowledgeSourceStatus.INELEGIVEL
        )
        source.eligibility_reason = projection.reason
        source.error_code = None
        source.error_message = None
        source.sync_attempts = 0
        if source.document_id:
            document = db.session.get(RagDocument, source.document_id)
            if document is not None and document.tenant_id == tenant_id:
                document.active = False
        _audit_decision(
            source,
            "rag_operational_memory.ineligible",
            event_action=action,
        )
        return

    if has_prompt_injection(projection.content):
        source.status = RagKnowledgeSourceStatus.QUARENTENA
        source.eligibility_reason = "PROMPT_INJECTION_DETECTED"
        source.error_code = "CONTENT_SECURITY_REVIEW_REQUIRED"
        source.error_message = None
        source.quarantined_at = datetime.now(UTC)
        _audit_decision(
            source,
            "rag_operational_memory.quarantined",
            event_action=action,
        )
        return

    content_hash = hashlib.sha256(projection.content.encode("utf-8")).hexdigest()
    if (
        source.status
        in {RagKnowledgeSourceStatus.ATIVA, RagKnowledgeSourceStatus.PENDENTE}
        and source.content_hash == content_hash
        and source.document_id is not None
    ):
        return

    document = (
        db.session.get(RagDocument, source.document_id) if source.document_id else None
    )
    actor_id = projector.created_by(tenant_id, entity_id)
    if document is None:
        document = RagDocument(
            tenant_id=tenant_id,
            title=_unique_title(projection.title, entity_id),
            document_type=projection.document_type,
            access_level=projection.access_level,
            created_by_id=actor_id,
        )
        db.session.add(document)
        db.session.flush()
        source.document_id = document.id
    else:
        document.title = _unique_title(projection.title, entity_id)
        document.document_type = projection.document_type
        document.access_level = projection.access_level
        document.active = True

    version_number = source.source_version + 1
    version_id = uuid.uuid4()
    stored = store_generated_rag_text(
        tenant_id, document.id, version_id, projection.content
    )
    version = RagDocumentVersion(
        id=version_id,
        tenant_id=tenant_id,
        document_id=document.id,
        version_number=version_number,
        version_label=f"operacional-{version_number}",
        lifecycle_status=RagDocumentLifecycle.RASCUNHO,
        ingestion_status=RagIngestionStatus.PENDENTE,
        created_by_id=actor_id,
        **stored,
    )
    db.session.add(version)
    db.session.flush()
    source.status = RagKnowledgeSourceStatus.PENDENTE
    source.eligibility_reason = None
    source.error_code = None
    source.error_message = None
    source.sync_attempts = 0
    source.quarantined_at = None
    source.deleted_at = None
    source.purge_completed_at = None
    source.tombstone_hash = None
    source.content_hash = content_hash
    source.source_version = version_number
    source.latest_version_id = version.id
    enqueue_ingestion(version)
    _audit_decision(
        source,
        "rag_operational_memory.pending",
        version.id,
        event_action=action,
    )


def fail_operational_memory_sync(
    tenant_id: uuid.UUID,
    entity_type: str,
    entity_id: uuid.UUID,
    *,
    action: ProjectorAction,
    revision: int,
    error_message: str,
    attempts: int,
) -> bool:
    try:
        projector = projector_registry.require(entity_type, action)
    except ValueError:
        return False
    source = db.session.execute(
        select(RagKnowledgeSource)
        .where(
            RagKnowledgeSource.tenant_id == tenant_id,
            RagKnowledgeSource.source_module == projector.definition.module,
            RagKnowledgeSource.entity_type == entity_type,
            RagKnowledgeSource.entity_id == entity_id,
        )
        .with_for_update()
    ).scalar_one_or_none()
    if source is None:
        source = _create_operational_source(
            tenant_id,
            projector,
            entity_id,
            _ineligible(projector.definition, "SYNC_FAILED"),
            revision,
        )
    source.status = RagKnowledgeSourceStatus.ERRO
    source.eligibility_reason = "SYNC_FAILED"
    source.error_code = "OPERATIONAL_SYNC_EXHAUSTED"
    source.error_message = _safe_error_message(error_message)
    source.sync_attempts = max(1, attempts)
    source.source_revision = max(source.source_revision, revision)
    source.last_projected_at = datetime.now(UTC)
    _audit_decision(
        source,
        "rag_operational_memory.failed",
        event_action=action,
    )
    return True


def reprocess_operational_memory(source: RagKnowledgeSource) -> None:
    if source.status == RagKnowledgeSourceStatus.EXCLUIDA:
        raise ValueError("Fonte excluída não pode ser reprocessada sem recriar a origem.")
    source.status = RagKnowledgeSourceStatus.PENDENTE
    source.eligibility_reason = None
    source.error_code = None
    source.error_message = None
    source.sync_attempts = 0
    source.content_hash = None
    revision = time.time_ns()
    enqueue_operational_memory(
        source.tenant_id,
        source.entity_type,
        source.entity_id,
        action=ProjectorAction.RECONCILE,
        revision=revision,
    )
    _audit_decision(
        source,
        "rag_operational_memory.requeued",
        event_action=ProjectorAction.RECONCILE,
    )


def _create_operational_source(
    tenant_id: uuid.UUID,
    projector: OperationalMemoryProjector,
    entity_id: uuid.UUID,
    projection: Projection,
    revision: int,
) -> RagKnowledgeSource:
    source = RagKnowledgeSource(
        tenant_id=tenant_id,
        source_module=projector.definition.module,
        entity_type=projector.definition.entity_type,
        entity_id=entity_id,
        projector_version=projector.definition.version,
        source_revision=revision,
        purpose=projection.purpose,
        legal_basis=projection.legal_basis,
        access_level=projection.access_level,
        retention_until=projection.retention_until,
        status=RagKnowledgeSourceStatus.PENDENTE,
    )
    db.session.add(source)
    db.session.flush()
    return source


def _purge_operational_source(
    source: RagKnowledgeSource,
    action: ProjectorAction,
    revision: int,
) -> None:
    now = datetime.now(UTC)
    document = (
        db.session.get(RagDocument, source.document_id)
        if source.document_id is not None
        else None
    )
    versions = (
        list(document.versions)
        if document is not None and document.tenant_id == source.tenant_id
        else []
    )
    if document is not None and versions:
        from app.rag.learning import invalidate_learning_for_source

        invalidate_learning_for_source(
            source.tenant_id,
            document.id,
            [version.id for version in versions],
            versions[-1].created_by_id,
            "FONTE_OPERACIONAL_PURGADA",
        )
    if document is not None:
        document.active = False
        db.session.flush()

    for version in versions:
        delete_rag_object(
            version.storage_key,
            tenant_id=source.tenant_id,
            document_id=version.document_id,
            version_id=version.id,
        )

    version_ids = {str(version.id) for version in versions}
    if version_ids:
        pending_ingestions = db.session.scalars(
            select(OutboxEvent).where(
                OutboxEvent.tenant_id == source.tenant_id,
                OutboxEvent.event_type == RAG_INGESTION_EVENT,
                OutboxEvent.aggregate_id.in_(version_ids),
                OutboxEvent.published_at.is_(None),
                OutboxEvent.failed_at.is_(None),
            )
        )
        for event_item in pending_ingestions:
            event_item.published_at = now
            event_item.last_error = "Cancelado por purge da memória operacional."
            event_item.locked_at = None
            event_item.locked_by = None

    source.status = RagKnowledgeSourceStatus.EXCLUIDA
    source.eligibility_reason = _destructive_reason(action)
    source.source_revision = revision
    source.content_hash = None
    source.latest_version_id = None
    source.document_id = None
    source.error_code = None
    source.error_message = None
    source.sync_attempts = 0
    source.quarantined_at = None
    source.deleted_at = source.deleted_at or now
    source.tombstone_hash = _tombstone_hash(source)
    source.purge_completed_at = None
    db.session.flush()

    if document is not None and document.tenant_id == source.tenant_id:
        db.session.delete(document)
        db.session.flush()

    source.purge_completed_at = datetime.now(UTC)
    _audit_decision(
        source,
        "rag_operational_memory.purged",
        event_action=action,
    )


def _destructive_reason(action: ProjectorAction) -> str:
    return {
        ProjectorAction.DELETE: "ENTITY_DELETED",
        ProjectorAction.ANONYMIZE: "ENTITY_ANONYMIZED",
        ProjectorAction.RETENTION_EXPIRED: "RETENTION_EXPIRED",
    }[action]


def _tombstone_hash(source: RagKnowledgeSource) -> str:
    identity = (
        f"{source.tenant_id}:{source.source_module}:"
        f"{source.entity_type}:{source.entity_id}"
    )
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()


def _safe_error_message(error_message: str) -> str:
    return _minimize(re.sub(r"\s+", " ", str(error_message or "")).strip())[:500]


def reconcile_operational_memory(tenant_id: uuid.UUID) -> int:
    origins = [
        (projector.definition.entity_type, entity_id)
        for projector in projector_registry.all()
        for entity_id in projector.entity_ids(tenant_id)
    ]
    for entity_type, entity_id in origins:
        enqueue_operational_memory(
            tenant_id,
            entity_type,
            entity_id,
            action=ProjectorAction.RECONCILE,
        )
    return len(origins)


def enqueue_expired_operational_memory(
    tenant_id: uuid.UUID,
    *,
    as_of: date | None = None,
) -> int:
    reference_date = as_of or datetime.now(UTC).date()
    sources = list(
        db.session.scalars(
            select(RagKnowledgeSource)
            .where(
                RagKnowledgeSource.tenant_id == tenant_id,
                RagKnowledgeSource.status == RagKnowledgeSourceStatus.ATIVA,
                RagKnowledgeSource.retention_until.is_not(None),
                RagKnowledgeSource.retention_until < reference_date,
            )
            .with_for_update(skip_locked=True)
        )
    )
    for source in sources:
        enqueue_operational_memory(
            tenant_id,
            source.entity_type,
            source.entity_id,
            action=ProjectorAction.RETENTION_EXPIRED,
        )
    return len(sources)


def _collect_changed_entities(session: Session, _flush_context, _instances) -> None:
    if not _enabled():
        return
    pending = session.info.setdefault("operational_memory_pending", [])
    supported = (
        ServiceRequest
        | RequestInteraction
        | RequestForwarding
        | LegislativeDraft
        | LegislativeDraftVersion
        | LegislativeTramitation
        | DocumentOcr
        | AudioTranscription
        | AgendaEvent
        | OversightAction
        | RagThematicMemory
    )
    for item in session.new:
        if isinstance(item, supported):
            pending.append((item, ProjectorAction.CREATE))
    for item in session.dirty:
        if isinstance(item, ServiceRequest):
            action = (
                ProjectorAction.CANCEL
                if inspect(item).attrs.status.history.has_changes()
                and item.status == RequestStatus.CANCELADA
                else ProjectorAction.UPDATE
            )
            pending.append((item, action))
        elif isinstance(
            item,
            RequestInteraction
            | RequestForwarding
            | LegislativeDraft
            | LegislativeDraftVersion
            | LegislativeTramitation
            | DocumentOcr
            | AudioTranscription
            | RagThematicMemory,
        ):
            pending.append((item, ProjectorAction.UPDATE))
        elif isinstance(item, AgendaEvent):
            action = (
                ProjectorAction.CANCEL
                if inspect(item).attrs.status.history.has_changes()
                and item.status == AgendaEventStatus.CANCELADO
                else ProjectorAction.UPDATE
            )
            pending.append((item, action))
        elif isinstance(item, OversightAction):
            action = (
                ProjectorAction.CANCEL
                if inspect(item).attrs.status.history.has_changes()
                and item.status == OversightActionStatus.CANCELADA
                else ProjectorAction.UPDATE
            )
            pending.append((item, action))
        elif isinstance(item, ExternalAgency) and inspect(
            item
        ).attrs.name.history.has_changes():
            pending.append((item, ProjectorAction.UPDATE))
        elif (
            isinstance(item, Citizen)
            and inspect(item).attrs.anonymized_at.history.has_changes()
            and item.anonymized_at is not None
        ):
            pending.append((item, ProjectorAction.ANONYMIZE))
    for item in session.deleted:
        if isinstance(item, supported):
            pending.append((item, ProjectorAction.DELETE))


def _enqueue_changed_entities(session: Session, _flush_context) -> None:
    pending = session.info.pop("operational_memory_pending", [])
    origins: dict[
        tuple[uuid.UUID, str, uuid.UUID], ProjectorAction
    ] = {}
    for item, action in pending:
        if isinstance(item, ServiceRequest):
            _remember_origin(
                origins,
                item.tenant_id,
                SERVICE_REQUEST_ENTITY,
                item.id,
                action,
            )
            dependent_action = (
                action
                if action
                in {
                    ProjectorAction.CANCEL,
                    ProjectorAction.DELETE,
                    ProjectorAction.ANONYMIZE,
                }
                else ProjectorAction.UPDATE
            )
            for forwarding in item.forwardings:
                _remember_origin(
                    origins,
                    forwarding.tenant_id,
                    REQUEST_FORWARDING_ENTITY,
                    forwarding.id,
                    dependent_action,
                )
            for model, entity_type in (
                (DocumentOcr, DOCUMENT_OCR_ENTITY),
                (AudioTranscription, AUDIO_TRANSCRIPTION_ENTITY),
            ):
                entity_ids = session.scalars(
                    select(model.id).where(
                        model.tenant_id == item.tenant_id,
                        model.request_id == item.id,
                    )
                )
                for entity_id in entity_ids:
                    _remember_origin(
                        origins,
                        item.tenant_id,
                        entity_type,
                        entity_id,
                        dependent_action,
                    )
        elif isinstance(item, RagThematicMemory):
            _remember_origin(
                origins,
                item.tenant_id,
                THEMATIC_MEMORY_ENTITY,
                item.id,
                action,
            )
        elif isinstance(item, RequestInteraction):
            _remember_origin(
                origins,
                item.tenant_id,
                SERVICE_REQUEST_ENTITY,
                item.request_id,
                ProjectorAction.UPDATE,
            )
        elif isinstance(item, RequestForwarding):
            _remember_origin(
                origins,
                item.tenant_id,
                REQUEST_FORWARDING_ENTITY,
                item.id,
                action,
            )
        elif isinstance(item, DocumentOcr):
            _remember_origin(
                origins,
                item.tenant_id,
                DOCUMENT_OCR_ENTITY,
                item.id,
                action,
            )
        elif isinstance(item, AudioTranscription):
            _remember_origin(
                origins,
                item.tenant_id,
                AUDIO_TRANSCRIPTION_ENTITY,
                item.id,
                action,
            )
        elif isinstance(item, LegislativeDraft):
            _remember_origin(
                origins,
                item.tenant_id,
                LEGISLATIVE_DRAFT_ENTITY,
                item.id,
                action,
            )
            dependent_action = (
                action
                if action
                in {
                    ProjectorAction.DELETE,
                    ProjectorAction.ANONYMIZE,
                }
                else ProjectorAction.UPDATE
            )
            tramitation_ids = session.scalars(
                select(LegislativeTramitation.id).where(
                    LegislativeTramitation.tenant_id == item.tenant_id,
                    LegislativeTramitation.draft_id == item.id,
                )
            )
            for tramitation_id in tramitation_ids:
                _remember_origin(
                    origins,
                    item.tenant_id,
                    LEGISLATIVE_TRAMITATION_ENTITY,
                    tramitation_id,
                    dependent_action,
                )
        elif isinstance(item, LegislativeDraftVersion):
            _remember_origin(
                origins,
                item.tenant_id,
                LEGISLATIVE_DRAFT_ENTITY,
                item.draft_id,
                ProjectorAction.UPDATE,
            )
        elif isinstance(item, LegislativeTramitation):
            _remember_origin(
                origins,
                item.tenant_id,
                LEGISLATIVE_TRAMITATION_ENTITY,
                item.id,
                action,
            )
        elif isinstance(item, AgendaEvent):
            _remember_origin(
                origins,
                item.tenant_id,
                AGENDA_EVENT_ENTITY,
                item.id,
                action,
            )
        elif isinstance(item, OversightAction):
            _remember_origin(
                origins,
                item.tenant_id,
                OVERSIGHT_ACTION_ENTITY,
                item.id,
                action,
            )
        elif isinstance(item, Citizen):
            request_ids = session.scalars(
                select(ServiceRequest.id).where(
                    ServiceRequest.tenant_id == item.tenant_id,
                    ServiceRequest.citizen_id == item.id,
                )
            )
            for request_id in request_ids:
                _remember_origin(
                    origins,
                    item.tenant_id,
                    SERVICE_REQUEST_ENTITY,
                    request_id,
                    ProjectorAction.ANONYMIZE,
                )
                forwarding_ids = session.scalars(
                    select(RequestForwarding.id).where(
                        RequestForwarding.tenant_id == item.tenant_id,
                        RequestForwarding.request_id == request_id,
                    )
                )
                for forwarding_id in forwarding_ids:
                    _remember_origin(
                        origins,
                        item.tenant_id,
                        REQUEST_FORWARDING_ENTITY,
                        forwarding_id,
                        ProjectorAction.ANONYMIZE,
                    )
                for model, entity_type in (
                    (DocumentOcr, DOCUMENT_OCR_ENTITY),
                    (AudioTranscription, AUDIO_TRANSCRIPTION_ENTITY),
                ):
                    entity_ids = session.scalars(
                        select(model.id).where(
                            model.tenant_id == item.tenant_id,
                            model.request_id == request_id,
                        )
                    )
                    for entity_id in entity_ids:
                        _remember_origin(
                            origins,
                            item.tenant_id,
                            entity_type,
                            entity_id,
                            ProjectorAction.ANONYMIZE,
                        )
            agenda_ids = session.scalars(
                select(AgendaEvent.id).where(
                    AgendaEvent.tenant_id == item.tenant_id,
                    AgendaEvent.citizen_id == item.id,
                )
            )
            for agenda_id in agenda_ids:
                _remember_origin(
                    origins,
                    item.tenant_id,
                    AGENDA_EVENT_ENTITY,
                    agenda_id,
                    ProjectorAction.ANONYMIZE,
                )
        elif isinstance(item, ExternalAgency):
            forwarding_ids = session.scalars(
                select(RequestForwarding.id).where(
                    RequestForwarding.tenant_id == item.tenant_id,
                    RequestForwarding.agency_id == item.id,
                )
            )
            for forwarding_id in forwarding_ids:
                _remember_origin(
                    origins,
                    item.tenant_id,
                    REQUEST_FORWARDING_ENTITY,
                    forwarding_id,
                    ProjectorAction.UPDATE,
                )
            oversight_ids = session.scalars(
                select(OversightAction.id).where(
                    OversightAction.tenant_id == item.tenant_id,
                    OversightAction.agency_id == item.id,
                )
            )
            for oversight_id in oversight_ids:
                _remember_origin(
                    origins,
                    item.tenant_id,
                    OVERSIGHT_ACTION_ENTITY,
                    oversight_id,
                    ProjectorAction.UPDATE,
                )
    for (tenant_id, entity_type, entity_id), action in origins.items():
        if not tenant_id or not entity_id:
            continue
        session.add(
            _operational_memory_event(
                tenant_id,
                entity_type,
                entity_id,
                action=action,
            )
        )


def _operational_memory_event(
    tenant_id: uuid.UUID,
    entity_type: str,
    entity_id: uuid.UUID,
    *,
    action: ProjectorAction,
    revision: int | None = None,
) -> OutboxEvent:
    action = _projector_action(action)
    projector = projector_registry.require(entity_type, action)
    event_revision = revision if revision is not None else time.time_ns()
    if event_revision < 1:
        raise ValueError("A revisão do evento deve ser maior ou igual a 1.")
    if action in {
        ProjectorAction.DELETE,
        ProjectorAction.ANONYMIZE,
        ProjectorAction.RETENTION_EXPIRED,
    }:
        _unpublish_operational_source(
            tenant_id,
            projector.definition.module,
            entity_type,
            entity_id,
            action,
        )
    return OutboxEvent(
        tenant_id=tenant_id,
        event_type=OPERATIONAL_MEMORY_EVENT,
        aggregate_type=entity_type,
        aggregate_id=str(entity_id),
        payload={
            "schemaVersion": OPERATIONAL_MEMORY_EVENT_SCHEMA_VERSION,
            "sourceModule": projector.definition.module,
            "entityType": entity_type,
            "entityId": str(entity_id),
            "action": action.value,
            "revision": event_revision,
        },
    )


def _unpublish_operational_source(
    tenant_id: uuid.UUID,
    source_module: str,
    entity_type: str,
    entity_id: uuid.UUID,
    action: ProjectorAction,
) -> None:
    source = db.session.execute(
        select(RagKnowledgeSource)
        .where(
            RagKnowledgeSource.tenant_id == tenant_id,
            RagKnowledgeSource.source_module == source_module,
            RagKnowledgeSource.entity_type == entity_type,
            RagKnowledgeSource.entity_id == entity_id,
        )
        .with_for_update()
    ).scalar_one_or_none()
    if source is None or source.status == RagKnowledgeSourceStatus.EXCLUIDA:
        return
    source.status = (
        RagKnowledgeSourceStatus.EXPIRADA
        if action == ProjectorAction.RETENTION_EXPIRED
        else RagKnowledgeSourceStatus.INELEGIVEL
    )
    source.eligibility_reason = _destructive_reason(action)
    if source.document_id is not None:
        document = db.session.get(RagDocument, source.document_id)
        if document is not None and document.tenant_id == tenant_id:
            document.active = False


def _projector_action(action: ProjectorAction | str) -> ProjectorAction:
    if isinstance(action, ProjectorAction):
        return action
    try:
        return ProjectorAction(str(action).upper())
    except ValueError as error:
        raise ValueError(f"Ação de memória operacional inválida: {action}.") from error


def _remember_origin(
    origins: dict[tuple[uuid.UUID, str, uuid.UUID], ProjectorAction],
    tenant_id: uuid.UUID,
    entity_type: str,
    entity_id: uuid.UUID,
    action: ProjectorAction,
) -> None:
    key = (tenant_id, entity_type, entity_id)
    priority = {
        ProjectorAction.UPDATE: 1,
        ProjectorAction.RECONCILE: 1,
        ProjectorAction.CREATE: 2,
        ProjectorAction.CANCEL: 3,
        ProjectorAction.ANONYMIZE: 4,
        ProjectorAction.RETENTION_EXPIRED: 5,
        ProjectorAction.DELETE: 6,
    }
    current = origins.get(key)
    if current is None or priority[action] > priority[current]:
        origins[key] = action


def _enabled() -> bool:
    return bool(
        has_app_context()
        and current_app.config.get("RAG_OPERATIONAL_MEMORY_ENABLED", True)
    )


def _ineligible(
    definition: ProjectorDefinition,
    reason: str,
    retention_until: date | None = None,
) -> Projection:
    return Projection(
        False,
        reason,
        f"Memória {definition.entity_type}",
        "MEMORIA_OPERACIONAL",
        definition.purpose,
        "NAO_APLICAVEL",
        definition.access_level,
        retention_until,
        "",
    )


def _render_request(item: ServiceRequest) -> str:
    values = [
        f"Protocolo: {item.protocol}",
        f"Título: {_minimize(item.title)}",
        f"Descrição: {_minimize(item.description)}",
        f"Status: {item.status.value}",
        f"Prioridade: {item.priority.value}",
        f"Categoria: {_minimize(item.category)}",
        f"Subcategoria: {_minimize(item.subcategory)}",
        f"Tema: {_minimize(item.theme)}",
        f"Impacto: {_minimize(item.impact)}",
        f"Urgência: {_minimize(item.urgency)}",
        f"Motivo de encerramento: {_minimize(item.closing_reason)}",
        f"Evidência de encerramento: {_minimize(item.closing_evidence)}",
    ]
    for interaction in item.interactions:
        values.append(
            "Interação "
            f"({interaction.interaction_type}/{interaction.channel}/"
            f"{interaction.direction.value}): {_minimize(interaction.content)}"
        )
    return "\n".join(value for value in values if not value.endswith(": "))


def _render_forwarding(
    item: RequestForwarding,
    service_request: ServiceRequest,
    agency_name: str,
) -> str:
    values = [
        f"Protocolo da solicitação: {_minimize(service_request.protocol)}",
        f"Título da solicitação: {_minimize(service_request.title)}",
        f"Órgão destinatário: {_minimize(agency_name)}",
        f"Protocolo externo: {_minimize(item.external_protocol)}",
        f"Situação do encaminhamento: {item.status.value}",
        f"Observações: {_minimize(item.notes)}",
        f"Prazo: {item.due_at.isoformat() if item.due_at else ''}",
        f"Resposta oficial: {_minimize(item.response)}",
        f"Respondido em: {item.response_at.isoformat() if item.response_at else ''}",
    ]
    return "\n".join(value for value in values if not value.endswith(": "))


def _render_tramitation(
    item: LegislativeTramitation,
    draft: LegislativeDraft,
) -> str:
    values = [
        f"Tipo legislativo: {draft.document_type.value}",
        f"Título: {_minimize(draft.title)}",
        f"Protocolo legislativo: {_minimize(draft.protocol_number)}",
        f"Situação da tramitação: {item.status.value}",
        f"Etapa: {_minimize(item.stage)}",
        f"Destino: {_minimize(item.destination)}",
        f"Referência externa: {_minimize(item.external_reference)}",
        f"Observações: {_minimize(item.notes)}",
        f"Ocorrida em: {item.occurred_at.isoformat()}",
    ]
    return "\n".join(value for value in values if not value.endswith(": "))


def _render_reviewed_content(
    service_request: ServiceRequest,
    original_name: str | None,
    language: str | None,
    review_status: str,
    reviewed_text: str,
    reviewed_at: datetime | None,
) -> str:
    values = [
        f"Protocolo da solicitação: {_minimize(service_request.protocol)}",
        f"Título da solicitação: {_minimize(service_request.title)}",
        f"Arquivo: {_minimize(original_name)}",
        f"Idioma: {_minimize(language)}",
        f"Revisão humana: {review_status}",
        f"Texto revisado: {_minimize(reviewed_text)}",
        f"Revisado em: {reviewed_at.isoformat() if reviewed_at else ''}",
    ]
    return "\n".join(value for value in values if not value.endswith(": "))


def _render_agenda_event(item: AgendaEvent) -> str:
    values = [
        f"Tipo de compromisso: {item.event_type.value}",
        f"Título: {_minimize(item.title)}",
        f"Descrição: {_minimize(item.description)}",
        f"Início: {item.starts_at.isoformat()}",
        f"Fim: {item.ends_at.isoformat() if item.ends_at else ''}",
        f"Ata revisada: {_minimize(item.minutes)}",
        f"Pendências: {_minimize(_json_text(item.pending_items))}",
    ]
    return "\n".join(value for value in values if not value.endswith(": "))


def _render_oversight_action(
    item: OversightAction,
    agency_name: str | None,
) -> str:
    values = [
        f"Título: {_minimize(item.title)}",
        f"Descrição: {_minimize(item.description)}",
        f"Órgão fiscalizado: {_minimize(agency_name)}",
        f"Realizada em: {item.occurred_at.isoformat() if item.occurred_at else ''}",
        f"Achados: {_minimize(_json_text(item.findings))}",
        f"Relatório concluído: {_minimize(item.report)}",
        f"Providências: {_minimize(_json_text(item.follow_up_actions))}",
    ]
    return "\n".join(value for value in values if not value.endswith(": "))


def _render_thematic_memory(item: RagThematicMemory) -> str:
    return "\n".join(
        [
            f"Tema: {_minimize(item.theme)}",
            f"Território: {_minimize(item.territory) or 'Todos'}",
            f"Período: {item.period_start.isoformat()} a {item.period_end.isoformat()}",
            f"Total de solicitações: {item.request_count}",
            f"Solicitações resolvidas: {item.resolved_count}",
            f"Solicitações de alta prioridade: {item.high_priority_count}",
            f"Síntese agregada: {_minimize(item.summary)}",
        ]
    )


def _render_draft(item: LegislativeDraft) -> str:
    bases = "; ".join(_minimize(value) for value in (item.legal_basis or []))
    return "\n".join(
        [
            f"Tipo: {item.document_type.value}",
            f"Título: {_minimize(item.title)}",
            f"Conteúdo: {_minimize(item.content)}",
            f"Justificativa: {_minimize(item.justification)}",
            f"Fundamentação: {bases}",
            f"Situação: {item.status.value}",
            f"Protocolo legislativo: {_minimize(item.protocol_number)}",
        ]
    )


def _json_text(value) -> str:
    return json.dumps(value or [], ensure_ascii=False, sort_keys=True)


def _minimize(value) -> str:
    text = str(value or "").strip()
    patterns = (
        r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b",
        r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b",
        r"(?<!\d)(?:\+?55\s*)?(?:\(?\d{2}\)?\s*)?9?\d{4}[-\s]?\d{4}(?!\d)",
        r"\b\d{5}-?\d{3}\b",
    )
    for pattern in patterns:
        text = re.sub(pattern, _REDACTED, text, flags=re.IGNORECASE)
    return re.sub(r"[ \t]+", " ", text)


def _retention_until(
    tenant_id: uuid.UUID, data_type: str, created_at: datetime
) -> date | None:
    policy = db.session.execute(
        select(RetentionPolicy).where(
            RetentionPolicy.tenant_id == tenant_id,
            RetentionPolicy.data_type == data_type,
            RetentionPolicy.active.is_(True),
        )
    ).scalar_one_or_none()
    return (
        (created_at + timedelta(days=policy.retention_days)).date()
        if policy is not None
        else None
    )


def _thematic_min_group_size() -> int:
    return max(
        2,
        int(
            current_app.config.get("RAG_THEMATIC_MIN_GROUP_SIZE", 3)
            if has_app_context()
            else 3
        ),
    )


def _unique_title(title: str, entity_id: uuid.UUID) -> str:
    return f"[Memória] {title[:190]} ({str(entity_id)[:8]})"


def _audit_decision(
    source: RagKnowledgeSource,
    action: str,
    version_id: uuid.UUID | None = None,
    *,
    event_action: ProjectorAction | None = None,
) -> None:
    details = {
        "modulo": source.source_module,
        "entidadeTipo": source.entity_type,
        "entidadeId": str(source.entity_id),
        "versaoProjetor": source.projector_version,
        "acaoEvento": event_action.value if event_action else None,
        "revisaoOrigem": source.source_revision,
        "status": source.status.value,
        "motivo": source.eligibility_reason,
        "codigoErro": source.error_code,
        "tentativas": source.sync_attempts,
        "finalidade": source.purpose,
        "baseLegal": source.legal_basis,
        "retencaoAte": (
            source.retention_until.isoformat() if source.retention_until else None
        ),
        "documentoId": str(source.document_id) if source.document_id else None,
        "versaoId": str(version_id) if version_id else None,
        "quarentenaEm": (
            source.quarantined_at.isoformat() if source.quarantined_at else None
        ),
        "excluidaEm": source.deleted_at.isoformat() if source.deleted_at else None,
        "purgeConcluidoEm": (
            source.purge_completed_at.isoformat()
            if source.purge_completed_at
            else None
        ),
        "tombstoneHash": source.tombstone_hash,
    }
    db.session.add(
        AuditLog(
            tenant_id=source.tenant_id,
            user_id=None,
            action=action,
            entity_type="rag_knowledge_source",
            entity_id=str(source.id),
            after=details,
        )
    )
