import hashlib
import re
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from flask import current_app, has_app_context
from sqlalchemy import event, select
from sqlalchemy.orm import Session

from app.extensions import db
from app.models import (
    AuditLog,
    Citizen,
    LegislativeDraft,
    LegislativeDraftVersion,
    LegislativeGenerationStatus,
    OutboxEvent,
    RagDocument,
    RagDocumentAccess,
    RagDocumentLifecycle,
    RagDocumentVersion,
    RagIngestionStatus,
    RagKnowledgeSource,
    RagKnowledgeSourceStatus,
    RequestInteraction,
    RequestStatus,
    RetentionPolicy,
    ServiceRequest,
)
from app.rag.service import enqueue_ingestion
from app.rag.storage import store_generated_rag_text

OPERATIONAL_MEMORY_EVENT = "SincronizacaoMemoriaOperacional"
SERVICE_REQUEST_ENTITY = "SERVICE_REQUEST"
LEGISLATIVE_DRAFT_ENTITY = "LEGISLATIVE_DRAFT"
_REGISTERED = False
_REDACTED = "[DADO_PESSOAL_REMOVIDO]"


@dataclass(frozen=True)
class Projection:
    eligible: bool
    reason: str | None
    title: str
    document_type: str
    purpose: str
    legal_basis: str
    access_level: RagDocumentAccess
    retention_until: date | None
    content: str


def register_operational_memory_events() -> None:
    global _REGISTERED
    if _REGISTERED:
        return
    event.listen(Session, "before_flush", _collect_changed_entities)
    event.listen(Session, "after_flush_postexec", _enqueue_changed_entities)
    _REGISTERED = True


def enqueue_operational_memory(
    tenant_id: uuid.UUID, entity_type: str, entity_id: uuid.UUID
) -> None:
    db.session.add(
        OutboxEvent(
            tenant_id=tenant_id,
            event_type=OPERATIONAL_MEMORY_EVENT,
            aggregate_type=entity_type,
            aggregate_id=str(entity_id),
            payload={"entityType": entity_type, "entityId": str(entity_id)},
        )
    )


def execute_operational_memory_sync(
    tenant_id: uuid.UUID, entity_type: str, entity_id: uuid.UUID
) -> None:
    projection = _projection(tenant_id, entity_type, entity_id)
    module = _module(entity_type)
    source = db.session.execute(
        select(RagKnowledgeSource).where(
            RagKnowledgeSource.tenant_id == tenant_id,
            RagKnowledgeSource.source_module == module,
            RagKnowledgeSource.entity_type == entity_type,
            RagKnowledgeSource.entity_id == entity_id,
        )
    ).scalar_one_or_none()
    if source is None:
        source = RagKnowledgeSource(
            tenant_id=tenant_id,
            source_module=module,
            entity_type=entity_type,
            entity_id=entity_id,
            purpose=projection.purpose,
            legal_basis=projection.legal_basis,
            access_level=projection.access_level,
        )
        db.session.add(source)
        db.session.flush()

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
        if source.document_id:
            document = db.session.get(RagDocument, source.document_id)
            if document is not None and document.tenant_id == tenant_id:
                document.active = False
        _audit_decision(source, "rag_operational_memory.ineligible")
        return

    content_hash = hashlib.sha256(projection.content.encode("utf-8")).hexdigest()
    if (
        source.status == RagKnowledgeSourceStatus.ATIVA
        and source.content_hash == content_hash
        and source.document_id is not None
    ):
        return

    document = (
        db.session.get(RagDocument, source.document_id) if source.document_id else None
    )
    actor_id = _created_by(tenant_id, entity_type, entity_id)
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
    source.status = RagKnowledgeSourceStatus.ATIVA
    source.eligibility_reason = None
    source.content_hash = content_hash
    source.source_version = version_number
    source.latest_version_id = version.id
    enqueue_ingestion(version)
    _audit_decision(source, "rag_operational_memory.projected", version.id)


def reconcile_operational_memory(tenant_id: uuid.UUID) -> int:
    origins = [
        (SERVICE_REQUEST_ENTITY, item)
        for item in db.session.scalars(
            select(ServiceRequest.id).where(ServiceRequest.tenant_id == tenant_id)
        )
    ]
    origins.extend(
        (LEGISLATIVE_DRAFT_ENTITY, item)
        for item in db.session.scalars(
            select(LegislativeDraft.id).where(LegislativeDraft.tenant_id == tenant_id)
        )
    )
    for entity_type, entity_id in origins:
        enqueue_operational_memory(tenant_id, entity_type, entity_id)
    return len(origins)


def _collect_changed_entities(session: Session, _flush_context, _instances) -> None:
    if not _enabled():
        return
    pending = session.info.setdefault("operational_memory_pending", set())
    for item in set(session.new).union(session.dirty):
        if isinstance(
            item,
            ServiceRequest
            | RequestInteraction
            | LegislativeDraft
            | LegislativeDraftVersion,
        ):
            pending.add(item)


def _enqueue_changed_entities(session: Session, _flush_context) -> None:
    pending = session.info.pop("operational_memory_pending", set())
    origins = set()
    for item in pending:
        if isinstance(item, ServiceRequest):
            origins.add((item.tenant_id, SERVICE_REQUEST_ENTITY, item.id))
        elif isinstance(item, RequestInteraction):
            origins.add((item.tenant_id, SERVICE_REQUEST_ENTITY, item.request_id))
        elif isinstance(item, LegislativeDraft):
            origins.add((item.tenant_id, LEGISLATIVE_DRAFT_ENTITY, item.id))
        else:
            origins.add((item.tenant_id, LEGISLATIVE_DRAFT_ENTITY, item.draft_id))
    for tenant_id, entity_type, entity_id in origins:
        if not tenant_id or not entity_id:
            continue
        session.add(
            OutboxEvent(
                tenant_id=tenant_id,
                event_type=OPERATIONAL_MEMORY_EVENT,
                aggregate_type=entity_type,
                aggregate_id=str(entity_id),
                payload={"entityType": entity_type, "entityId": str(entity_id)},
            )
        )


def _enabled() -> bool:
    return bool(
        has_app_context()
        and current_app.config.get("RAG_OPERATIONAL_MEMORY_ENABLED", True)
    )


def _projection(
    tenant_id: uuid.UUID, entity_type: str, entity_id: uuid.UUID
) -> Projection:
    if entity_type == SERVICE_REQUEST_ENTITY:
        item = db.session.get(ServiceRequest, entity_id)
        if item is None or item.tenant_id != tenant_id:
            return _ineligible(entity_type, "ENTITY_NOT_FOUND")
        retention_until = _retention_until(
            tenant_id, "SOLICITACAO", item.created_at
        )
        if retention_until and retention_until < datetime.now(UTC).date():
            return _ineligible(entity_type, "RETENTION_EXPIRED", retention_until)
        if item.status == RequestStatus.CANCELADA:
            return _ineligible(entity_type, "ENTITY_CANCELLED", retention_until)
        citizen = db.session.get(Citizen, item.citizen_id) if item.citizen_id else None
        legal_basis = (
            citizen.legal_basis
            if citizen is not None and citizen.tenant_id == tenant_id
            else "EXERCICIO_REGULAR_DE_DIREITOS"
        )
        return Projection(
            True,
            None,
            f"Solicitação {item.protocol}: {item.title or 'sem título'}",
            "MEMORIA_SOLICITACAO",
            "ATENDIMENTO_E_PLANEJAMENTO_LEGISLATIVO",
            legal_basis,
            RagDocumentAccess.INTERNO,
            retention_until,
            _render_request(item),
        )
    if entity_type == LEGISLATIVE_DRAFT_ENTITY:
        item = db.session.get(LegislativeDraft, entity_id)
        if item is None or item.tenant_id != tenant_id:
            return _ineligible(entity_type, "ENTITY_NOT_FOUND")
        retention_until = _retention_until(
            tenant_id, "DOCUMENTO_LEGISLATIVO", item.created_at
        )
        if retention_until and retention_until < datetime.now(UTC).date():
            return _ineligible(entity_type, "RETENTION_EXPIRED", retention_until)
        if (
            item.generation_status != LegislativeGenerationStatus.CONCLUIDA
            or not (item.content or "").strip()
        ):
            return _ineligible(entity_type, "CONTENT_NOT_APPROVED", retention_until)
        return Projection(
            True,
            None,
            item.title,
            f"MEMORIA_{item.document_type.value}",
            "MEMORIA_E_PRODUCAO_LEGISLATIVA",
            "EXERCICIO_DA_FUNCAO_LEGISLATIVA",
            RagDocumentAccess.INTERNO,
            retention_until,
            _render_draft(item),
        )
    return _ineligible(entity_type, "UNSUPPORTED_ENTITY")


def _ineligible(
    entity_type: str, reason: str, retention_until: date | None = None
) -> Projection:
    return Projection(
        False,
        reason,
        f"Memória {entity_type}",
        "MEMORIA_OPERACIONAL",
        "MEMORIA_OPERACIONAL",
        "NAO_APLICAVEL",
        RagDocumentAccess.INTERNO,
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


def _created_by(
    tenant_id: uuid.UUID, entity_type: str, entity_id: uuid.UUID
) -> uuid.UUID:
    model = ServiceRequest if entity_type == SERVICE_REQUEST_ENTITY else LegislativeDraft
    item = db.session.get(model, entity_id)
    if item is None or item.tenant_id != tenant_id:
        raise ValueError("Entidade de memória operacional não encontrada.")
    return item.created_by_id


def _module(entity_type: str) -> str:
    if entity_type == SERVICE_REQUEST_ENTITY:
        return "SOLICITACOES"
    if entity_type == LEGISLATIVE_DRAFT_ENTITY:
        return "LEGISLATIVO"
    raise ValueError("Tipo de entidade operacional não suportado.")


def _unique_title(title: str, entity_id: uuid.UUID) -> str:
    return f"[Memória] {title[:190]} ({str(entity_id)[:8]})"


def _audit_decision(
    source: RagKnowledgeSource, action: str, version_id: uuid.UUID | None = None
) -> None:
    details = {
        "modulo": source.source_module,
        "entidadeTipo": source.entity_type,
        "entidadeId": str(source.entity_id),
        "status": source.status.value,
        "motivo": source.eligibility_reason,
        "finalidade": source.purpose,
        "baseLegal": source.legal_basis,
        "retencaoAte": (
            source.retention_until.isoformat() if source.retention_until else None
        ),
        "documentoId": str(source.document_id) if source.document_id else None,
        "versaoId": str(version_id) if version_id else None,
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
