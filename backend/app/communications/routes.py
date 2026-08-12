import io
import json
import time
import uuid
from datetime import UTC, datetime, timedelta
from html.parser import HTMLParser
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from flask import Blueprint, current_app, jsonify, request, send_file
from flask_jwt_extended import get_jwt, get_jwt_identity, jwt_required
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.audit import add_audit
from app.auth.permissions import roles_required
from app.communications.email import (
    WebhookVerificationError,
    email_idempotency_key,
    retrieve_received_email,
    verify_resend_webhook,
)
from app.communications.identity import (
    assisted_settings_data,
    get_assisted_settings,
    parse_candidate_ids,
    prepare_identity_review,
)
from app.communications.service import (
    ALLOWED_CHANNELS,
    CommunicationValidationError,
    render_template,
    scheduled_return_data,
    template_data,
    validate_template_body,
)
from app.communications.social import extract_meta_social_events
from app.communications.whatsapp import (
    WhatsAppWebhookError,
    extract_whatsapp_messages,
    verify_meta_signature,
)
from app.communications.whatsapp_conversations import (
    ConversationValidationError,
    assign_conversation,
    conversation_detail_data,
    conversation_search_filter,
    conversation_summary_data,
    mark_conversation_read,
    resume_bot,
    start_handoff,
)
from app.communications.whatsapp_flows import (
    WhatsAppFlowError,
    activate_flow_definition,
    bootstrap_flow_definitions,
    create_flow_version,
    flow_definition_data,
    flow_state_data,
    launch_flow,
)
from app.communications.whatsapp_inbound import ingest_meta_webhook
from app.communications.whatsapp_media import (
    WHATSAPP_MEDIA_ANALYSIS_EVENT,
    WHATSAPP_MEDIA_DOWNLOAD_EVENT,
    WhatsAppMediaError,
    media_asset_data,
    media_plaintext,
    review_media_asset,
    verify_media_token,
)
from app.communications.whatsapp_onboarding import (
    LIVE_INTEGRATION_STATUSES,
    MetaOnboardingError,
    SecretBackendUnavailable,
    WhatsAppOnboardingError,
    build_onboarding_state,
    create_onboarding_session,
    get_meta_onboarding_adapter,
    get_whatsapp_secret_store,
    integration_data,
    next_integration_version,
    normalize_idempotency_key,
    validate_onboarding_state,
)
from app.communications.whatsapp_outbound import (
    WHATSAPP_TEMPLATE_SYNC_EVENT,
    WhatsAppOutboundError,
    queue_outbound_message,
)
from app.communications.whatsapp_outbound import (
    create_template as create_whatsapp_template_domain,
)
from app.communications.whatsapp_outbound import (
    message_data as outbound_message_data,
)
from app.communications.whatsapp_outbound import (
    template_data as whatsapp_template_data,
)
from app.communications.whatsapp_pilot import (
    WhatsAppPilotError,
    change_pilot_status,
    operations_snapshot,
    pilot_data,
    review_gate,
)
from app.communications.whatsapp_queue import (
    WhatsAppQueueUnavailable,
    publish_webhook_events,
)
from app.communications.whatsapp_readiness import whatsapp_readiness_data
from app.communications.whatsapp_service_flow import (
    WhatsAppServiceFlowError,
    acknowledge_privacy,
    confirm_request_draft,
    identify_citizen,
    save_request_draft,
    service_flow_data,
)
from app.extensions import db, limiter
from app.models import (
    ChannelAssistedSetting,
    ChannelIdentityReview,
    ChannelIdentityReviewStatus,
    ChannelMessage,
    ChannelMessageStatus,
    Citizen,
    IntegrationSetting,
    IntegrationStatus,
    IntegrationType,
    InteractionDirection,
    InteractionVisibility,
    OutboxEvent,
    RequestCategory,
    RequestHistory,
    RequestInteraction,
    RequestSource,
    ResponseTemplate,
    ScheduledReturn,
    ScheduledReturnStatus,
    ServiceRequest,
    Tenant,
    User,
    UserStatus,
    WhatsAppContact,
    WhatsAppConversation,
    WhatsAppConversationMode,
    WhatsAppConversationState,
    WhatsAppConversationTransition,
    WhatsAppFlowDefinition,
    WhatsAppIntegration,
    WhatsAppIntegrationStatus,
    WhatsAppMediaAsset,
    WhatsAppMessage,
    WhatsAppMessageTemplate,
    WhatsAppOnboardingSession,
    WhatsAppOnboardingStatus,
    WhatsAppWebhookEvent,
    WhatsAppWebhookEventStatus,
)
from app.outbox.handlers import EMAIL_RESPONSE_EVENT
from app.requests.access import request_visibility_filters
from app.requests.service import creation_event, next_protocol

communications_bp = Blueprint("communications", __name__)


@communications_bp.get("/webhooks/meta/whatsapp")
@limiter.limit("60 per minute")
def verify_global_whatsapp_webhook():
    verify_token = current_app.config.get("WHATSAPP_WEBHOOK_VERIFY_TOKEN")
    mode = request.args.get("hub.mode")
    challenge = request.args.get("hub.challenge")
    supplied_token = request.args.get("hub.verify_token")
    if not verify_token:
        return jsonify(error="webhook_unavailable"), 503
    if mode == "subscribe" and supplied_token == verify_token and challenge:
        return challenge, 200, {"Content-Type": "text/plain"}
    return jsonify(error="invalid_token"), 403


@communications_bp.post("/webhooks/meta/whatsapp")
@limiter.limit("600 per minute")
def receive_global_whatsapp_webhook():
    started_at = time.perf_counter()
    app_secret = current_app.config.get("META_APP_SECRET")
    if not app_secret:
        return jsonify(error="webhook_unavailable"), 503

    max_bytes = int(current_app.config["WHATSAPP_WEBHOOK_MAX_BYTES"])
    if request.content_length is not None and request.content_length > max_bytes:
        current_app.logger.warning(
            "WhatsApp webhook payload rejected",
            extra={"security_event": "payload_too_large"},
        )
        return jsonify(error="payload_too_large"), 413
    raw_body = request.get_data(cache=True)
    if len(raw_body) > max_bytes:
        current_app.logger.warning(
            "WhatsApp webhook payload rejected",
            extra={"security_event": "payload_too_large"},
        )
        return jsonify(error="payload_too_large"), 413
    try:
        verify_meta_signature(raw_body, request.headers.get("X-Hub-Signature-256"), app_secret)
    except WhatsAppWebhookError:
        current_app.logger.warning(
            "WhatsApp webhook signature rejected",
            extra={"security_event": "invalid_signature"},
        )
        return jsonify(error="invalid_signature"), 401

    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify(error="invalid_payload"), 400

    correlation_id = request.headers.get("X-Correlation-ID") or uuid.uuid4().hex
    result = ingest_meta_webhook(payload, correlation_id=correlation_id[:64])
    if result.event_ids:
        try:
            publish_webhook_events(result.event_ids)
        except WhatsAppQueueUnavailable:
            db.session.rollback()
            current_app.logger.exception(
                "WhatsApp webhook persisted but queue publication failed",
                extra={"correlation_id": correlation_id[:64]},
            )
    if result.persisted_event_ids:
        ack_duration_ms = max(0, round((time.perf_counter() - started_at) * 1000))
        events = list(
            db.session.scalars(
                select(WhatsAppWebhookEvent).where(
                    WhatsAppWebhookEvent.id.in_(result.persisted_event_ids)
                )
            )
        )
        for event in events:
            event.ack_duration_ms = ack_duration_ms
        db.session.commit()
    return (
        jsonify(
            status="accepted",
            accepted=result.accepted,
            duplicated=result.duplicated,
            quarantined=result.quarantined,
            correlationId=correlation_id[:64],
        ),
        200,
    )


def _context() -> tuple[uuid.UUID, uuid.UUID]:
    return uuid.UUID(get_jwt()["tenant_id"]), uuid.UUID(get_jwt_identity())


@communications_bp.get("/tenants/<uuid:tenant_id>/whatsapp/readiness")
@roles_required("admin")
def whatsapp_readiness(tenant_id: uuid.UUID):
    context_tenant_id, _ = _context()
    if tenant_id != context_tenant_id:
        return jsonify(error="resource_not_found", message="Gabinete nao encontrado."), 404
    tenant = db.session.get(Tenant, tenant_id)
    if tenant is None:
        return jsonify(error="resource_not_found", message="Gabinete nao encontrado."), 404
    return jsonify(whatsapp_readiness_data(current_app.config, tenant.slug))


def _whatsapp_tenant(tenant_id: uuid.UUID) -> Tenant | None:
    context_tenant_id, _ = _context()
    if tenant_id != context_tenant_id:
        return None
    return db.session.get(Tenant, tenant_id)


@communications_bp.get("/tenants/<uuid:tenant_id>/whatsapp/integration")
@roles_required("admin")
def get_whatsapp_integration(tenant_id: uuid.UUID):
    if _whatsapp_tenant(tenant_id) is None:
        return jsonify(error="resource_not_found", message="Gabinete nao encontrado."), 404
    integration = (
        db.session.execute(
            select(WhatsAppIntegration)
            .where(WhatsAppIntegration.tenant_id == tenant_id)
            .order_by(WhatsAppIntegration.version.desc())
        )
        .scalars()
        .first()
    )
    if integration is None:
        return jsonify(error="resource_not_found", message="Integracao nao encontrada."), 404
    return jsonify(integration_data(integration))


@communications_bp.get("/tenants/<uuid:tenant_id>/whatsapp/health")
@roles_required("admin")
def get_whatsapp_health(tenant_id: uuid.UUID):
    if _whatsapp_tenant(tenant_id) is None:
        return jsonify(error="resource_not_found", message="Gabinete nao encontrado."), 404
    integration = (
        db.session.execute(
            select(WhatsAppIntegration)
            .where(WhatsAppIntegration.tenant_id == tenant_id)
            .order_by(WhatsAppIntegration.version.desc())
        )
        .scalars()
        .first()
    )
    if integration is None:
        return jsonify(error="resource_not_found", message="Integracao nao encontrada."), 404

    last_inbound_at = db.session.scalar(
        select(func.max(WhatsAppWebhookEvent.received_at)).where(
            WhatsAppWebhookEvent.tenant_id == tenant_id,
            WhatsAppWebhookEvent.event_type == "message",
        )
    )
    failed_events = db.session.scalar(
        select(func.count(WhatsAppWebhookEvent.id)).where(
            WhatsAppWebhookEvent.tenant_id == tenant_id,
            WhatsAppWebhookEvent.status == WhatsAppWebhookEventStatus.FAILED,
        )
    )
    webhook_ready = integration.webhook_subscribed_at is not None
    messaging_ready = integration.status == WhatsAppIntegrationStatus.ACTIVE
    issues = []
    if not webhook_ready:
        issues.append("WEBHOOK_NOT_SUBSCRIBED")
    if not messaging_ready:
        issues.append("INTEGRATION_NOT_ACTIVE")
    if failed_events:
        issues.append("INBOUND_EVENTS_FAILED")
    if integration.last_health_error:
        issues.append("INTEGRATION_HEALTH_ERROR")

    if integration.status in {
        WhatsAppIntegrationStatus.SUSPENDED,
        WhatsAppIntegrationStatus.DISCONNECTED,
        WhatsAppIntegrationStatus.REVOKED,
    }:
        status = "DOWN"
    elif issues:
        status = "DEGRADED"
    else:
        status = "HEALTHY"
    operation = operations_snapshot(tenant_id)
    last_outbound_at = db.session.scalar(
        select(func.max(WhatsAppMessage.occurred_at)).where(
            WhatsAppMessage.tenant_id == tenant_id,
            WhatsAppMessage.direction == "OUTBOUND",
        )
    )
    return jsonify(
        status=status,
        webhook=webhook_ready,
        messaging=messaging_ready,
        lastInboundAt=last_inbound_at.isoformat() if last_inbound_at else None,
        lastOutboundAt=last_outbound_at.isoformat() if last_outbound_at else None,
        issues=issues,
        operation=operation,
    )


@communications_bp.get("/tenants/<uuid:tenant_id>/whatsapp/operations")
@roles_required("admin", "manager")
def get_whatsapp_operations(tenant_id: uuid.UUID):
    if _whatsapp_tenant(tenant_id) is None:
        return jsonify(error="resource_not_found", message="Gabinete nao encontrado."), 404
    try:
        window_hours = int(request.args.get("windowHours") or 0) or None
    except (TypeError, ValueError):
        return jsonify(error="validation_error", message="Janela de metricas invalida."), 422
    return jsonify(operations_snapshot(tenant_id, window_hours=window_hours))


@communications_bp.get("/tenants/<uuid:tenant_id>/whatsapp/pilot")
@roles_required("admin", "manager")
def get_whatsapp_pilot(tenant_id: uuid.UUID):
    tenant = _whatsapp_tenant(tenant_id)
    if tenant is None:
        return jsonify(error="resource_not_found", message="Gabinete nao encontrado."), 404
    readiness = whatsapp_readiness_data(current_app.config, tenant.slug)
    return jsonify(pilot_data(tenant_id, readiness=readiness))


@communications_bp.put("/tenants/<uuid:tenant_id>/whatsapp/pilot/gates/<gate_key>")
@roles_required("admin")
def update_whatsapp_pilot_gate(tenant_id: uuid.UUID, gate_key: str):
    if _whatsapp_tenant(tenant_id) is None:
        return jsonify(error="resource_not_found", message="Gabinete nao encontrado."), 404
    _, actor_id = _context()
    payload = request.get_json(silent=True) or {}
    try:
        expires_at = _optional_iso_datetime(payload.get("expiraEm"))
        gate = review_gate(
            tenant_id,
            actor_id,
            gate_key,
            status=payload.get("status"),
            evidence_reference=payload.get("evidenciaReferencia"),
            notes=payload.get("observacao"),
            expires_at=expires_at,
        )
        db.session.flush()
        add_audit(
            tenant_id,
            actor_id,
            "whatsapp.pilot.gate.reviewed",
            "whatsapp_pilot_gate",
            gate.id,
            after={
                "gate": gate.gate_key,
                "status": gate.status,
                "evidenceHash": gate.evidence_hash,
                "expiresAt": gate.expires_at.isoformat() if gate.expires_at else None,
            },
        )
        db.session.commit()
    except (WhatsAppPilotError, ValueError) as error:
        db.session.rollback()
        return jsonify(error="validation_error", message=str(error)), 422
    tenant = db.session.get(Tenant, tenant_id)
    return jsonify(
        pilot_data(
            tenant_id,
            readiness=whatsapp_readiness_data(current_app.config, tenant.slug),
        )
    )


@communications_bp.post("/tenants/<uuid:tenant_id>/whatsapp/pilot/actions")
@roles_required("admin")
def update_whatsapp_pilot_status(tenant_id: uuid.UUID):
    tenant = _whatsapp_tenant(tenant_id)
    if tenant is None:
        return jsonify(error="resource_not_found", message="Gabinete nao encontrado."), 404
    _, actor_id = _context()
    payload = request.get_json(silent=True) or {}
    try:
        control = change_pilot_status(
            tenant_id,
            actor_id,
            action=payload.get("action"),
            reason=payload.get("reason"),
            readiness=whatsapp_readiness_data(current_app.config, tenant.slug),
        )
        db.session.flush()
        add_audit(
            tenant_id,
            actor_id,
            "whatsapp.pilot.status.changed",
            "whatsapp_pilot_control",
            control.id,
            after={
                "status": control.status,
                "outboundPaused": control.outbound_paused,
                "reasonProvided": bool(control.pause_reason),
            },
        )
        db.session.commit()
    except WhatsAppPilotError as error:
        db.session.rollback()
        return jsonify(error="validation_error", message=str(error)), 422
    return jsonify(
        pilot_data(
            tenant_id,
            readiness=whatsapp_readiness_data(current_app.config, tenant.slug),
        )
    )


def _optional_iso_datetime(value) -> datetime | None:
    if value in (None, ""):
        return None
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)


@communications_bp.get("/tenants/<uuid:tenant_id>/conversations")
@roles_required("admin", "manager", "staff")
def list_whatsapp_conversations(tenant_id: uuid.UUID):
    if _whatsapp_tenant(tenant_id) is None:
        return jsonify(error="resource_not_found", message="Gabinete nao encontrado."), 404
    statement = (
        select(WhatsAppConversation, WhatsAppContact, User)
        .join(
            WhatsAppContact,
            (WhatsAppContact.tenant_id == WhatsAppConversation.tenant_id)
            & (WhatsAppContact.id == WhatsAppConversation.contact_id),
        )
        .outerjoin(
            User,
            (User.tenant_id == WhatsAppConversation.tenant_id)
            & (User.id == WhatsAppConversation.assigned_user_id),
        )
        .where(WhatsAppConversation.tenant_id == tenant_id)
    )
    state = str(request.args.get("estado") or "").strip().upper()
    mode = str(request.args.get("modo") or "").strip().upper()
    assignee = str(request.args.get("responsavelId") or "").strip()
    query = str(request.args.get("q") or "").strip()[:120]
    unread_only = request.args.get("naoLidas") == "true"
    if state:
        try:
            statement = statement.where(
                WhatsAppConversation.state == WhatsAppConversationState(state)
            )
        except ValueError:
            return jsonify(error="validation_error", message="Estado invalido."), 422
    if mode:
        try:
            statement = statement.where(WhatsAppConversation.mode == WhatsAppConversationMode(mode))
        except ValueError:
            return jsonify(error="validation_error", message="Modo invalido."), 422
    if assignee == "SEM_RESPONSAVEL":
        statement = statement.where(WhatsAppConversation.assigned_user_id.is_(None))
    elif assignee:
        try:
            statement = statement.where(
                WhatsAppConversation.assigned_user_id == uuid.UUID(assignee)
            )
        except ValueError:
            return jsonify(error="validation_error", message="Responsavel invalido."), 422
    if query:
        statement = statement.where(conversation_search_filter(query))
    if unread_only:
        statement = statement.where(WhatsAppConversation.unread_count > 0)

    rows = db.session.execute(
        statement.order_by(
            WhatsAppConversation.last_message_at.desc(), WhatsAppConversation.id
        ).limit(200)
    ).all()
    content = []
    for conversation, contact, responsible in rows:
        last_channel_message = (
            db.session.execute(
                select(ChannelMessage)
                .join(
                    WhatsAppMessage,
                    WhatsAppMessage.channel_message_id == ChannelMessage.id,
                )
                .where(
                    WhatsAppMessage.tenant_id == tenant_id,
                    WhatsAppMessage.conversation_id == conversation.id,
                )
                .order_by(WhatsAppMessage.occurred_at.desc())
            )
            .scalars()
            .first()
        )
        content.append(
            conversation_summary_data(
                conversation,
                contact=contact,
                assignee=responsible,
                last_message=last_channel_message,
            )
        )
    users = list(
        db.session.scalars(
            select(User)
            .where(
                User.tenant_id == tenant_id,
                User.status == UserStatus.ACTIVE,
                User.role != "representative",
            )
            .order_by(User.name)
        )
    )
    return jsonify(
        content=content,
        resumo={
            "total": len(content),
            "naoLidas": sum(item["naoLidas"] for item in content),
            "humanas": sum(item["modo"] == "HUMAN" for item in content),
            "semResponsavel": sum(item["responsavel"] is None for item in content),
        },
        responsaveis=[{"id": str(user.id), "nome": user.name} for user in users],
    )


@communications_bp.get("/tenants/<uuid:tenant_id>/conversations/<uuid:conversation_id>")
@roles_required("admin", "manager", "staff")
def get_whatsapp_conversation(tenant_id: uuid.UUID, conversation_id: uuid.UUID):
    conversation = _tenant_conversation(tenant_id, conversation_id)
    if conversation is None:
        return jsonify(error="resource_not_found", message="Conversa nao encontrada."), 404
    contact = db.session.execute(
        select(WhatsAppContact).where(
            WhatsAppContact.tenant_id == tenant_id,
            WhatsAppContact.id == conversation.contact_id,
        )
    ).scalar_one()
    assignee = (
        db.session.execute(
            select(User).where(
                User.tenant_id == tenant_id,
                User.id == conversation.assigned_user_id,
            )
        ).scalar_one_or_none()
        if conversation.assigned_user_id
        else None
    )
    message_rows = db.session.execute(
        select(WhatsAppMessage, ChannelMessage)
        .outerjoin(
            ChannelMessage,
            (ChannelMessage.tenant_id == WhatsAppMessage.tenant_id)
            & (ChannelMessage.id == WhatsAppMessage.channel_message_id),
        )
        .where(
            WhatsAppMessage.tenant_id == tenant_id,
            WhatsAppMessage.conversation_id == conversation_id,
        )
        .order_by(WhatsAppMessage.occurred_at, WhatsAppMessage.id)
        .limit(500)
    ).all()
    transitions = list(
        db.session.scalars(
            select(WhatsAppConversationTransition)
            .where(
                WhatsAppConversationTransition.tenant_id == tenant_id,
                WhatsAppConversationTransition.conversation_id == conversation_id,
            )
            .order_by(WhatsAppConversationTransition.occurred_at)
        )
    )
    result = conversation_detail_data(
        conversation,
        contact=contact,
        assignee=assignee,
        messages=list(message_rows),
        transitions=transitions,
    )
    result["jornada"] = service_flow_data(conversation, contact)
    result["whatsappFlow"] = flow_state_data(conversation)
    result["midias"] = [
        media_asset_data(item)
        for item in db.session.scalars(
            select(WhatsAppMediaAsset)
            .where(
                WhatsAppMediaAsset.tenant_id == tenant_id,
                WhatsAppMediaAsset.conversation_id == conversation.id,
            )
            .order_by(WhatsAppMediaAsset.created_at)
        )
    ]
    result["categorias"] = [
        {"id": str(item.id), "nome": item.name}
        for item in db.session.scalars(
            select(RequestCategory)
            .where(
                RequestCategory.tenant_id == tenant_id,
                RequestCategory.active.is_(True),
            )
            .order_by(RequestCategory.name)
        )
    ]
    result["templatesSaida"] = [
        whatsapp_template_data(item)
        for item in db.session.scalars(
            select(WhatsAppMessageTemplate)
            .where(
                WhatsAppMessageTemplate.tenant_id == tenant_id,
                WhatsAppMessageTemplate.integration_id == conversation.integration_id,
                WhatsAppMessageTemplate.status == "APPROVED",
                WhatsAppMessageTemplate.active.is_(True),
                WhatsAppMessageTemplate.category != "MARKETING",
            )
            .order_by(WhatsAppMessageTemplate.name, WhatsAppMessageTemplate.version.desc())
        )
    ]
    return jsonify(result)


@communications_bp.post("/tenants/<uuid:tenant_id>/conversations/<uuid:conversation_id>/messages")
@roles_required("admin", "manager", "staff")
def send_whatsapp_conversation_message(tenant_id: uuid.UUID, conversation_id: uuid.UUID):
    conversation = _tenant_conversation(tenant_id, conversation_id)
    if conversation is None:
        return jsonify(error="resource_not_found", message="Conversa não encontrada."), 404
    payload = request.get_json(silent=True) or {}
    try:
        template_id = uuid.UUID(str(payload["templateId"])) if payload.get("templateId") else None
        message, created = queue_outbound_message(
            conversation,
            actor_id=uuid.UUID(get_jwt_identity()),
            idempotency_key=str(request.headers.get("Idempotency-Key") or ""),
            text=payload.get("texto"),
            template_id=template_id,
            parameters=payload.get("parametros") or [],
        )
        if created:
            add_audit(
                tenant_id,
                uuid.UUID(get_jwt_identity()),
                "whatsapp.outbound.queued",
                "whatsapp_message",
                message.id,
                after={
                    "tipo": message.message_type,
                    "politica": message.policy_decision,
                    "templateId": str(message.template_id) if message.template_id else None,
                },
            )
        db.session.commit()
    except (ValueError, WhatsAppOutboundError) as error:
        db.session.rollback()
        return jsonify(error="validation_error", message=str(error)), 422
    return jsonify(outbound_message_data(message)), 202 if created else 200


@communications_bp.get("/tenants/<uuid:tenant_id>/whatsapp/templates")
@roles_required("admin", "manager")
def list_whatsapp_message_templates(tenant_id: uuid.UUID):
    if _whatsapp_tenant(tenant_id) is None:
        return jsonify(error="resource_not_found", message="Gabinete não encontrado."), 404
    items = list(
        db.session.scalars(
            select(WhatsAppMessageTemplate)
            .where(WhatsAppMessageTemplate.tenant_id == tenant_id)
            .order_by(WhatsAppMessageTemplate.name, WhatsAppMessageTemplate.version.desc())
        )
    )
    return jsonify(content=[whatsapp_template_data(item) for item in items])


@communications_bp.post("/tenants/<uuid:tenant_id>/whatsapp/templates")
@roles_required("admin")
def create_whatsapp_message_template(tenant_id: uuid.UUID):
    if _whatsapp_tenant(tenant_id) is None:
        return jsonify(error="resource_not_found", message="Gabinete não encontrado."), 404
    payload = request.get_json(silent=True) or {}
    integration = db.session.scalar(
        select(WhatsAppIntegration)
        .where(
            WhatsAppIntegration.tenant_id == tenant_id,
            WhatsAppIntegration.status == WhatsAppIntegrationStatus.ACTIVE,
        )
        .order_by(WhatsAppIntegration.version.desc())
    )
    if integration is None:
        return jsonify(error="validation_error", message="Integração ativa não encontrada."), 422
    try:
        item = create_whatsapp_template_domain(
            tenant_id=tenant_id,
            integration_id=integration.id,
            actor_id=uuid.UUID(get_jwt_identity()),
            name=payload.get("nome"),
            language=payload.get("idioma") or "pt_BR",
            category=payload.get("categoria") or "UTILITY",
            body=payload.get("conteudo"),
            variables=payload.get("variaveis") or [],
        )
        add_audit(
            tenant_id,
            uuid.UUID(get_jwt_identity()),
            "whatsapp.template.created",
            "whatsapp_message_template",
            item.id,
            after={"nome": item.name, "versao": item.version, "status": item.status},
        )
        db.session.commit()
    except WhatsAppOutboundError as error:
        db.session.rollback()
        return jsonify(error="validation_error", message=str(error)), 422
    return jsonify(whatsapp_template_data(item)), 202


@communications_bp.post("/tenants/<uuid:tenant_id>/whatsapp/templates/<uuid:template_id>/refresh")
@roles_required("admin", "manager")
def refresh_whatsapp_message_template(tenant_id: uuid.UUID, template_id: uuid.UUID):
    item = db.session.scalar(
        select(WhatsAppMessageTemplate).where(
            WhatsAppMessageTemplate.tenant_id == tenant_id,
            WhatsAppMessageTemplate.id == template_id,
        )
    )
    if item is None or _whatsapp_tenant(tenant_id) is None:
        return jsonify(error="resource_not_found", message="Template não encontrado."), 404
    db.session.add(
        OutboxEvent(
            tenant_id=tenant_id,
            event_type=WHATSAPP_TEMPLATE_SYNC_EVENT,
            aggregate_type="whatsapp_message_template",
            aggregate_id=str(item.id),
            payload={"templateId": str(item.id)},
        )
    )
    db.session.commit()
    return jsonify(whatsapp_template_data(item)), 202


@communications_bp.get("/tenants/<uuid:tenant_id>/whatsapp/flows")
@roles_required("admin", "manager")
def list_whatsapp_flows(tenant_id: uuid.UUID):
    if _whatsapp_tenant(tenant_id) is None:
        return jsonify(error="resource_not_found", message="Gabinete nao encontrado."), 404
    items = list(
        db.session.scalars(
            select(WhatsAppFlowDefinition)
            .where(WhatsAppFlowDefinition.tenant_id == tenant_id)
            .order_by(
                WhatsAppFlowDefinition.flow_key,
                WhatsAppFlowDefinition.environment,
                WhatsAppFlowDefinition.version.desc(),
            )
        )
    )
    return jsonify(content=[flow_definition_data(item) for item in items])


@communications_bp.post("/tenants/<uuid:tenant_id>/whatsapp/flows/bootstrap")
@roles_required("admin")
def bootstrap_whatsapp_flows(tenant_id: uuid.UUID):
    if _whatsapp_tenant(tenant_id) is None:
        return jsonify(error="resource_not_found", message="Gabinete nao encontrado."), 404
    try:
        items = bootstrap_flow_definitions(
            tenant_id,
            uuid.UUID(get_jwt_identity()),
            environment=_flow_environment(),
        )
        db.session.commit()
    except WhatsAppFlowError as error:
        db.session.rollback()
        return jsonify(error="validation_error", message=str(error)), 422
    return jsonify(content=[flow_definition_data(item) for item in items]), 201


@communications_bp.post("/tenants/<uuid:tenant_id>/whatsapp/flows/versions")
@roles_required("admin")
def create_whatsapp_flow_version(tenant_id: uuid.UUID):
    if _whatsapp_tenant(tenant_id) is None:
        return jsonify(error="resource_not_found", message="Gabinete nao encontrado."), 404
    payload = request.get_json(silent=True) or {}
    try:
        item = create_flow_version(
            tenant_id,
            uuid.UUID(get_jwt_identity()),
            flow_key=str(payload.get("chave") or ""),
            environment=_flow_environment(),
        )
        db.session.commit()
    except WhatsAppFlowError as error:
        db.session.rollback()
        return jsonify(error="validation_error", message=str(error)), 422
    return jsonify(flow_definition_data(item)), 201


@communications_bp.post("/tenants/<uuid:tenant_id>/whatsapp/flows/<uuid:definition_id>/activate")
@roles_required("admin")
def activate_whatsapp_flow(tenant_id: uuid.UUID, definition_id: uuid.UUID):
    if _whatsapp_tenant(tenant_id) is None:
        return jsonify(error="resource_not_found", message="Gabinete nao encontrado."), 404
    item = db.session.execute(
        select(WhatsAppFlowDefinition).where(
            WhatsAppFlowDefinition.tenant_id == tenant_id,
            WhatsAppFlowDefinition.id == definition_id,
        )
    ).scalar_one_or_none()
    if item is None:
        return jsonify(error="resource_not_found", message="Flow nao encontrado."), 404
    payload = request.get_json(silent=True) or {}
    try:
        activate_flow_definition(item, meta_flow_id=payload.get("metaFlowId"))
        db.session.commit()
    except WhatsAppFlowError as error:
        db.session.rollback()
        return jsonify(error="validation_error", message=str(error)), 422
    return jsonify(flow_definition_data(item))


@communications_bp.post(
    "/tenants/<uuid:tenant_id>/conversations/<uuid:conversation_id>/flows/<flow_key>/launch"
)
@roles_required("admin", "manager", "staff")
def launch_whatsapp_flow(tenant_id: uuid.UUID, conversation_id: uuid.UUID, flow_key: str):
    conversation = _tenant_conversation(tenant_id, conversation_id)
    if conversation is None:
        return jsonify(error="resource_not_found", message="Conversa nao encontrada."), 404
    try:
        mode, session = launch_flow(
            conversation,
            _conversation_contact(conversation),
            actor_id=uuid.UUID(get_jwt_identity()),
            flow_key=flow_key,
            environment=_flow_environment(),
        )
        db.session.commit()
    except (WhatsAppFlowError, ConversationValidationError) as error:
        db.session.rollback()
        return jsonify(error="validation_error", message=str(error)), 422
    return (
        jsonify(
            modo=mode,
            estado=conversation.state.value,
            sessaoId=str(session.id) if session else None,
            expiraEm=session.expires_at.isoformat() if session else None,
        ),
        202 if session else 200,
    )


@communications_bp.get("/tenants/<uuid:tenant_id>/whatsapp/media/<uuid:asset_id>/download")
@roles_required("admin", "manager", "staff")
def download_whatsapp_media(tenant_id: uuid.UUID, asset_id: uuid.UUID):
    asset = _tenant_media_asset(tenant_id, asset_id)
    if asset is None:
        return jsonify(error="resource_not_found", message="Mídia não encontrada."), 404
    if not verify_media_token(str(request.args.get("token") or ""), asset):
        return jsonify(error="invalid_token", message="Link inválido ou expirado."), 403
    try:
        content = media_plaintext(asset)
    except Exception:
        return jsonify(error="resource_not_found", message="Arquivo não encontrado."), 404
    return send_file(
        io.BytesIO(content),
        mimetype=asset.mime_type,
        as_attachment=True,
        download_name=asset.original_name or f"whatsapp-{asset.id}",
    )


@communications_bp.post("/tenants/<uuid:tenant_id>/whatsapp/media/<uuid:asset_id>/review")
@roles_required("admin", "manager", "staff")
def review_whatsapp_media(tenant_id: uuid.UUID, asset_id: uuid.UUID):
    asset = _tenant_media_asset(tenant_id, asset_id)
    if asset is None:
        return jsonify(error="resource_not_found", message="Mídia não encontrada."), 404
    payload = request.get_json(silent=True) or {}
    try:
        review_media_asset(
            asset,
            actor_id=uuid.UUID(get_jwt_identity()),
            action=str(payload.get("acao") or ""),
            text=payload.get("texto"),
        )
        add_audit(
            tenant_id,
            uuid.UUID(get_jwt_identity()),
            "whatsapp.media.reviewed",
            "whatsapp_media_asset",
            asset.id,
            after={"decisao": asset.review_status, "analise": asset.analysis_type},
        )
        db.session.commit()
    except WhatsAppMediaError as error:
        db.session.rollback()
        return jsonify(error="validation_error", message=str(error)), 422
    return jsonify(media_asset_data(asset))


@communications_bp.post("/tenants/<uuid:tenant_id>/whatsapp/media/<uuid:asset_id>/retry")
@roles_required("admin", "manager", "staff")
def retry_whatsapp_media(tenant_id: uuid.UUID, asset_id: uuid.UUID):
    asset = _tenant_media_asset(tenant_id, asset_id)
    if asset is None:
        return jsonify(error="resource_not_found", message="Mídia não encontrada."), 404
    if asset.status == "FAILED":
        asset.status = "RECEIVED"
        event_type = WHATSAPP_MEDIA_DOWNLOAD_EVENT
    elif asset.analysis_status == "FAILED" and asset.status == "READY":
        asset.analysis_status = "PENDING"
        asset.review_status = "PENDING"
        event_type = WHATSAPP_MEDIA_ANALYSIS_EVENT
    else:
        return jsonify(error="conflict", message="A mídia não permite reprocessamento."), 409
    asset.error = None
    asset.error_code = None
    db.session.add(
        OutboxEvent(
            tenant_id=tenant_id,
            event_type=event_type,
            aggregate_type="whatsapp_media_asset",
            aggregate_id=str(asset.id),
            payload={"mediaAssetId": str(asset.id)},
        )
    )
    db.session.commit()
    return jsonify(media_asset_data(asset)), 202


def _tenant_media_asset(tenant_id: uuid.UUID, asset_id: uuid.UUID) -> WhatsAppMediaAsset | None:
    if _whatsapp_tenant(tenant_id) is None:
        return None
    return db.session.execute(
        select(WhatsAppMediaAsset).where(
            WhatsAppMediaAsset.id == asset_id,
            WhatsAppMediaAsset.tenant_id == tenant_id,
        )
    ).scalar_one_or_none()


@communications_bp.post("/tenants/<uuid:tenant_id>/conversations/<uuid:conversation_id>/privacy")
@roles_required("admin", "manager", "staff")
def acknowledge_whatsapp_privacy(tenant_id: uuid.UUID, conversation_id: uuid.UUID):
    conversation = _tenant_conversation(tenant_id, conversation_id)
    if conversation is None:
        return jsonify(error="resource_not_found", message="Conversa nao encontrada."), 404
    contact = _conversation_contact(conversation)
    payload = request.get_json(silent=True) or {}
    try:
        record = acknowledge_privacy(
            conversation,
            contact,
            actor_id=uuid.UUID(get_jwt_identity()),
            legal_basis=str(payload.get("baseLegal") or ""),
            consent_required=bool(payload.get("consentimentoNecessario", False)),
            granted=payload.get("concedido"),
            provider_message_id=payload.get("mensagemEvidenciaId"),
        )
        db.session.commit()
    except (ConversationValidationError, WhatsAppServiceFlowError) as error:
        db.session.rollback()
        return jsonify(error="validation_error", message=str(error)), 422
    return jsonify(
        estado=conversation.state.value,
        privacidade={
            "versaoAviso": record.notice_version,
            "baseLegal": record.legal_basis,
            "evidenciaHash": record.evidence_hash,
        },
    )


@communications_bp.post("/tenants/<uuid:tenant_id>/conversations/<uuid:conversation_id>/citizen")
@roles_required("admin", "manager", "staff")
def identify_whatsapp_citizen(tenant_id: uuid.UUID, conversation_id: uuid.UUID):
    conversation = _tenant_conversation(tenant_id, conversation_id)
    if conversation is None:
        return jsonify(error="resource_not_found", message="Conversa nao encontrada."), 404
    payload = request.get_json(silent=True) or {}
    try:
        citizen_id = uuid.UUID(str(payload["cidadaoId"])) if payload.get("cidadaoId") else None
        citizen, created = identify_citizen(
            conversation,
            _conversation_contact(conversation),
            actor_id=uuid.UUID(get_jwt_identity()),
            citizen_id=citizen_id,
            name=payload.get("nome"),
            confirmed=payload.get("confirmado") is True,
        )
        db.session.commit()
    except (ValueError, ConversationValidationError, WhatsAppServiceFlowError) as error:
        db.session.rollback()
        return jsonify(error="validation_error", message=str(error)), 422
    return (
        jsonify(
            estado=conversation.state.value,
            cidadao={"id": str(citizen.id), "nome": citizen.social_name or citizen.name},
        ),
        201 if created else 200,
    )


@communications_bp.put(
    "/tenants/<uuid:tenant_id>/conversations/<uuid:conversation_id>/request-draft"
)
@roles_required("admin", "manager", "staff")
def update_whatsapp_request_draft(tenant_id: uuid.UUID, conversation_id: uuid.UUID):
    conversation = _tenant_conversation(tenant_id, conversation_id)
    if conversation is None:
        return jsonify(error="resource_not_found", message="Conversa nao encontrada."), 404
    payload = request.get_json(silent=True) or {}
    try:
        category_id = uuid.UUID(str(payload["categoriaId"])) if payload.get("categoriaId") else None
        draft = save_request_draft(
            conversation,
            _conversation_contact(conversation),
            actor_id=uuid.UUID(get_jwt_identity()),
            title=payload.get("titulo"),
            description=str(payload.get("descricao") or ""),
            address=payload.get("endereco"),
            category_id=category_id,
        )
        db.session.commit()
    except (ValueError, ConversationValidationError, WhatsAppServiceFlowError) as error:
        db.session.rollback()
        return jsonify(error="validation_error", message=str(error)), 422
    return jsonify(id=str(draft.id), estado=conversation.state.value, status=draft.status)


@communications_bp.post(
    "/tenants/<uuid:tenant_id>/conversations/<uuid:conversation_id>/request-draft/confirm"
)
@roles_required("admin", "manager", "staff")
def confirm_whatsapp_request(tenant_id: uuid.UUID, conversation_id: uuid.UUID):
    conversation = _tenant_conversation(tenant_id, conversation_id)
    if conversation is None:
        return jsonify(error="resource_not_found", message="Conversa nao encontrada."), 404
    payload = request.get_json(silent=True) or {}
    try:
        service_request, public_key, created = confirm_request_draft(
            conversation,
            _conversation_contact(conversation),
            actor_id=uuid.UUID(get_jwt_identity()),
            idempotency_key=request.headers.get("Idempotency-Key", ""),
            confirmed=payload.get("confirmado") is True,
        )
        db.session.commit()
    except (ConversationValidationError, WhatsAppServiceFlowError) as error:
        db.session.rollback()
        return jsonify(error="validation_error", message=str(error)), 422
    response = {
        "id": str(service_request.id),
        "protocoloPublico": service_request.public_protocol,
        "estado": conversation.state.value,
        "criada": created,
    }
    if public_key:
        response["chaveAcompanhamento"] = public_key
    return jsonify(response), 201 if created else 200


@communications_bp.post("/tenants/<uuid:tenant_id>/conversations/<uuid:conversation_id>/read")
@roles_required("admin", "manager", "staff")
def read_whatsapp_conversation(tenant_id: uuid.UUID, conversation_id: uuid.UUID):
    conversation = _tenant_conversation(tenant_id, conversation_id)
    if conversation is None:
        return jsonify(error="resource_not_found", message="Conversa nao encontrada."), 404
    mark_conversation_read(conversation)
    db.session.commit()
    return jsonify(naoLidas=0, lidaEm=conversation.last_read_at.isoformat())


@communications_bp.put("/tenants/<uuid:tenant_id>/conversations/<uuid:conversation_id>/assignment")
@roles_required("admin", "manager", "staff")
def update_whatsapp_conversation_assignment(tenant_id: uuid.UUID, conversation_id: uuid.UUID):
    conversation = _tenant_conversation(tenant_id, conversation_id)
    if conversation is None:
        return jsonify(error="resource_not_found", message="Conversa nao encontrada."), 404
    payload = request.get_json(silent=True) or {}
    try:
        assignee_id = (
            uuid.UUID(str(payload["responsavelId"])) if payload.get("responsavelId") else None
        )
        assign_conversation(
            conversation,
            actor_id=uuid.UUID(get_jwt_identity()),
            assignee_id=assignee_id,
        )
    except (ValueError, ConversationValidationError) as error:
        return jsonify(error="validation_error", message=str(error)), 422
    db.session.commit()
    return jsonify(status="updated", responsavelId=str(assignee_id) if assignee_id else None)


@communications_bp.post("/tenants/<uuid:tenant_id>/conversations/<uuid:conversation_id>/handoff")
@roles_required("admin", "manager", "staff")
def handoff_whatsapp_conversation(tenant_id: uuid.UUID, conversation_id: uuid.UUID):
    conversation = _tenant_conversation(tenant_id, conversation_id)
    if conversation is None:
        return jsonify(error="resource_not_found", message="Conversa nao encontrada."), 404
    payload = request.get_json(silent=True) or {}
    try:
        assignee_id = uuid.UUID(str(payload["assigneeId"])) if payload.get("assigneeId") else None
        start_handoff(
            conversation,
            actor_id=uuid.UUID(get_jwt_identity()),
            assignee_id=assignee_id,
            reason=str(payload.get("reason") or "").strip()[:500],
        )
    except (ValueError, ConversationValidationError) as error:
        return jsonify(error="validation_error", message=str(error)), 422
    db.session.commit()
    return jsonify(estado=conversation.state.value, modo=conversation.mode.value), 200


@communications_bp.post("/tenants/<uuid:tenant_id>/conversations/<uuid:conversation_id>/resume-bot")
@roles_required("admin", "manager")
def resume_whatsapp_conversation_bot(tenant_id: uuid.UUID, conversation_id: uuid.UUID):
    conversation = _tenant_conversation(tenant_id, conversation_id)
    if conversation is None:
        return jsonify(error="resource_not_found", message="Conversa nao encontrada."), 404
    payload = request.get_json(silent=True) or {}
    try:
        resume_bot(
            conversation,
            actor_id=uuid.UUID(get_jwt_identity()),
            reason=str(payload.get("reason") or "").strip()[:500],
        )
    except ConversationValidationError as error:
        return jsonify(error="validation_error", message=str(error)), 422
    db.session.commit()
    return jsonify(estado=conversation.state.value, modo=conversation.mode.value), 200


def _tenant_conversation(
    tenant_id: uuid.UUID, conversation_id: uuid.UUID
) -> WhatsAppConversation | None:
    if _whatsapp_tenant(tenant_id) is None:
        return None
    return db.session.execute(
        select(WhatsAppConversation).where(
            WhatsAppConversation.tenant_id == tenant_id,
            WhatsAppConversation.id == conversation_id,
        )
    ).scalar_one_or_none()


def _conversation_contact(conversation: WhatsAppConversation) -> WhatsAppContact:
    return db.session.execute(
        select(WhatsAppContact).where(
            WhatsAppContact.tenant_id == conversation.tenant_id,
            WhatsAppContact.id == conversation.contact_id,
        )
    ).scalar_one()


def _flow_environment() -> str:
    environment = str(current_app.config.get("APP_ENV") or "development").lower()
    return {
        "production": "PRODUCTION",
        "staging": "STAGING",
    }.get(environment, "SANDBOX")


@communications_bp.post("/tenants/<uuid:tenant_id>/whatsapp/onboarding-sessions")
@roles_required("admin")
@limiter.limit("10 per minute")
def create_whatsapp_onboarding(tenant_id: uuid.UUID):
    tenant = _whatsapp_tenant(tenant_id)
    if tenant is None:
        return jsonify(error="resource_not_found", message="Gabinete nao encontrado."), 404
    readiness = whatsapp_readiness_data(current_app.config, tenant.slug)
    if not readiness["prontoSandbox"] or not readiness["embeddedSignupHabilitado"]:
        return (
            jsonify(
                error="whatsapp_not_ready",
                message="O onboarding WhatsApp ainda nao esta habilitado para este gabinete.",
                pendencias=readiness["pendencias"],
            ),
            503,
        )
    _, user_id = _context()
    try:
        idempotency_key = normalize_idempotency_key(request.headers.get("Idempotency-Key"))
        session, created = create_onboarding_session(
            tenant=tenant,
            user_id=user_id,
            idempotency_key=idempotency_key,
        )
        if session.status != WhatsAppOnboardingStatus.PENDING:
            raise WhatsAppOnboardingError(
                "idempotency_conflict",
                "A chave de idempotencia pertence a uma sessao encerrada.",
                409,
            )
        state = build_onboarding_state(session, str(current_app.config["SECRET_KEY"]))
        if created:
            add_audit(
                tenant_id,
                user_id,
                "whatsapp.onboarding.started",
                "whatsapp_onboarding_session",
                session.id,
                after={"status": session.status.value, "expiresAt": session.expires_at.isoformat()},
            )
        db.session.commit()
    except WhatsAppOnboardingError as exc:
        db.session.rollback()
        return jsonify(error=exc.code, message=exc.message), exc.status_code
    return (
        jsonify(
            state=state,
            expiresAt=session.expires_at.isoformat(),
            appId=current_app.config["WHATSAPP_META_APP_ID"],
            configurationId=current_app.config["WHATSAPP_META_CONFIGURATION_ID"],
            graphApiVersion=current_app.config["WHATSAPP_GRAPH_API_VERSION"],
        ),
        201 if created else 200,
    )


def _fail_whatsapp_onboarding(session_id: uuid.UUID, code: str) -> None:
    db.session.rollback()
    session = db.session.get(WhatsAppOnboardingSession, session_id)
    if session:
        session.status = WhatsAppOnboardingStatus.FAILED
        session.failure_code = code
        session.state_nonce = None
        db.session.commit()


@communications_bp.post("/tenants/<uuid:tenant_id>/whatsapp/onboarding-callback")
@roles_required("admin")
@limiter.limit("10 per minute")
def complete_whatsapp_onboarding(tenant_id: uuid.UUID):
    tenant = _whatsapp_tenant(tenant_id)
    if tenant is None:
        return jsonify(error="resource_not_found", message="Gabinete nao encontrado."), 404
    readiness = whatsapp_readiness_data(current_app.config, tenant.slug)
    if not readiness["prontoSandbox"] or not readiness["embeddedSignupHabilitado"]:
        return (
            jsonify(
                error="whatsapp_not_ready",
                message="O onboarding WhatsApp foi desabilitado para este gabinete.",
            ),
            503,
        )
    payload = request.get_json(silent=True) or {}
    code = str(payload.get("code") or "").strip()
    state = str(payload.get("state") or "").strip()
    if not code or len(code) > 4096 or not state or len(state) > 512:
        return jsonify(error="invalid_callback", message="Callback da Meta invalido."), 400
    _, user_id = _context()
    try:
        session = validate_onboarding_state(tenant_id=tenant_id, state=state)
        if session.initiated_by_id != user_id:
            raise WhatsAppOnboardingError(
                "invalid_state", "A sessao pertence a outro administrador."
            )
        session.status = WhatsAppOnboardingStatus.PROCESSING
        session.consumed_at = datetime.now(UTC)
        db.session.commit()
    except WhatsAppOnboardingError as exc:
        db.session.rollback()
        return jsonify(error=exc.code, message=exc.message), exc.status_code

    session_id = session.id
    secret_reference = None
    try:
        result = get_meta_onboarding_adapter().complete(code)
        if not result.webhook_subscribed:
            raise MetaOnboardingError("A Meta nao confirmou a assinatura do webhook.")
        if not result.phone_registered:
            raise MetaOnboardingError("A Meta nao confirmou o registro do numero.")
        conflict = db.session.execute(
            select(WhatsAppIntegration.id).where(
                WhatsAppIntegration.phone_number_id == result.phone_number_id,
                WhatsAppIntegration.status.in_(LIVE_INTEGRATION_STATUSES),
            )
        ).first()
        if conflict:
            raise WhatsAppOnboardingError(
                "phone_number_conflict",
                "O numero autorizado ja esta vinculado a uma integracao.",
                409,
            )
        integration = WhatsAppIntegration(
            tenant_id=tenant_id,
            business_portfolio_id=result.business_portfolio_id,
            waba_id=result.waba_id,
            phone_number_id=result.phone_number_id,
            display_phone=result.display_phone,
            display_name=result.display_name,
            status=WhatsAppIntegrationStatus.PENDING,
            version=next_integration_version(tenant_id),
            token_secret_ref="pending",  # noqa: S106 - overwritten before commit
            webhook_subscribed_at=datetime.now(UTC),
            created_by_id=user_id,
        )
        db.session.add(integration)
        db.session.flush()
        secret_reference = get_whatsapp_secret_store().put(
            tenant_id=tenant_id,
            integration_id=integration.id,
            value=json.dumps(
                {"access_token": result.access_token, "two_step_pin": result.two_step_pin},
                separators=(",", ":"),
            ),
        )
        integration.token_secret_ref = secret_reference
        session = db.session.get(WhatsAppOnboardingSession, session_id)
        session.status = WhatsAppOnboardingStatus.COMPLETED
        session.integration_id = integration.id
        session.state_nonce = None
        add_audit(
            tenant_id,
            user_id,
            "whatsapp.onboarding.completed",
            "whatsapp_integration",
            integration.id,
            after={"status": integration.status.value, "version": integration.version},
        )
        db.session.commit()
    except WhatsAppOnboardingError as exc:
        _fail_whatsapp_onboarding(session_id, exc.code)
        return jsonify(error=exc.code, message=exc.message), exc.status_code
    except SecretBackendUnavailable:
        _fail_whatsapp_onboarding(session_id, "secret_backend_unavailable")
        return (
            jsonify(
                error="secret_backend_unavailable",
                message="O cofre de segredos do WhatsApp nao esta disponivel.",
            ),
            503,
        )
    except MetaOnboardingError:
        _fail_whatsapp_onboarding(session_id, "meta_onboarding_failed")
        return (
            jsonify(
                error="meta_onboarding_failed",
                message="Nao foi possivel validar o onboarding junto a Meta.",
            ),
            502,
        )
    except IntegrityError:
        if secret_reference:
            get_whatsapp_secret_store().delete(secret_reference)
        _fail_whatsapp_onboarding(session_id, "integration_conflict")
        return (
            jsonify(error="integration_conflict", message="A integracao entrou em conflito."),
            409,
        )
    return jsonify(integration_data(integration)), 202


def _parse_datetime(value, timezone_name: str = "UTC") -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        raise CommunicationValidationError("Data e hora inválidas.") from None
    if parsed.tzinfo is None:
        try:
            parsed = parsed.replace(tzinfo=ZoneInfo(timezone_name))
        except ZoneInfoNotFoundError:
            parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _service_request(request_id: uuid.UUID, tenant_id: uuid.UUID):
    return db.session.execute(
        select(ServiceRequest).where(
            ServiceRequest.id == request_id,
            *request_visibility_filters(tenant_id),
        )
    ).scalar_one_or_none()


def _template_payload(payload: dict, tenant_id: uuid.UUID) -> dict:
    name = str(payload.get("nome", "")).strip()
    channel = str(payload.get("canal", "")).upper().strip()
    body = str(payload.get("conteudo", "")).strip()
    if len(name) < 2 or not body:
        raise CommunicationValidationError("Informe nome e conteúdo do template.")
    if channel not in ALLOWED_CHANNELS:
        raise CommunicationValidationError("Canal inválido.")
    validate_template_body(body)
    category_id = payload.get("categoriaId")
    try:
        category_uuid = uuid.UUID(str(category_id)) if category_id else None
    except (TypeError, ValueError):
        raise CommunicationValidationError("Categoria inválida.") from None
    if category_uuid:
        category = db.session.execute(
            select(RequestCategory).where(
                RequestCategory.id == category_uuid,
                RequestCategory.tenant_id == tenant_id,
            )
        ).scalar_one_or_none()
        if category is None:
            raise CommunicationValidationError("Categoria não encontrada.")
    return {
        "name": name,
        "channel": channel,
        "body": body,
        "subject": str(payload.get("assunto", "")).strip() or None,
        "category_id": category_uuid,
        "active": payload.get("ativa", True) is not False,
    }


def _channel_message_data(item: ChannelMessage) -> dict:
    return {
        "id": str(item.id),
        "canal": item.channel.value,
        "status": item.status.value,
        "remetenteNome": item.sender_name,
        "remetenteContato": item.sender_contact,
        "assunto": item.subject,
        "conteudo": item.content,
        "idExterno": item.external_id,
        "metadados": _safe_channel_metadata(item.metadata_data),
        "solicitacaoId": str(item.request_id) if item.request_id else None,
        "recebidaEm": item.received_at.isoformat(),
        "revisadaEm": item.reviewed_at.isoformat() if item.reviewed_at else None,
    }


def _safe_channel_metadata(value: dict | None) -> dict:
    metadata = value if isinstance(value, dict) else {}
    allowed = {
        "provider",
        "eventType",
        "messageType",
        "phoneNumberId",
        "displayPhoneNumber",
        "timestamp",
        "messageId",
    }
    result = {key: metadata[key] for key in allowed if metadata.get(key) is not None}
    attachments = metadata.get("attachments")
    if isinstance(attachments, list):
        result["attachments"] = [
            {
                key: attachment.get(key)
                for key in ("id", "filename", "contentType", "size")
                if attachment.get(key) is not None
            }
            for attachment in attachments[:20]
            if isinstance(attachment, dict)
        ]
    return result


def _masked_contact(value: str | None) -> str | None:
    contact = str(value or "").strip()
    if not contact:
        return None
    if "@" in contact:
        local, domain = contact.rsplit("@", 1)
        return f"{local[:1]}***@{domain}"
    digits = "".join(character for character in contact if character.isdigit())
    return f"***{digits[-4:]}" if digits else "***"


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _identity_review_data(review: ChannelIdentityReview) -> dict:
    candidate_ids = parse_candidate_ids(review)
    candidates = []
    if candidate_ids:
        candidates = db.session.execute(
            select(Citizen).where(
                Citizen.tenant_id == review.tenant_id,
                Citizen.id.in_(candidate_ids),
                Citizen.anonymized_at.is_(None),
            )
        ).scalars()
    message = review.message
    due_at = _as_utc(review.due_at)
    return {
        "id": str(review.id),
        "status": review.status.value,
        "estadoResolucao": review.resolution_state,
        "criterios": review.match_basis,
        "mensagem": {
            "id": str(message.id),
            "canal": message.channel.value,
            "remetenteNome": message.sender_name,
            "remetenteContatoMascarado": _masked_contact(message.sender_contact),
            "assunto": message.subject,
            "conteudo": message.content,
            "recebidaEm": message.received_at.isoformat(),
        },
        "candidatos": [
            {
                "id": str(citizen.id),
                "nome": citizen.name,
                "nomeSocial": citizen.social_name,
                "vip": citizen.vip,
            }
            for citizen in candidates
        ],
        "cidadaoSelecionadoId": (
            str(review.selected_citizen_id) if review.selected_citizen_id else None
        ),
        "responsavelId": str(review.assigned_to_id) if review.assigned_to_id else None,
        "responsavel": review.assigned_to.name if review.assigned_to else None,
        "prazoEm": due_at.isoformat() if due_at else None,
        "vencida": bool(
            review.status == ChannelIdentityReviewStatus.PENDENTE
            and due_at
            and due_at < datetime.now(UTC)
        ),
        "tipoDecisao": review.decision_type,
        "reaberturas": review.reopened_count,
        "revisadoPor": review.reviewed_by.name if review.reviewed_by else None,
        "observacao": review.review_note,
        "criadaEm": review.created_at.isoformat(),
        "revisadaEm": review.reviewed_at.isoformat() if review.reviewed_at else None,
    }


def _channel_from_payload(value) -> RequestSource:
    try:
        channel = RequestSource(str(value or "").upper())
    except ValueError:
        raise CommunicationValidationError("Canal inválido.") from None
    if channel not in {RequestSource.WHATSAPP, RequestSource.EMAIL, RequestSource.REDE_SOCIAL}:
        raise CommunicationValidationError("Canal não suportado pela caixa de entrada.")
    return channel


@communications_bp.get("/canais/mensagens")
@jwt_required()
def list_channel_messages():
    tenant_id, _ = _context()
    filters = [ChannelMessage.tenant_id == tenant_id]
    status = request.args.get("status")
    channel = request.args.get("canal")
    if status:
        try:
            filters.append(ChannelMessage.status == ChannelMessageStatus(status.upper()))
        except ValueError:
            return jsonify(error="validation_error", message="Status inválido."), 422
    if channel:
        try:
            filters.append(ChannelMessage.channel == _channel_from_payload(channel))
        except CommunicationValidationError as error:
            return jsonify(error="validation_error", message=str(error)), 422
    items = db.session.execute(
        select(ChannelMessage).where(*filters).order_by(ChannelMessage.received_at.desc())
    ).scalars()
    return jsonify(content=[_channel_message_data(item) for item in items])


@communications_bp.get("/canais/revisoes-identidade")
@roles_required("admin", "manager", "staff")
def list_channel_identity_reviews():
    tenant_id, _ = _context()
    filters = [ChannelIdentityReview.tenant_id == tenant_id]
    status = request.args.get("status", "PENDENTE")
    channel = request.args.get("canal")
    assignee_id = request.args.get("responsavelId")
    overdue = request.args.get("vencida")
    if status:
        try:
            filters.append(
                ChannelIdentityReview.status == ChannelIdentityReviewStatus(status.upper())
            )
        except ValueError:
            return jsonify(error="validation_error", message="Status inválido."), 422
    query = (
        select(ChannelIdentityReview)
        .join(
            ChannelMessage,
            (ChannelMessage.id == ChannelIdentityReview.message_id)
            & (ChannelMessage.tenant_id == ChannelIdentityReview.tenant_id),
        )
        .where(*filters)
        .order_by(ChannelIdentityReview.created_at.desc())
        .limit(100)
    )
    if channel:
        try:
            query = query.where(ChannelMessage.channel == _channel_from_payload(channel))
        except CommunicationValidationError as error:
            return jsonify(error="validation_error", message=str(error)), 422
    if assignee_id:
        if assignee_id == "SEM_RESPONSAVEL":
            query = query.where(ChannelIdentityReview.assigned_to_id.is_(None))
        else:
            try:
                query = query.where(ChannelIdentityReview.assigned_to_id == uuid.UUID(assignee_id))
            except ValueError:
                return jsonify(error="validation_error", message="Responsável inválido."), 422
    if overdue == "true":
        query = query.where(ChannelIdentityReview.due_at < datetime.now(UTC))
    items = db.session.execute(query).scalars().all()
    counts = dict(
        db.session.execute(
            select(ChannelIdentityReview.status, func.count(ChannelIdentityReview.id))
            .where(ChannelIdentityReview.tenant_id == tenant_id)
            .group_by(ChannelIdentityReview.status)
        ).all()
    )
    users = db.session.execute(
        select(User)
        .where(User.tenant_id == tenant_id, User.status == UserStatus.ACTIVE)
        .order_by(User.name)
    ).scalars()
    overdue_count = db.session.execute(
        select(func.count(ChannelIdentityReview.id)).where(
            ChannelIdentityReview.tenant_id == tenant_id,
            ChannelIdentityReview.status == ChannelIdentityReviewStatus.PENDENTE,
            ChannelIdentityReview.due_at < datetime.now(UTC),
        )
    ).scalar_one()
    return jsonify(
        content=[_identity_review_data(item) for item in items],
        resumo={
            "pendentes": counts.get(ChannelIdentityReviewStatus.PENDENTE, 0),
            "vinculadas": counts.get(ChannelIdentityReviewStatus.VINCULADA, 0),
            "descartadas": counts.get(ChannelIdentityReviewStatus.DESCARTADA, 0),
            "vencidas": overdue_count,
        },
        responsaveis=[{"id": str(user.id), "nome": user.name} for user in users],
    )


@communications_bp.get("/canais/configuracao-cadastro-assistido")
@jwt_required()
def get_channel_assisted_settings():
    tenant_id, _ = _context()
    return jsonify(assisted_settings_data(get_assisted_settings(tenant_id)))


@communications_bp.put("/canais/configuracao-cadastro-assistido")
@roles_required("admin", "manager")
def save_channel_assisted_settings():
    tenant_id, user_id = _context()
    payload = request.get_json(silent=True) or {}
    legal_basis = str(payload.get("baseLegalPadrao", "")).strip() or None
    allowed_legal_basis = {"EXECUCAO_POLITICA_PUBLICA", "CONSENTIMENTO", "LEGITIMO_INTERESSE"}
    try:
        sla_hours = int(payload.get("slaHoras", 24))
        retention_days = int(payload.get("retencaoDias", 365))
    except (TypeError, ValueError):
        return jsonify(error="validation_error", message="Configuração inválida."), 422
    if legal_basis not in allowed_legal_basis | {None}:
        return jsonify(error="validation_error", message="Base legal inválida."), 422
    if not 1 <= sla_hours <= 720 or not 30 <= retention_days <= 3650:
        return jsonify(error="validation_error", message="SLA ou retenção inválidos."), 422
    item = get_assisted_settings(tenant_id)
    before = assisted_settings_data(item)
    if item is None:
        item = ChannelAssistedSetting(tenant_id=tenant_id)
        db.session.add(item)
    item.default_legal_basis = legal_basis
    item.sla_hours = sla_hours
    item.retention_days = retention_days
    item.updated_by_id = user_id
    after = assisted_settings_data(item)
    add_audit(
        tenant_id,
        user_id,
        "channel.assisted_settings.updated",
        "channel_assisted_setting",
        item.id,
        before=before,
        after=after,
    )
    db.session.commit()
    return jsonify(assisted_settings_data(item))


@communications_bp.put("/canais/revisoes-identidade/<uuid:review_id>/atribuicao")
@roles_required("admin", "manager", "staff")
def assign_channel_identity_review(review_id: uuid.UUID):
    tenant_id, user_id = _context()
    review = db.session.execute(
        select(ChannelIdentityReview)
        .where(
            ChannelIdentityReview.id == review_id,
            ChannelIdentityReview.tenant_id == tenant_id,
        )
        .with_for_update()
    ).scalar_one_or_none()
    if review is None:
        return jsonify(error="resource_not_found", message="Revisão não encontrada."), 404
    payload = request.get_json(silent=True) or {}
    assignee_id = payload.get("responsavelId")
    assignee = None
    if assignee_id:
        try:
            assignee_uuid = uuid.UUID(str(assignee_id))
        except ValueError:
            return jsonify(error="validation_error", message="Responsável inválido."), 422
        assignee = db.session.execute(
            select(User).where(
                User.id == assignee_uuid,
                User.tenant_id == tenant_id,
                User.status == UserStatus.ACTIVE,
            )
        ).scalar_one_or_none()
        if assignee is None:
            return jsonify(error="resource_not_found", message="Responsável não encontrado."), 404
    review.assigned_to_id = assignee.id if assignee else None
    add_audit(
        tenant_id,
        user_id,
        "channel.identity_review.assigned",
        "channel_identity_review",
        review.id,
        after={"responsavelId": str(assignee.id) if assignee else None},
    )
    db.session.commit()
    return jsonify(_identity_review_data(review))


@communications_bp.post("/canais/revisoes-identidade/<uuid:review_id>/reabrir")
@roles_required("admin", "manager")
def reopen_channel_identity_review(review_id: uuid.UUID):
    tenant_id, user_id = _context()
    review = db.session.execute(
        select(ChannelIdentityReview)
        .where(
            ChannelIdentityReview.id == review_id,
            ChannelIdentityReview.tenant_id == tenant_id,
        )
        .with_for_update()
    ).scalar_one_or_none()
    if review is None:
        return jsonify(error="resource_not_found", message="Revisão não encontrada."), 404
    if review.status == ChannelIdentityReviewStatus.PENDENTE:
        return jsonify(error="validation_error", message="Revisão já está pendente."), 422
    payload = request.get_json(silent=True) or {}
    note = str(payload.get("justificativa", "")).strip()
    if len(note) < 5 or len(note) > 500:
        return jsonify(error="validation_error", message="Informe a justificativa."), 422
    settings = get_assisted_settings(tenant_id)
    review.status = ChannelIdentityReviewStatus.PENDENTE
    review.selected_citizen_id = None
    review.reviewed_by_id = None
    review.reviewed_at = None
    review.review_note = note
    review.decision_type = "REABERTA"
    review.reopened_count += 1
    review.due_at = datetime.now(UTC) + timedelta(hours=settings.sla_hours if settings else 24)
    add_audit(
        tenant_id,
        user_id,
        "channel.identity_review.reopened",
        "channel_identity_review",
        review.id,
        after={"reaberturas": review.reopened_count},
    )
    db.session.commit()
    return jsonify(_identity_review_data(review))


@communications_bp.post("/canais/revisoes-identidade/<uuid:review_id>/preparar-cadastro")
@roles_required("admin", "manager", "staff")
def prepare_assisted_citizen_registration(review_id: uuid.UUID):
    tenant_id, user_id = _context()
    review = db.session.execute(
        select(ChannelIdentityReview)
        .where(
            ChannelIdentityReview.id == review_id,
            ChannelIdentityReview.tenant_id == tenant_id,
        )
        .with_for_update()
    ).scalar_one_or_none()
    if review is None:
        return jsonify(error="resource_not_found", message="Revisão não encontrada."), 404
    if review.status != ChannelIdentityReviewStatus.PENDENTE:
        return jsonify(error="validation_error", message="Revisão já concluída."), 422
    settings = get_assisted_settings(tenant_id)
    if settings is None or not settings.default_legal_basis:
        return (
            jsonify(
                error="configuration_required",
                code="BASE_LEGAL_PADRAO_OBRIGATORIA",
                message="Configure a base legal padrão do cadastro assistido.",
            ),
            409,
        )
    if review.assigned_to_id is None:
        review.assigned_to_id = user_id
    review.decision_type = "CADASTRO_EM_PREPARACAO"
    message = review.message
    contact = message.sender_contact or ""
    review_payload = {
        "revisaoId": str(review.id),
        "mensagemId": str(message.id),
        "canal": message.channel.value,
        "preenchimento": {
            "nome": message.sender_name or "",
            "telefone": contact if message.channel == RequestSource.WHATSAPP else "",
            "email": contact if message.channel == RequestSource.EMAIL else "",
            "canalPreferencial": message.channel.value,
            "baseLegal": settings.default_legal_basis,
        },
        "confirmacoesObrigatorias": ["nome", "contato", "baseLegal"],
        "aviso": "Confira cada campo. A mensagem não comprova identidade civil.",
    }
    add_audit(
        tenant_id,
        user_id,
        "channel.identity_review.registration_prepared",
        "channel_identity_review",
        review.id,
        after={"mensagemId": str(message.id)},
    )
    db.session.commit()
    return jsonify(review_payload)


@communications_bp.get("/canais/revisoes-identidade/metricas")
@roles_required("admin", "manager")
def channel_identity_review_metrics():
    tenant_id, _ = _context()
    reviews = (
        db.session.execute(
            select(ChannelIdentityReview).where(ChannelIdentityReview.tenant_id == tenant_id)
        )
        .scalars()
        .all()
    )
    completed = [item for item in reviews if item.reviewed_at]
    average_hours = (
        sum((item.reviewed_at - item.created_at).total_seconds() for item in completed)
        / len(completed)
        / 3600
        if completed
        else None
    )
    return jsonify(
        total=len(reviews),
        pendentes=sum(item.status == ChannelIdentityReviewStatus.PENDENTE for item in reviews),
        vinculadas=sum(item.status == ChannelIdentityReviewStatus.VINCULADA for item in reviews),
        descartadas=sum(item.status == ChannelIdentityReviewStatus.DESCARTADA for item in reviews),
        cadastrosManuais=sum(item.decision_type == "CADASTRO_MANUAL" for item in reviews),
        tempoMedioRevisaoHoras=round(average_hours, 2) if average_hours is not None else None,
    )


@communications_bp.post("/canais/revisoes-identidade/retencao/executar")
@roles_required("admin", "manager")
def execute_channel_message_retention():
    tenant_id, user_id = _context()
    settings = get_assisted_settings(tenant_id)
    retention_days = settings.retention_days if settings else 365
    cutoff = datetime.now(UTC) - timedelta(days=retention_days)
    messages = (
        db.session.execute(
            select(ChannelMessage)
            .join(
                ChannelIdentityReview,
                (ChannelIdentityReview.message_id == ChannelMessage.id)
                & (ChannelIdentityReview.tenant_id == ChannelMessage.tenant_id),
            )
            .where(
                ChannelMessage.tenant_id == tenant_id,
                ChannelMessage.redacted_at.is_(None),
                ChannelIdentityReview.status != ChannelIdentityReviewStatus.PENDENTE,
                ChannelIdentityReview.reviewed_at < cutoff,
            )
            .limit(500)
        )
        .scalars()
        .all()
    )
    for message in messages:
        message.sender_name = None
        message.sender_contact = None
        message.subject = None
        message.content = "[CONTEÚDO REMOVIDO POR POLÍTICA DE RETENÇÃO]"
        message.metadata_data = {}
        message.redacted_at = datetime.now(UTC)
    add_audit(
        tenant_id,
        user_id,
        "channel.message.retention_executed",
        "channel_message",
        None,
        after={"quantidade": len(messages), "retencaoDias": retention_days},
    )
    db.session.commit()
    return jsonify(processadas=len(messages), retencaoDias=retention_days)


@communications_bp.post("/canais/revisoes-identidade/<uuid:review_id>/decisao")
@roles_required("admin", "manager", "staff")
def decide_channel_identity_review(review_id: uuid.UUID):
    tenant_id, user_id = _context()
    review = db.session.execute(
        select(ChannelIdentityReview)
        .where(
            ChannelIdentityReview.id == review_id,
            ChannelIdentityReview.tenant_id == tenant_id,
        )
        .with_for_update()
    ).scalar_one_or_none()
    if review is None:
        return jsonify(error="resource_not_found", message="Revisão não encontrada."), 404
    if review.status != ChannelIdentityReviewStatus.PENDENTE:
        return jsonify(error="validation_error", message="Revisão já concluída."), 422

    payload = request.get_json(silent=True) or {}
    decision = str(payload.get("decisao", "")).upper()
    note = str(payload.get("observacao", "")).strip() or None
    if note and len(note) > 500:
        return jsonify(error="validation_error", message="Observação excede 500 caracteres."), 422
    citizen = None
    if decision == "VINCULAR":
        try:
            citizen_id = uuid.UUID(str(payload.get("cidadaoId")))
        except (TypeError, ValueError):
            return jsonify(error="validation_error", message="Selecione um cidadão."), 422
        citizen = db.session.execute(
            select(Citizen).where(
                Citizen.id == citizen_id,
                Citizen.tenant_id == tenant_id,
                Citizen.anonymized_at.is_(None),
            )
        ).scalar_one_or_none()
        if citizen is None:
            return jsonify(error="resource_not_found", message="Cidadão não encontrado."), 404
        review.status = ChannelIdentityReviewStatus.VINCULADA
        review.selected_citizen_id = citizen.id
        review.decision_type = "VINCULO_EXISTENTE"
        whatsapp_contact = db.session.execute(
            select(WhatsAppContact)
            .join(
                WhatsAppConversation,
                (WhatsAppConversation.tenant_id == WhatsAppContact.tenant_id)
                & (WhatsAppConversation.contact_id == WhatsAppContact.id),
            )
            .join(
                WhatsAppMessage,
                (WhatsAppMessage.tenant_id == WhatsAppConversation.tenant_id)
                & (WhatsAppMessage.conversation_id == WhatsAppConversation.id),
            )
            .where(
                WhatsAppContact.tenant_id == tenant_id,
                WhatsAppMessage.channel_message_id == review.message_id,
            )
        ).scalar_one_or_none()
        if whatsapp_contact is not None:
            whatsapp_contact.citizen_id = citizen.id
    elif decision == "DESCARTAR":
        review.status = ChannelIdentityReviewStatus.DESCARTADA
        review.selected_citizen_id = None
        review.decision_type = "DESCARTADA"
    else:
        return (
            jsonify(
                error="validation_error",
                message="Decisão deve ser VINCULAR ou DESCARTAR.",
            ),
            422,
        )
    review.reviewed_by_id = user_id
    review.reviewed_at = datetime.now(UTC)
    review.review_note = note
    add_audit(
        tenant_id,
        user_id,
        "channel.identity_review.decided",
        "channel_identity_review",
        review.id,
        after={
            "decisao": review.status.value,
            "mensagemId": str(review.message_id),
            "cidadaoId": str(citizen.id) if citizen else None,
        },
    )
    db.session.commit()
    return jsonify(_identity_review_data(review))


@communications_bp.post("/canais/mensagens")
@roles_required("admin", "manager", "staff")
def create_channel_message():
    tenant_id, user_id = _context()
    payload = request.get_json(silent=True) or {}
    try:
        channel = _channel_from_payload(payload.get("canal"))
    except CommunicationValidationError as error:
        return jsonify(error="validation_error", message=str(error)), 422
    item, error_response = _create_channel_message(
        tenant_id,
        channel,
        payload,
        reviewed_by_id=user_id,
    )
    if error_response:
        return error_response
    add_audit(
        tenant_id,
        user_id,
        "channel.message.received",
        "channel_message",
        item.id,
        after={"canal": item.channel.value, "status": item.status.value},
    )
    db.session.commit()
    return jsonify(_channel_message_data(item)), 201


@communications_bp.post("/canais/webhooks/<tenant_slug>/<channel>")
@limiter.limit("30 per minute")
def receive_channel_webhook(tenant_slug: str, channel: str):
    tenant = db.session.execute(
        select(Tenant).where(Tenant.slug == tenant_slug)
    ).scalar_one_or_none()
    if tenant is None:
        return jsonify(error="resource_not_found", message="Tenant não encontrado."), 404
    try:
        source = _channel_from_payload(channel)
    except CommunicationValidationError as error:
        return jsonify(error="validation_error", message=str(error)), 422
    integration_type = {
        RequestSource.WHATSAPP: IntegrationType.WHATSAPP,
        RequestSource.EMAIL: IntegrationType.EMAIL,
        RequestSource.REDE_SOCIAL: IntegrationType.REDE_SOCIAL,
    }[source]
    integration = db.session.execute(
        select(IntegrationSetting).where(
            IntegrationSetting.tenant_id == tenant.id,
            IntegrationSetting.integration_type == integration_type,
            IntegrationSetting.status == IntegrationStatus.ATIVA,
        )
    ).scalar_one_or_none()
    if integration is None:
        return jsonify(error="validation_error", message="Integração inativa."), 422
    item, error_response = _create_channel_message(
        tenant.id,
        source,
        request.get_json(silent=True) or {},
        reviewed_by_id=None,
    )
    if error_response:
        return error_response
    add_audit(
        tenant.id,
        None,
        "channel.webhook.received",
        "channel_message",
        item.id,
        after={"canal": source.value, "idExterno": item.external_id},
    )
    db.session.commit()
    return jsonify(id=str(item.id), status=item.status.value), 202


@communications_bp.post("/canais/webhooks/<tenant_slug>/email/resend")
@limiter.limit("30 per minute")
def receive_resend_inbound_email(tenant_slug: str):
    tenant = db.session.execute(
        select(Tenant).where(Tenant.slug == tenant_slug)
    ).scalar_one_or_none()
    if tenant is None:
        return jsonify(error="resource_not_found", message="Tenant nÃ£o encontrado."), 404
    integration = db.session.execute(
        select(IntegrationSetting).where(
            IntegrationSetting.tenant_id == tenant.id,
            IntegrationSetting.integration_type == IntegrationType.EMAIL,
            IntegrationSetting.status == IntegrationStatus.ATIVA,
        )
    ).scalar_one_or_none()
    if integration is None:
        return jsonify(error="validation_error", message="IntegraÃ§Ã£o de e-mail inativa."), 422

    secret = current_app.config.get("RESEND_WEBHOOK_SECRET")
    if not secret:
        return jsonify(error="validation_error", message="Webhook Resend nÃ£o configurado."), 422

    try:
        event = verify_resend_webhook(
            request.get_data(cache=True),
            request.headers,
            secret,
            tolerance_seconds=current_app.config["RESEND_WEBHOOK_TOLERANCE_SECONDS"],
        )
    except WebhookVerificationError as error:
        return jsonify(error="invalid_signature", message=str(error)), 400

    if event.get("type") != "email.received":
        return jsonify(status="ignored", eventType=event.get("type")), 202

    data = event.get("data") if isinstance(event.get("data"), dict) else {}
    email_id = str(data.get("email_id") or data.get("id") or "").strip()
    if not email_id:
        return jsonify(error="validation_error", message="Evento sem identificador de e-mail."), 422

    existing = db.session.execute(
        select(ChannelMessage).where(
            ChannelMessage.tenant_id == tenant.id,
            ChannelMessage.channel == RequestSource.EMAIL,
            ChannelMessage.external_id == email_id,
        )
    ).scalar_one_or_none()
    if existing is not None:
        return (
            jsonify(id=str(existing.id), status=existing.status.value, duplicado=True),
            200,
        )

    received_email = retrieve_received_email(email_id) or {}
    subject = str(received_email.get("subject") or data.get("subject") or "").strip() or None
    sender = _first_email_value(received_email.get("from") or data.get("from"))
    content = _resend_email_content(received_email, data)
    metadata = {
        "provider": "resend",
        "eventType": event.get("type"),
        "emailId": email_id,
        "messageId": data.get("message_id") or received_email.get("message_id"),
        "to": received_email.get("to") or data.get("to"),
        "cc": received_email.get("cc") or data.get("cc"),
        "bcc": received_email.get("bcc") or data.get("bcc"),
        "attachments": [
            {
                "id": attachment.get("id"),
                "filename": attachment.get("filename"),
                "contentType": attachment.get("content_type"),
                "size": attachment.get("size"),
            }
            for attachment in received_email.get("attachments", [])
            if isinstance(attachment, dict)
        ],
    }
    item = ChannelMessage(
        tenant_id=tenant.id,
        channel=RequestSource.EMAIL,
        status=ChannelMessageStatus.RECEBIDA,
        sender_name=sender,
        sender_contact=sender,
        subject=subject,
        content=content,
        external_id=email_id,
        metadata_data={key: value for key, value in metadata.items() if value},
    )
    db.session.add(item)
    db.session.flush()
    prepare_identity_review(item)
    add_audit(
        tenant.id,
        None,
        "channel.email.resend.received",
        "channel_message",
        item.id,
        after={"canal": RequestSource.EMAIL.value, "idExterno": item.external_id},
    )
    db.session.commit()
    return jsonify(id=str(item.id), status=item.status.value), 202


@communications_bp.get("/canais/webhooks/<tenant_slug>/whatsapp/meta")
@limiter.limit("30 per minute")
def verify_whatsapp_webhook(tenant_slug: str):
    if current_app.config.get("WHATSAPP_PLATFORM_ENABLED"):
        return jsonify(error="global_webhook_required"), 410
    tenant = db.session.execute(
        select(Tenant).where(Tenant.slug == tenant_slug)
    ).scalar_one_or_none()
    if tenant is None:
        return jsonify(error="resource_not_found", message="Tenant nÃ£o encontrado."), 404
    integration = _active_integration(tenant.id, IntegrationType.WHATSAPP)
    if integration is None:
        return jsonify(error="validation_error", message="IntegraÃ§Ã£o WhatsApp inativa."), 422

    verify_token = current_app.config.get("WHATSAPP_WEBHOOK_VERIFY_TOKEN")
    mode = request.args.get("hub.mode")
    challenge = request.args.get("hub.challenge")
    if not verify_token:
        return jsonify(error="validation_error", message="Webhook WhatsApp nÃ£o configurado."), 422
    if mode == "subscribe" and request.args.get("hub.verify_token") == verify_token and challenge:
        return challenge, 200, {"Content-Type": "text/plain"}
    return jsonify(error="invalid_token", message="Token de verificaÃ§Ã£o invÃ¡lido."), 403


@communications_bp.post("/canais/webhooks/<tenant_slug>/whatsapp/meta")
@limiter.limit("30 per minute")
def receive_whatsapp_business_webhook(tenant_slug: str):
    if current_app.config.get("WHATSAPP_PLATFORM_ENABLED"):
        return jsonify(error="global_webhook_required"), 410
    tenant = db.session.execute(
        select(Tenant).where(Tenant.slug == tenant_slug)
    ).scalar_one_or_none()
    if tenant is None:
        return jsonify(error="resource_not_found", message="Tenant nÃ£o encontrado."), 404
    integration = _active_integration(tenant.id, IntegrationType.WHATSAPP)
    if integration is None:
        return jsonify(error="validation_error", message="IntegraÃ§Ã£o WhatsApp inativa."), 422

    app_secret = current_app.config.get("META_APP_SECRET")
    if not app_secret:
        return jsonify(error="validation_error", message="Webhook WhatsApp nÃ£o configurado."), 422

    raw_body = request.get_data(cache=True)
    try:
        verify_meta_signature(raw_body, request.headers.get("X-Hub-Signature-256"), app_secret)
    except WhatsAppWebhookError as error:
        return jsonify(error="invalid_signature", message=str(error)), 400

    payload = request.get_json(silent=True) or {}
    expected_phone_number_id = str(integration.config.get("phoneNumberId") or "").strip()
    items = []
    duplicated = 0
    for message in extract_whatsapp_messages(payload):
        if (
            expected_phone_number_id
            and str(message.get("phoneNumberId") or "") != expected_phone_number_id
        ):
            continue
        existing = db.session.execute(
            select(ChannelMessage).where(
                ChannelMessage.tenant_id == tenant.id,
                ChannelMessage.channel == RequestSource.WHATSAPP,
                ChannelMessage.external_id == message["id"],
            )
        ).scalar_one_or_none()
        if existing is not None:
            duplicated += 1
            continue
        item = ChannelMessage(
            tenant_id=tenant.id,
            channel=RequestSource.WHATSAPP,
            status=ChannelMessageStatus.RECEBIDA,
            sender_name=message.get("senderName"),
            sender_contact=message.get("from"),
            subject="WhatsApp Business",
            content=message["content"],
            external_id=message["id"],
            metadata_data={
                "provider": "meta_whatsapp_cloud_api",
                "messageType": message.get("type"),
                "phoneNumberId": message.get("phoneNumberId"),
                "displayPhoneNumber": message.get("displayPhoneNumber"),
                "timestamp": message.get("timestamp"),
                "raw": message.get("raw"),
            },
        )
        db.session.add(item)
        db.session.flush()
        prepare_identity_review(item)
        add_audit(
            tenant.id,
            None,
            "channel.whatsapp.meta.received",
            "channel_message",
            item.id,
            after={"canal": RequestSource.WHATSAPP.value, "idExterno": item.external_id},
        )
        items.append(item)

    if items:
        db.session.commit()
    else:
        db.session.rollback()
    return jsonify(recebidas=len(items), duplicadas=duplicated), 202


@communications_bp.get("/canais/webhooks/<tenant_slug>/redes-sociais/meta")
@limiter.limit("30 per minute")
def verify_meta_social_webhook(tenant_slug: str):
    tenant = db.session.execute(
        select(Tenant).where(Tenant.slug == tenant_slug)
    ).scalar_one_or_none()
    if tenant is None:
        return jsonify(error="resource_not_found", message="Tenant nÃ£o encontrado."), 404
    integration = _active_integration(tenant.id, IntegrationType.REDE_SOCIAL)
    if integration is None:
        return (
            jsonify(error="validation_error", message="IntegraÃ§Ã£o de redes sociais inativa."),
            422,
        )

    verify_token = current_app.config.get("META_WEBHOOK_VERIFY_TOKEN")
    mode = request.args.get("hub.mode")
    challenge = request.args.get("hub.challenge")
    if not verify_token:
        return jsonify(error="validation_error", message="Webhook Meta nÃ£o configurado."), 422
    if mode == "subscribe" and request.args.get("hub.verify_token") == verify_token and challenge:
        return challenge, 200, {"Content-Type": "text/plain"}
    return jsonify(error="invalid_token", message="Token de verificaÃ§Ã£o invÃ¡lido."), 403


@communications_bp.post("/canais/webhooks/<tenant_slug>/redes-sociais/meta")
@limiter.limit("30 per minute")
def receive_meta_social_webhook(tenant_slug: str):
    tenant = db.session.execute(
        select(Tenant).where(Tenant.slug == tenant_slug)
    ).scalar_one_or_none()
    if tenant is None:
        return jsonify(error="resource_not_found", message="Tenant nÃ£o encontrado."), 404
    integration = _active_integration(tenant.id, IntegrationType.REDE_SOCIAL)
    if integration is None:
        return (
            jsonify(error="validation_error", message="IntegraÃ§Ã£o de redes sociais inativa."),
            422,
        )

    app_secret = current_app.config.get("META_APP_SECRET")
    if not app_secret:
        return jsonify(error="validation_error", message="Webhook Meta nÃ£o configurado."), 422

    raw_body = request.get_data(cache=True)
    try:
        verify_meta_signature(raw_body, request.headers.get("X-Hub-Signature-256"), app_secret)
    except WhatsAppWebhookError as error:
        return jsonify(error="invalid_signature", message=str(error)), 400

    payload = request.get_json(silent=True) or {}
    allowed_platforms = {
        str(platform).upper()
        for platform in integration.config.get("plataformas", ["FACEBOOK", "INSTAGRAM"])
    }
    items = []
    duplicated = 0
    for event in extract_meta_social_events(payload):
        if event["platform"] not in allowed_platforms:
            continue
        existing = db.session.execute(
            select(ChannelMessage).where(
                ChannelMessage.tenant_id == tenant.id,
                ChannelMessage.channel == RequestSource.REDE_SOCIAL,
                ChannelMessage.external_id == event["id"],
            )
        ).scalar_one_or_none()
        if existing is not None:
            duplicated += 1
            continue
        item = ChannelMessage(
            tenant_id=tenant.id,
            channel=RequestSource.REDE_SOCIAL,
            status=ChannelMessageStatus.RECEBIDA,
            sender_name=event.get("senderName"),
            sender_contact=event.get("senderId"),
            subject=f"{event['platform']} - {event['eventType']}",
            content=event["content"],
            external_id=event["id"],
            metadata_data={
                "provider": "meta_social_webhooks",
                "platform": event.get("platform"),
                "eventType": event.get("eventType"),
                "recipientId": event.get("recipientId"),
                "timestamp": event.get("timestamp"),
                "raw": event.get("raw"),
            },
        )
        db.session.add(item)
        db.session.flush()
        add_audit(
            tenant.id,
            None,
            "channel.social.meta.received",
            "channel_message",
            item.id,
            after={"canal": RequestSource.REDE_SOCIAL.value, "idExterno": item.external_id},
        )
        items.append(item)

    if items:
        db.session.commit()
    else:
        db.session.rollback()
    return jsonify(recebidas=len(items), duplicadas=duplicated), 202


@communications_bp.post("/canais/mensagens/<uuid:message_id>/solicitacao")
@roles_required("admin", "manager", "staff")
def convert_channel_message(message_id: uuid.UUID):
    tenant_id, user_id = _context()
    item = db.session.execute(
        select(ChannelMessage).where(
            ChannelMessage.id == message_id,
            ChannelMessage.tenant_id == tenant_id,
        )
    ).scalar_one_or_none()
    if item is None:
        return jsonify(error="resource_not_found", message="Mensagem não encontrada."), 404
    if item.status != ChannelMessageStatus.RECEBIDA:
        return jsonify(error="validation_error", message="Mensagem já revisada."), 422
    payload = request.get_json(silent=True) or {}
    title = str(
        payload.get("titulo") or item.subject or f"Mensagem via {item.channel.value}"
    ).strip()
    description = str(payload.get("descricao") or item.content).strip()
    if len(title) < 3 or len(description) < 10:
        return jsonify(error="validation_error", message="Informe título e descrição."), 422
    identity_review = db.session.execute(
        select(ChannelIdentityReview).where(
            ChannelIdentityReview.tenant_id == tenant_id,
            ChannelIdentityReview.message_id == item.id,
            ChannelIdentityReview.status == ChannelIdentityReviewStatus.VINCULADA,
        )
    ).scalar_one_or_none()
    service_request = ServiceRequest(
        tenant_id=tenant_id,
        created_by_id=user_id,
        citizen_id=identity_review.selected_citizen_id if identity_review else None,
        protocol=next_protocol(tenant_id),
        source=item.channel,
        title=title,
        description=description,
    )
    db.session.add(service_request)
    db.session.flush()
    item.status = ChannelMessageStatus.CONVERTIDA
    item.request_id = service_request.id
    item.reviewed_by_id = user_id
    item.reviewed_at = datetime.now(UTC)
    db.session.add(creation_event(service_request))
    add_audit(
        tenant_id,
        user_id,
        "channel.message.converted",
        "channel_message",
        item.id,
        after={"solicitacaoId": str(service_request.id), "protocolo": service_request.protocol},
    )
    db.session.commit()
    return jsonify(id=str(service_request.id), protocolo=service_request.protocol), 201


@communications_bp.patch("/canais/mensagens/<uuid:message_id>")
@roles_required("admin", "manager", "staff")
def update_channel_message(message_id: uuid.UUID):
    tenant_id, user_id = _context()
    item = db.session.execute(
        select(ChannelMessage).where(
            ChannelMessage.id == message_id,
            ChannelMessage.tenant_id == tenant_id,
        )
    ).scalar_one_or_none()
    if item is None:
        return jsonify(error="resource_not_found", message="Mensagem não encontrada."), 404
    payload = request.get_json(silent=True) or {}
    before = {"status": item.status.value}
    if "status" in payload:
        try:
            item.status = ChannelMessageStatus(str(payload["status"]).upper())
        except ValueError:
            return jsonify(error="validation_error", message="Status inválido."), 422
        item.reviewed_by_id = user_id
        item.reviewed_at = datetime.now(UTC)
    after = {"status": item.status.value}
    add_audit(
        tenant_id,
        user_id,
        "channel.message.updated",
        "channel_message",
        item.id,
        before,
        after,
    )
    db.session.commit()
    return jsonify(after)


@communications_bp.get("/publico/formularios/<tenant_slug>")
@limiter.limit("60 per minute")
def public_form_config(tenant_slug: str):
    tenant = db.session.execute(
        select(Tenant).where(Tenant.slug == tenant_slug)
    ).scalar_one_or_none()
    if tenant is None:
        return jsonify(error="resource_not_found", message="Tenant não encontrado."), 404
    integration = db.session.execute(
        select(IntegrationSetting).where(
            IntegrationSetting.tenant_id == tenant.id,
            IntegrationSetting.integration_type == IntegrationType.FORMULARIO_PUBLICO,
            IntegrationSetting.status == IntegrationStatus.ATIVA,
        )
    ).scalar_one_or_none()
    return jsonify(
        tenant=tenant.slug,
        nome=tenant.name,
        ativo=integration is not None,
        campos=["nome", "contato", "titulo", "descricao", "endereco"],
        jurisdicao={
            "municipio": tenant.jurisdiction_city,
            "uf": tenant.jurisdiction_state,
            "limites": tenant.jurisdiction_bounds,
        },
    )


@communications_bp.post("/publico/formularios/<tenant_slug>/solicitacoes")
@limiter.limit("10 per minute")
def submit_public_request(tenant_slug: str):
    tenant = db.session.execute(
        select(Tenant).where(Tenant.slug == tenant_slug)
    ).scalar_one_or_none()
    if tenant is None:
        return jsonify(error="resource_not_found", message="Tenant não encontrado."), 404
    integration = db.session.execute(
        select(IntegrationSetting).where(
            IntegrationSetting.tenant_id == tenant.id,
            IntegrationSetting.integration_type == IntegrationType.FORMULARIO_PUBLICO,
            IntegrationSetting.status == IntegrationStatus.ATIVA,
        )
    ).scalar_one_or_none()
    if integration is None:
        return jsonify(error="validation_error", message="Formulário público inativo."), 422
    payload = request.get_json(silent=True) or {}
    title = str(payload.get("titulo", "")).strip()
    description = str(payload.get("descricao", "")).strip()
    if len(title) < 3 or len(description) < 10:
        return jsonify(error="validation_error", message="Informe título e descrição."), 422
    try:
        receiver_user_id = _tenant_receiver_user_id(tenant.id)
    except CommunicationValidationError as error:
        return jsonify(error="validation_error", message=str(error)), 422
    service_request = ServiceRequest(
        tenant_id=tenant.id,
        created_by_id=receiver_user_id,
        protocol=next_protocol(tenant.id),
        source=RequestSource.FORMULARIO,
        title=title,
        description=description,
        address=str(payload.get("endereco", "")).strip() or None,
    )
    db.session.add(service_request)
    db.session.flush()
    db.session.add(creation_event(service_request))
    message = ChannelMessage(
        tenant_id=tenant.id,
        channel=RequestSource.FORMULARIO,
        status=ChannelMessageStatus.CONVERTIDA,
        sender_name=str(payload.get("nome", "")).strip() or None,
        sender_contact=str(payload.get("contato", "")).strip() or None,
        subject=title,
        content=description,
        metadata_data={"origem": "formulario_publico"},
        request_id=service_request.id,
        reviewed_at=datetime.now(UTC),
    )
    db.session.add(message)
    add_audit(
        tenant.id,
        None,
        "public_form.request.created",
        "service_request",
        service_request.id,
        after={"protocolo": service_request.protocol, "mensagemId": str(message.id)},
    )
    db.session.commit()
    return jsonify(id=str(service_request.id), protocolo=service_request.protocol), 201


def _tenant_receiver_user_id(tenant_id: uuid.UUID) -> uuid.UUID:
    user = (
        db.session.execute(
            select(User)
            .where(User.tenant_id == tenant_id, User.status == UserStatus.ACTIVE)
            .order_by(User.created_at)
        )
        .scalars()
        .first()
    )
    if user is None:
        raise CommunicationValidationError("Tenant não possui usuário ativo para receber demandas.")
    return user.id


def _active_integration(tenant_id: uuid.UUID, integration_type: IntegrationType):
    return db.session.execute(
        select(IntegrationSetting).where(
            IntegrationSetting.tenant_id == tenant_id,
            IntegrationSetting.integration_type == integration_type,
            IntegrationSetting.status == IntegrationStatus.ATIVA,
        )
    ).scalar_one_or_none()


def _create_channel_message(
    tenant_id: uuid.UUID,
    channel: RequestSource,
    payload: dict,
    *,
    reviewed_by_id: uuid.UUID | None,
) -> tuple[ChannelMessage | None, tuple | None]:
    content = str(payload.get("conteudo") or payload.get("mensagem") or "").strip()
    if len(content) < 3:
        return None, (jsonify(error="validation_error", message="Informe a mensagem."), 422)
    metadata = payload.get("metadados") or {}
    if not isinstance(metadata, dict):
        return None, (jsonify(error="validation_error", message="Metadados inválidos."), 422)
    external_id = str(payload.get("idExterno", "")).strip() or None
    if external_id:
        existing = db.session.execute(
            select(ChannelMessage).where(
                ChannelMessage.tenant_id == tenant_id,
                ChannelMessage.channel == channel,
                ChannelMessage.external_id == external_id,
            )
        ).scalar_one_or_none()
        if existing is not None:
            return existing, (
                jsonify(id=str(existing.id), status=existing.status.value, duplicado=True),
                200,
            )
    item = ChannelMessage(
        tenant_id=tenant_id,
        channel=channel,
        status=ChannelMessageStatus.RECEBIDA,
        sender_name=str(payload.get("remetenteNome", "")).strip() or None,
        sender_contact=str(payload.get("remetenteContato", "")).strip() or None,
        subject=str(payload.get("assunto", "")).strip() or None,
        content=content,
        external_id=external_id,
        metadata_data=metadata,
        reviewed_by_id=reviewed_by_id,
    )
    db.session.add(item)
    db.session.flush()
    prepare_identity_review(item)
    return item, None


class _HTMLTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        text = data.strip()
        if text:
            self.parts.append(text)

    def text(self) -> str:
        return " ".join(self.parts)


def _html_to_text(value) -> str:
    if not value:
        return ""
    parser = _HTMLTextExtractor()
    parser.feed(str(value))
    return parser.text()


def _first_email_value(value) -> str | None:
    if isinstance(value, list):
        value = value[0] if value else ""
    return str(value or "").strip() or None


def _resend_email_content(received_email: dict, data: dict) -> str:
    content = (
        received_email.get("text")
        or data.get("text")
        or _html_to_text(received_email.get("html") or data.get("html"))
        or received_email.get("subject")
        or data.get("subject")
        or "E-mail recebido sem corpo disponÃ­vel."
    )
    return str(content).strip()


@communications_bp.get("/admin/templates-resposta")
@roles_required("admin", "manager", "staff", "representative")
def list_templates():
    tenant_id, _ = _context()
    filters = [ResponseTemplate.tenant_id == tenant_id]
    channel = request.args.get("canal")
    category_id = request.args.get("categoriaId")
    if channel:
        filters.append(ResponseTemplate.channel == channel.upper())
    if category_id:
        try:
            filters.append(ResponseTemplate.category_id == uuid.UUID(category_id))
        except ValueError:
            return jsonify(error="validation_error", message="Categoria inválida."), 422
    items = db.session.execute(
        select(ResponseTemplate).where(*filters).order_by(ResponseTemplate.name)
    ).scalars()
    return jsonify(content=[template_data(item) for item in items])


@communications_bp.post("/admin/templates-resposta")
@roles_required("admin")
def create_template():
    tenant_id, user_id = _context()
    try:
        values = _template_payload(request.get_json(silent=True) or {}, tenant_id)
    except (CommunicationValidationError, ValueError) as error:
        return jsonify(error="validation_error", message=str(error)), 422
    item = ResponseTemplate(tenant_id=tenant_id, created_by_id=user_id, **values)
    db.session.add(item)
    try:
        db.session.flush()
    except IntegrityError:
        db.session.rollback()
        return jsonify(error="conflict", message="Já existe um template com este nome."), 409
    add_audit(
        tenant_id,
        user_id,
        "response_template.created",
        "response_template",
        item.id,
        after=template_data(item),
    )
    db.session.commit()
    return jsonify(template_data(item)), 201


@communications_bp.patch("/admin/templates-resposta/<uuid:template_id>")
@roles_required("admin")
def update_template(template_id: uuid.UUID):
    tenant_id, user_id = _context()
    item = db.session.execute(
        select(ResponseTemplate).where(
            ResponseTemplate.id == template_id,
            ResponseTemplate.tenant_id == tenant_id,
        )
    ).scalar_one_or_none()
    if item is None:
        return jsonify(error="resource_not_found", message="Template não encontrado."), 404
    before = template_data(item)
    payload = request.get_json(silent=True) or {}
    merged = {
        "nome": payload.get("nome", item.name),
        "canal": payload.get("canal", item.channel),
        "conteudo": payload.get("conteudo", item.body),
        "assunto": payload.get("assunto", item.subject),
        "categoriaId": payload.get(
            "categoriaId", str(item.category_id) if item.category_id else None
        ),
        "ativa": payload.get("ativa", item.active),
    }
    try:
        values = _template_payload(merged, tenant_id)
    except (CommunicationValidationError, ValueError) as error:
        return jsonify(error="validation_error", message=str(error)), 422
    for field, value in values.items():
        setattr(item, field, value)
    item.version += 1
    try:
        db.session.flush()
    except IntegrityError:
        db.session.rollback()
        return jsonify(error="conflict", message="Já existe um template com este nome."), 409
    add_audit(
        tenant_id,
        user_id,
        "response_template.updated",
        "response_template",
        item.id,
        before=before,
        after=template_data(item),
    )
    db.session.commit()
    return jsonify(template_data(item))


@communications_bp.delete("/admin/templates-resposta/<uuid:template_id>")
@roles_required("admin")
def delete_template(template_id: uuid.UUID):
    tenant_id, user_id = _context()
    item = db.session.execute(
        select(ResponseTemplate).where(
            ResponseTemplate.id == template_id,
            ResponseTemplate.tenant_id == tenant_id,
        )
    ).scalar_one_or_none()
    if item is None:
        return jsonify(error="resource_not_found", message="Template não encontrado."), 404
    before = template_data(item)
    item.active = False
    item.version += 1
    after = template_data(item)
    add_audit(
        tenant_id,
        user_id,
        "response_template.deactivated",
        "response_template",
        item.id,
        before=before,
        after=after,
    )
    db.session.commit()
    return jsonify(after)


@communications_bp.post("/solicitacoes/<uuid:request_id>/respostas/preview")
@jwt_required()
def preview_response(request_id: uuid.UUID):
    tenant_id, _ = _context()
    service_request = _service_request(request_id, tenant_id)
    template_id = (request.get_json(silent=True) or {}).get("templateId")
    if service_request is None:
        return jsonify(error="resource_not_found", message="Solicitação não encontrada."), 404
    try:
        template_uuid = uuid.UUID(template_id)
    except (TypeError, ValueError):
        return jsonify(error="validation_error", message="Template inválido."), 422
    template = db.session.execute(
        select(ResponseTemplate).where(
            ResponseTemplate.id == template_uuid,
            ResponseTemplate.tenant_id == tenant_id,
            ResponseTemplate.active.is_(True),
        )
    ).scalar_one_or_none()
    if template is None:
        return jsonify(error="resource_not_found", message="Template não encontrado."), 404
    return jsonify(
        templateId=str(template.id),
        canal=template.channel,
        assunto=template.subject,
        conteudo=render_template(template, service_request),
    )


@communications_bp.post("/solicitacoes/<uuid:request_id>/respostas")
@jwt_required()
def send_response(request_id: uuid.UUID):
    tenant_id, user_id = _context()
    service_request = _service_request(request_id, tenant_id)
    if service_request is None:
        return jsonify(error="resource_not_found", message="Solicitação não encontrada."), 404
    payload = request.get_json(silent=True) or {}
    content = str(payload.get("conteudo", "")).strip()
    channel = str(payload.get("canal", "")).upper().strip()
    subject = str(payload.get("assunto", "")).strip()
    if not content or channel not in ALLOWED_CHANNELS:
        return jsonify(error="validation_error", message="Informe canal e resposta."), 422
    template_id = payload.get("templateId")
    template = None
    if template_id:
        try:
            template = db.session.execute(
                select(ResponseTemplate).where(
                    ResponseTemplate.id == uuid.UUID(template_id),
                    ResponseTemplate.tenant_id == tenant_id,
                )
            ).scalar_one_or_none()
        except ValueError:
            template = None
        if template is None:
            return jsonify(error="validation_error", message="Template inválido."), 422
    destination = None
    if channel == "EMAIL":
        citizen = (
            db.session.get(Citizen, service_request.citizen_id)
            if service_request.citizen_id
            else None
        )
        destination = _citizen_email(citizen)
        subject = (
            subject
            or (template.subject if template else None)
            or (f"Atualização da solicitação {service_request.protocol}")
        )
        if destination is None:
            return (
                jsonify(
                    error="validation_error",
                    message="O cidadão não possui um e-mail cadastrado.",
                ),
                422,
            )
    interaction = RequestInteraction(
        tenant_id=tenant_id,
        request_id=service_request.id,
        interaction_type="RESPOSTA",
        channel=channel,
        direction=InteractionDirection.SAIDA,
        content=content,
        visibility=InteractionVisibility.CIDADAO,
        author_id=user_id,
    )
    db.session.add(interaction)
    db.session.flush()
    event = None
    if channel == "EMAIL":
        event = OutboxEvent(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            event_type=EMAIL_RESPONSE_EVENT,
            aggregate_type="Solicitacao",
            aggregate_id=str(service_request.id),
            payload={},
        )
        event.payload = {
            "requestId": str(service_request.id),
            "userId": str(user_id),
            "interactionId": str(interaction.id),
            "recipient": destination,
            "subject": subject,
            "text": content,
            "idempotencyKey": email_idempotency_key(event.id),
        }
        db.session.add(event)
    details = {
        "canal": channel,
        "assunto": subject or None,
        "templateId": str(template.id) if template else None,
        "templateVersao": template.version if template else None,
        "interacaoId": str(interaction.id),
        "eventoId": str(event.id) if event else None,
        "statusEntrega": "AGENDADO" if event else "REGISTRADO",
    }
    db.session.add(
        RequestHistory(
            tenant_id=tenant_id,
            request_id=service_request.id,
            user_id=user_id,
            action="request.response.queued" if event else "request.response.sent",
            changes=details,
        )
    )
    add_audit(
        tenant_id,
        user_id,
        "request.response.queued" if event else "request.response.sent",
        "service_request",
        service_request.id,
        after=details,
    )
    db.session.commit()
    return jsonify(id=str(interaction.id), **details), 202 if event else 201


def _citizen_email(citizen: Citizen | None) -> str | None:
    if citizen is None:
        return None
    for contact in citizen.contacts or []:
        if str(contact.get("tipo", "")).upper() == "EMAIL":
            value = str(contact.get("valor", "")).strip()
            if value:
                return value
    return None


def _valid_assignee(tenant_id: uuid.UUID, assignee_id) -> User | None:
    try:
        assignee_uuid = uuid.UUID(str(assignee_id))
    except (TypeError, ValueError):
        return None
    return db.session.execute(
        select(User).where(
            User.id == assignee_uuid,
            User.tenant_id == tenant_id,
            User.status == UserStatus.ACTIVE,
        )
    ).scalar_one_or_none()


@communications_bp.post("/solicitacoes/<uuid:request_id>/retornos")
@roles_required("admin", "manager", "staff")
def schedule_return(request_id: uuid.UUID):
    tenant_id, user_id = _context()
    service_request = _service_request(request_id, tenant_id)
    if service_request is None:
        return jsonify(error="resource_not_found", message="Solicitação não encontrada."), 404
    payload = request.get_json(silent=True) or {}
    tenant = db.session.get(Tenant, tenant_id)
    assignee = _valid_assignee(
        tenant_id, payload.get("responsavelId") or service_request.responsible_id or user_id
    )
    if assignee is None:
        return jsonify(error="validation_error", message="Responsável inválido."), 422
    try:
        scheduled_at = _parse_datetime(payload.get("agendadoPara"), tenant.timezone)
        reminder_minutes = int(payload.get("lembreteMinutos", 60))
    except (CommunicationValidationError, TypeError, ValueError) as error:
        return jsonify(error="validation_error", message=str(error)), 422
    if scheduled_at <= datetime.now(UTC):
        return jsonify(error="validation_error", message="Agende o retorno para o futuro."), 422
    if not 0 <= reminder_minutes <= 10080:
        return jsonify(error="validation_error", message="Lembrete deve ter até 7 dias."), 422
    item = ScheduledReturn(
        tenant_id=tenant_id,
        request_id=service_request.id,
        assignee_id=assignee.id,
        scheduled_at=scheduled_at,
        notes=str(payload.get("observacoes", "")).strip() or None,
        reminder_enabled=payload.get("lembreteHabilitado", True) is not False,
        reminder_minutes=reminder_minutes,
        created_by_id=user_id,
    )
    db.session.add(item)
    db.session.flush()
    data = scheduled_return_data(item)
    db.session.add(
        RequestHistory(
            tenant_id=tenant_id,
            request_id=service_request.id,
            user_id=user_id,
            action="request.return.scheduled",
            changes=data,
        )
    )
    add_audit(
        tenant_id,
        user_id,
        "request.return.scheduled",
        "scheduled_return",
        item.id,
        after=data,
    )
    db.session.commit()
    return jsonify(data), 201


@communications_bp.patch("/retornos/<uuid:return_id>")
@roles_required("admin", "manager", "staff")
def update_return(return_id: uuid.UUID):
    tenant_id, user_id = _context()
    item = db.session.execute(
        select(ScheduledReturn).where(
            ScheduledReturn.id == return_id,
            ScheduledReturn.tenant_id == tenant_id,
        )
    ).scalar_one_or_none()
    if item is None:
        return jsonify(error="resource_not_found", message="Retorno não encontrado."), 404
    payload = request.get_json(silent=True) or {}
    tenant = db.session.get(Tenant, tenant_id)
    before = scheduled_return_data(item)
    action = "updated"
    if "responsavelId" in payload:
        assignee = _valid_assignee(tenant_id, payload["responsavelId"])
        if assignee is None:
            return jsonify(error="validation_error", message="Responsável inválido."), 422
        item.assignee = assignee
    if "observacoes" in payload:
        item.notes = str(payload["observacoes"]).strip() or None
    if "lembreteHabilitado" in payload:
        item.reminder_enabled = payload["lembreteHabilitado"] is True
    if "lembreteMinutos" in payload:
        try:
            reminder_minutes = int(payload["lembreteMinutos"])
        except (TypeError, ValueError):
            return jsonify(error="validation_error", message="Lembrete inválido."), 422
        if not 0 <= reminder_minutes <= 10080:
            return jsonify(error="validation_error", message="Lembrete deve ter até 7 dias."), 422
        item.reminder_minutes = reminder_minutes
        item.reminder_sent_at = None
    if "agendadoPara" in payload:
        try:
            scheduled_at = _parse_datetime(payload["agendadoPara"], tenant.timezone)
        except CommunicationValidationError as error:
            return jsonify(error="validation_error", message=str(error)), 422
        if scheduled_at <= datetime.now(UTC):
            return jsonify(error="validation_error", message="Agende o retorno para o futuro."), 422
        item.scheduled_at = scheduled_at
        item.status = ScheduledReturnStatus.AGENDADO
        item.completed_at = None
        item.reminder_sent_at = None
        action = "rescheduled"
    if "status" in payload:
        try:
            status = ScheduledReturnStatus(str(payload["status"]).upper())
        except ValueError:
            return jsonify(error="validation_error", message="Status inválido."), 422
        item.status = status
        item.completed_at = datetime.now(UTC) if status == ScheduledReturnStatus.CONCLUIDO else None
        action = status.value.lower()
    db.session.flush()
    data = scheduled_return_data(item)
    history_action = f"request.return.{action}"
    db.session.add(
        RequestHistory(
            tenant_id=tenant_id,
            request_id=item.request_id,
            user_id=user_id,
            action=history_action,
            changes={"antes": before, "depois": data},
        )
    )
    add_audit(
        tenant_id,
        user_id,
        history_action,
        "scheduled_return",
        item.id,
        before=before,
        after=data,
    )
    db.session.commit()
    return jsonify(data)
