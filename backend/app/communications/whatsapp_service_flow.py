import hashlib
import json
import uuid
from datetime import UTC, datetime, timedelta

from flask import current_app
from sqlalchemy import select

from app.ai.service import enqueue_triage_execution
from app.communications.identity import get_assisted_settings, normalize_channel_contact
from app.communications.whatsapp_conversations import (
    TERMINAL_STATES,
    ConversationValidationError,
    transition_conversation,
)
from app.extensions import db
from app.models import (
    Citizen,
    ConsentRecord,
    OutboxEvent,
    RequestCategory,
    RequestHistory,
    RequestPriority,
    RequestSource,
    RequestStatus,
    ServiceRequest,
    WhatsAppContact,
    WhatsAppContactOptStatus,
    WhatsAppConversation,
    WhatsAppConversationState,
    WhatsAppPrivacyRecord,
    WhatsAppRequestDraft,
)
from app.requests.service import creation_event, new_public_protocol, next_protocol

NOTICE_VERSION = "whatsapp-privacy-v1"
NOTICE_PURPOSE = "ATENDIMENTO_INSTITUCIONAL"
DEFAULT_LEGAL_BASIS = "EXECUCAO_POLITICA_PUBLICA"
PRIVACY_NOTICE_EVENT = "WhatsappPrivacyNoticeRequested"
PROTOCOL_CREATED_EVENT = "WhatsappProtocolCreated"


class WhatsAppServiceFlowError(ValueError):
    pass


def ensure_privacy_notice_requested(
    conversation: WhatsAppConversation,
    contact: WhatsAppContact,
    *,
    correlation_id: str | None,
) -> WhatsAppPrivacyRecord:
    existing = _privacy_record(conversation, "NOTICE_REQUESTED")
    if existing is not None:
        return existing
    settings = get_assisted_settings(conversation.tenant_id)
    legal_basis = (
        settings.default_legal_basis
        if settings and settings.default_legal_basis
        else DEFAULT_LEGAL_BASIS
    )
    evidence = {
        "conversationId": str(conversation.id),
        "noticeVersion": NOTICE_VERSION,
        "purpose": NOTICE_PURPOSE,
        "legalBasis": legal_basis,
        "correlationId": correlation_id,
    }
    record = WhatsAppPrivacyRecord(
        tenant_id=conversation.tenant_id,
        contact_id=contact.id,
        conversation_id=conversation.id,
        purpose=NOTICE_PURPOSE,
        legal_basis=legal_basis,
        notice_version=NOTICE_VERSION,
        action="NOTICE_REQUESTED",
        consent_required=False,
        granted=None,
        evidence_hash=_evidence_hash(evidence),
    )
    db.session.add(record)
    db.session.add(
        OutboxEvent(
            tenant_id=conversation.tenant_id,
            event_type=PRIVACY_NOTICE_EVENT,
            aggregate_type="whatsapp_conversation",
            aggregate_id=str(conversation.id),
            payload={
                "conversationId": str(conversation.id),
                "contactId": str(contact.id),
                "noticeVersion": NOTICE_VERSION,
                "purpose": NOTICE_PURPOSE,
                "legalBasis": legal_basis,
                "message": (
                    "Este canal institucional usa o GabFlow para registrar e acompanhar "
                    "seu atendimento. Podemos usar automacao como apoio, com revisao humana. "
                    "Envie PARAR a qualquer momento. Consulte o aviso completo de privacidade."
                ),
                "correlationId": correlation_id,
            },
        )
    )
    return record


def acknowledge_privacy(
    conversation: WhatsAppConversation,
    contact: WhatsAppContact,
    *,
    actor_id: uuid.UUID,
    legal_basis: str,
    consent_required: bool,
    granted: bool | None,
    provider_message_id: str | None,
) -> WhatsAppPrivacyRecord:
    _assert_active(conversation, contact)
    if conversation.state != WhatsAppConversationState.PRIVACY_NOTICE:
        existing = _privacy_record(conversation, "ACKNOWLEDGED")
        if existing is not None:
            return existing
        raise WhatsAppServiceFlowError("A conversa nao esta aguardando o aviso de privacidade.")
    legal_basis = str(legal_basis or "").strip()[:120]
    if not legal_basis:
        raise WhatsAppServiceFlowError("Informe a base legal aplicavel.")
    if consent_required and granted is not True:
        raise WhatsAppServiceFlowError("O consentimento exigido ainda nao foi concedido.")
    evidence = {
        "conversationId": str(conversation.id),
        "noticeVersion": NOTICE_VERSION,
        "legalBasis": legal_basis,
        "consentRequired": consent_required,
        "granted": granted,
        "providerMessageId": provider_message_id,
    }
    record = WhatsAppPrivacyRecord(
        tenant_id=conversation.tenant_id,
        contact_id=contact.id,
        conversation_id=conversation.id,
        purpose=NOTICE_PURPOSE,
        legal_basis=legal_basis,
        notice_version=NOTICE_VERSION,
        action="ACKNOWLEDGED",
        consent_required=consent_required,
        granted=granted if consent_required else None,
        evidence_hash=_evidence_hash(evidence),
        provider_message_id=(str(provider_message_id)[:160] if provider_message_id else None),
        recorded_by_id=actor_id,
    )
    db.session.add(record)
    transition_conversation(
        conversation,
        WhatsAppConversationState.IDENTIFICATION,
        actor_type="USER",
        actor_id=actor_id,
        origin="INBOX_PRIVACY",
        reason="Aviso de privacidade e base legal registrados.",
    )
    return record


def citizen_suggestions(contact: WhatsAppContact) -> list[Citizen]:
    expected = normalize_channel_contact(RequestSource.WHATSAPP, contact.wa_user_id)
    if expected is None:
        return []
    result = []
    citizens = db.session.scalars(
        select(Citizen).where(
            Citizen.tenant_id == contact.tenant_id,
            Citizen.anonymized_at.is_(None),
        )
    )
    for citizen in citizens:
        if any(
            isinstance(item, dict)
            and str(item.get("tipo") or "").upper() in {"WHATSAPP", "TELEFONE"}
            and normalize_channel_contact(RequestSource.WHATSAPP, item.get("valor")) == expected
            for item in (citizen.contacts or [])
        ):
            result.append(citizen)
    return result


def identify_citizen(
    conversation: WhatsAppConversation,
    contact: WhatsAppContact,
    *,
    actor_id: uuid.UUID,
    citizen_id: uuid.UUID | None = None,
    name: str | None = None,
    confirmed: bool,
    actor_type: str = "USER",
    origin: str = "INBOX_IDENTIFICATION",
) -> tuple[Citizen, bool]:
    _assert_active(conversation, contact)
    if _privacy_record(conversation, "ACKNOWLEDGED") is None:
        raise WhatsAppServiceFlowError("Registre o aviso de privacidade antes da identificacao.")
    if not confirmed:
        raise WhatsAppServiceFlowError("A identificacao precisa de confirmacao explicita.")
    if contact.citizen_id is not None:
        linked = db.session.execute(
            select(Citizen).where(
                Citizen.tenant_id == conversation.tenant_id,
                Citizen.id == contact.citizen_id,
            )
        ).scalar_one()
        if citizen_id == linked.id:
            return linked, False
        raise WhatsAppServiceFlowError("A conversa ja possui um cidadao confirmado.")
    created = False
    if citizen_id is not None:
        citizen = db.session.execute(
            select(Citizen).where(
                Citizen.tenant_id == conversation.tenant_id,
                Citizen.id == citizen_id,
                Citizen.anonymized_at.is_(None),
            )
        ).scalar_one_or_none()
        if citizen is None:
            raise WhatsAppServiceFlowError("Cidadao nao encontrado neste gabinete.")
    else:
        clean_name = " ".join(str(name or "").split())
        if len(clean_name) < 2 or len(clean_name) > 180:
            raise WhatsAppServiceFlowError("Informe o nome confirmado do cidadao.")
        privacy = _privacy_record(conversation, "ACKNOWLEDGED")
        citizen = Citizen(
            tenant_id=conversation.tenant_id,
            name=clean_name,
            contacts=[
                {
                    "tipo": "WHATSAPP",
                    "valor": contact.wa_user_id,
                    "principal": True,
                    "confirmado": True,
                }
            ],
            preferred_channel="WHATSAPP",
            contact_consent=bool(privacy and privacy.consent_required and privacy.granted),
            legal_basis=privacy.legal_basis if privacy else DEFAULT_LEGAL_BASIS,
            created_by_id=actor_id,
        )
        db.session.add(citizen)
        db.session.flush()
        created = True
    contact.citizen_id = citizen.id
    privacy = _privacy_record(conversation, "ACKNOWLEDGED")
    if privacy is not None:
        db.session.add(
            ConsentRecord(
                tenant_id=conversation.tenant_id,
                citizen_id=citizen.id,
                purpose=privacy.purpose,
                granted=privacy.granted if privacy.consent_required else False,
                legal_basis=privacy.legal_basis,
                source="WHATSAPP",
                evidence=f"sha256:{privacy.evidence_hash}",
                recorded_by_id=actor_id,
            )
        )
    transition_conversation(
        conversation,
        WhatsAppConversationState.INTENT,
        actor_type=actor_type,
        actor_id=actor_id,
        origin=origin,
        reason="Cidadao identificado com confirmacao explicita.",
    )
    db.session.add(
        OutboxEvent(
            tenant_id=conversation.tenant_id,
            event_type="WhatsappCitizenIdentified",
            aggregate_type="whatsapp_conversation",
            aggregate_id=str(conversation.id),
            payload={"conversationId": str(conversation.id), "citizenId": str(citizen.id)},
        )
    )
    return citizen, created


def save_request_draft(
    conversation: WhatsAppConversation,
    contact: WhatsAppContact,
    *,
    actor_id: uuid.UUID,
    title: str | None,
    description: str,
    address: str | None,
    category_id: uuid.UUID | None,
    declared_urgency: str | None = None,
    actor_type: str = "USER",
    origin: str = "INBOX_REQUEST_DRAFT",
) -> WhatsAppRequestDraft:
    _assert_active(conversation, contact)
    if contact.citizen_id is None:
        raise WhatsAppServiceFlowError("Identifique o cidadao antes de coletar a solicitacao.")
    clean_description = str(description or "").strip()
    if len(clean_description) < 3:
        raise WhatsAppServiceFlowError("A descricao deve possuir ao menos 3 caracteres.")
    clean_title = str(title or "").strip() or None
    if clean_title and len(clean_title) > 180:
        raise WhatsAppServiceFlowError("O titulo deve possuir no maximo 180 caracteres.")
    if (
        category_id is not None
        and db.session.execute(
            select(RequestCategory).where(
                RequestCategory.id == category_id,
                RequestCategory.tenant_id == conversation.tenant_id,
                RequestCategory.active.is_(True),
            )
        ).scalar_one_or_none()
        is None
    ):
        raise WhatsAppServiceFlowError("Categoria nao encontrada neste gabinete.")
    draft = db.session.execute(
        select(WhatsAppRequestDraft).where(
            WhatsAppRequestDraft.tenant_id == conversation.tenant_id,
            WhatsAppRequestDraft.conversation_id == conversation.id,
        )
    ).scalar_one_or_none()
    if draft is not None and draft.status == "CREATED":
        raise WhatsAppServiceFlowError("Esta coleta ja gerou uma solicitacao.")
    if draft is None:
        draft = WhatsAppRequestDraft(
            tenant_id=conversation.tenant_id,
            conversation_id=conversation.id,
            citizen_id=contact.citizen_id,
            created_by_id=actor_id,
            description=clean_description,
        )
        db.session.add(draft)
    draft.title = clean_title
    draft.description = clean_description
    draft.address = str(address or "").strip()[:500] or None
    draft.category_id = category_id
    urgency = str(declared_urgency or "").strip().upper() or None
    if urgency not in {None, "BAIXO", "MEDIO", "ALTO", "CRITICO"}:
        raise WhatsAppServiceFlowError("Urgencia declarada invalida.")
    draft.declared_urgency = urgency
    draft.status = "READY"
    transition_conversation(
        conversation,
        WhatsAppConversationState.REVIEW,
        actor_type=actor_type,
        actor_id=actor_id,
        origin=origin,
        reason="Dados minimos da solicitacao prontos para confirmacao.",
    )
    return draft


def confirm_request_draft(
    conversation: WhatsAppConversation,
    contact: WhatsAppContact,
    *,
    actor_id: uuid.UUID,
    idempotency_key: str,
    confirmed: bool,
    actor_type: str = "USER",
    origin: str = "INBOX_REQUEST_CONFIRMATION",
) -> tuple[ServiceRequest, str, bool]:
    _assert_active(conversation, contact)
    if not confirmed:
        raise WhatsAppServiceFlowError("A solicitacao precisa de confirmacao explicita.")
    key = str(idempotency_key or "").strip()
    if not 8 <= len(key) <= 120:
        raise WhatsAppServiceFlowError("Informe uma chave de idempotencia valida.")
    draft = db.session.execute(
        select(WhatsAppRequestDraft)
        .where(
            WhatsAppRequestDraft.tenant_id == conversation.tenant_id,
            WhatsAppRequestDraft.conversation_id == conversation.id,
        )
        .with_for_update()
    ).scalar_one_or_none()
    if draft is None:
        raise WhatsAppServiceFlowError("Nenhuma solicitacao esta pronta para confirmacao.")
    if draft.service_request_id is not None:
        if draft.idempotency_key != key:
            raise WhatsAppServiceFlowError("A solicitacao ja foi confirmada com outra chave.")
        existing = db.session.execute(
            select(ServiceRequest).where(
                ServiceRequest.tenant_id == conversation.tenant_id,
                ServiceRequest.id == draft.service_request_id,
            )
        ).scalar_one()
        return existing, "", False
    if draft.status != "READY":
        raise WhatsAppServiceFlowError("A solicitacao ainda nao esta pronta para protocolo.")
    category = (
        db.session.execute(
            select(RequestCategory).where(
                RequestCategory.tenant_id == conversation.tenant_id,
                RequestCategory.id == draft.category_id,
            )
        ).scalar_one_or_none()
        if draft.category_id
        else None
    )
    public_key = uuid.uuid4().hex + uuid.uuid4().hex[:8]
    now = datetime.now(UTC)
    service_request = ServiceRequest(
        tenant_id=conversation.tenant_id,
        created_by_id=actor_id,
        protocol=next_protocol(conversation.tenant_id),
        public_protocol=new_public_protocol(),
        source=RequestSource.WHATSAPP,
        title=draft.title,
        description=draft.description,
        address=draft.address,
        category_id=category.id if category else None,
        category=category.name if category else None,
        citizen_id=draft.citizen_id,
        urgency=draft.declared_urgency,
        status=RequestStatus.NOVA,
        priority=RequestPriority.MEDIA,
        due_at=now + timedelta(hours=category.sla_hours) if category else None,
        public_access_key_hash=hashlib.sha256(public_key.encode()).hexdigest(),
    )
    db.session.add(service_request)
    db.session.flush()
    service_request.history.append(
        RequestHistory(
            tenant_id=conversation.tenant_id,
            user_id=actor_id,
            action="request.created.whatsapp",
            changes={
                "protocolo": {"antes": None, "depois": service_request.protocol},
                "protocoloPublico": {
                    "antes": None,
                    "depois": service_request.public_protocol,
                },
                "status": {"antes": None, "depois": service_request.status.value},
            },
        )
    )
    draft.status = "CREATED"
    draft.idempotency_key = key
    draft.service_request_id = service_request.id
    draft.confirmed_at = now
    db.session.add(creation_event(service_request))
    _enqueue_triage_without_blocking_protocol(service_request, actor_id)
    from app.communications.whatsapp_media import link_conversation_media_to_request

    link_conversation_media_to_request(conversation, service_request)
    db.session.add(
        OutboxEvent(
            tenant_id=conversation.tenant_id,
            event_type=PROTOCOL_CREATED_EVENT,
            aggregate_type="whatsapp_conversation",
            aggregate_id=str(conversation.id),
            payload={
                "conversationId": str(conversation.id),
                "requestId": str(service_request.id),
                "publicProtocol": service_request.public_protocol,
            },
        )
    )
    transition_conversation(
        conversation,
        WhatsAppConversationState.PROTOCOL_CREATED,
        actor_type=actor_type,
        actor_id=actor_id,
        origin=origin,
        reason="Solicitacao confirmada e protocolada sem decisao automatica.",
    )
    return service_request, public_key, True


def _enqueue_triage_without_blocking_protocol(
    service_request: ServiceRequest, actor_id: uuid.UUID | None
) -> None:
    """Keep assistive AI configuration failures outside the protocol transaction."""
    try:
        enqueue_triage_execution(service_request, actor_id)
    except RuntimeError as error:
        current_app.logger.warning(
            "whatsapp_assistive_ai_unavailable request_id=%s error_type=%s",
            service_request.id,
            type(error).__name__,
        )


def service_flow_data(
    conversation: WhatsAppConversation,
    contact: WhatsAppContact,
) -> dict:
    privacy = (
        db.session.execute(
            select(WhatsAppPrivacyRecord)
            .where(
                WhatsAppPrivacyRecord.tenant_id == conversation.tenant_id,
                WhatsAppPrivacyRecord.conversation_id == conversation.id,
            )
            .order_by(WhatsAppPrivacyRecord.occurred_at)
        )
        .scalars()
        .all()
    )
    citizen = (
        db.session.execute(
            select(Citizen).where(
                Citizen.tenant_id == conversation.tenant_id,
                Citizen.id == contact.citizen_id,
            )
        ).scalar_one_or_none()
        if contact.citizen_id
        else None
    )
    draft = db.session.execute(
        select(WhatsAppRequestDraft).where(
            WhatsAppRequestDraft.tenant_id == conversation.tenant_id,
            WhatsAppRequestDraft.conversation_id == conversation.id,
        )
    ).scalar_one_or_none()
    service_request = (
        db.session.execute(
            select(ServiceRequest).where(
                ServiceRequest.tenant_id == conversation.tenant_id,
                ServiceRequest.id == draft.service_request_id,
            )
        ).scalar_one_or_none()
        if draft and draft.service_request_id
        else None
    )
    privacy_acknowledged = any(item.action == "ACKNOWLEDGED" for item in privacy)
    return {
        "privacidade": {
            "versaoAviso": NOTICE_VERSION,
            "solicitada": any(item.action == "NOTICE_REQUESTED" for item in privacy),
            "reconhecida": privacy_acknowledged,
            "baseLegal": privacy[-1].legal_basis if privacy else None,
            "evidenciaHash": privacy[-1].evidence_hash if privacy else None,
        },
        "cidadao": (
            {"id": str(citizen.id), "nome": citizen.social_name or citizen.name}
            if citizen
            else None
        ),
        "sugestoesCidadao": [
            {"id": str(item.id), "nome": item.social_name or item.name}
            for item in citizen_suggestions(contact)
        ]
        if citizen is None and privacy_acknowledged
        else [],
        "rascunhoSolicitacao": (
            {
                "id": str(draft.id),
                "titulo": draft.title,
                "descricao": draft.description,
                "endereco": draft.address,
                "urgenciaDeclarada": draft.declared_urgency,
                "categoriaId": str(draft.category_id) if draft.category_id else None,
                "status": draft.status,
            }
            if draft
            else None
        ),
        "solicitacao": (
            {
                "id": str(service_request.id),
                "protocoloPublico": service_request.public_protocol,
                "status": service_request.status.value,
            }
            if service_request
            else None
        ),
    }


def _privacy_record(
    conversation: WhatsAppConversation, action: str
) -> WhatsAppPrivacyRecord | None:
    return db.session.execute(
        select(WhatsAppPrivacyRecord).where(
            WhatsAppPrivacyRecord.tenant_id == conversation.tenant_id,
            WhatsAppPrivacyRecord.conversation_id == conversation.id,
            WhatsAppPrivacyRecord.notice_version == NOTICE_VERSION,
            WhatsAppPrivacyRecord.action == action,
        )
    ).scalar_one_or_none()


def _assert_active(conversation: WhatsAppConversation, contact: WhatsAppContact) -> None:
    if (
        conversation.state in TERMINAL_STATES
        or contact.opt_status != WhatsAppContactOptStatus.ACTIVE
    ):
        raise ConversationValidationError("Conversa encerrada nao permite esta operacao.")


def _evidence_hash(value: dict) -> str:
    canonical = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode()).hexdigest()
