import uuid
from datetime import UTC, datetime
from html.parser import HTMLParser
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from flask import Blueprint, current_app, jsonify, request
from flask_jwt_extended import get_jwt, get_jwt_identity, jwt_required
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.audit import add_audit
from app.auth.permissions import roles_required
from app.communications.email import (
    WebhookVerificationError,
    email_idempotency_key,
    retrieve_received_email,
    verify_resend_webhook,
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
from app.extensions import db, limiter
from app.models import (
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
)
from app.outbox.handlers import EMAIL_RESPONSE_EVENT
from app.requests.service import creation_event, next_protocol

communications_bp = Blueprint("communications", __name__)


def _context() -> tuple[uuid.UUID, uuid.UUID]:
    return uuid.UUID(get_jwt()["tenant_id"]), uuid.UUID(get_jwt_identity())


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
            ServiceRequest.tenant_id == tenant_id,
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
        "metadados": item.metadata_data,
        "solicitacaoId": str(item.request_id) if item.request_id else None,
        "recebidaEm": item.received_at.isoformat(),
        "revisadaEm": item.reviewed_at.isoformat() if item.reviewed_at else None,
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
        after=_channel_message_data(item),
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
    service_request = ServiceRequest(
        tenant_id=tenant_id,
        created_by_id=user_id,
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
    before = _channel_message_data(item)
    if "status" in payload:
        try:
            item.status = ChannelMessageStatus(str(payload["status"]).upper())
        except ValueError:
            return jsonify(error="validation_error", message="Status inválido."), 422
        item.reviewed_by_id = user_id
        item.reviewed_at = datetime.now(UTC)
    after = _channel_message_data(item)
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
    user = db.session.execute(
        select(User)
        .where(User.tenant_id == tenant_id, User.status == UserStatus.ACTIVE)
        .order_by(User.created_at)
    ).scalars().first()
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
    item = ChannelMessage(
        tenant_id=tenant_id,
        channel=channel,
        status=ChannelMessageStatus.RECEBIDA,
        sender_name=str(payload.get("remetenteNome", "")).strip() or None,
        sender_contact=str(payload.get("remetenteContato", "")).strip() or None,
        subject=str(payload.get("assunto", "")).strip() or None,
        content=content,
        external_id=str(payload.get("idExterno", "")).strip() or None,
        metadata_data=metadata,
        reviewed_by_id=reviewed_by_id,
    )
    db.session.add(item)
    db.session.flush()
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
        subject = subject or (template.subject if template else None) or (
            f"Atualização da solicitação {service_request.protocol}"
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
