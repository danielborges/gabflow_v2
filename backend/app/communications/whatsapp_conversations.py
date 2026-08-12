import re
import unicodedata
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import or_, select

from app.extensions import db
from app.models import (
    ChannelMessage,
    OutboxEvent,
    User,
    UserStatus,
    WhatsAppContact,
    WhatsAppContactOptStatus,
    WhatsAppConversation,
    WhatsAppConversationMode,
    WhatsAppConversationState,
    WhatsAppConversationTransition,
    WhatsAppIntegration,
    WhatsAppMessage,
    WhatsAppMessageDirection,
    WhatsAppMessageStatus,
    WhatsAppWebhookEvent,
)

RULE_VERSION = "conversation-v1"
CONVERSATION_STATE_CHANGED_EVENT = "WhatsappConversationStateChanged"
OPT_OUT_COMMANDS = {"PARAR", "SAIR", "CANCELAR", "STOP", "DESCADASTRAR"}
HUMAN_REQUESTS = {
    "ATENDENTE",
    "ASSESSOR",
    "FALAR COM ASSESSOR",
    "FALAR COM ATENDENTE",
    "ATENDIMENTO HUMANO",
}
TERMINAL_STATES = {
    WhatsAppConversationState.OPTED_OUT,
    WhatsAppConversationState.BLOCKED,
    WhatsAppConversationState.CLOSED,
}
STATUS_ORDER = {
    WhatsAppMessageStatus.QUEUED: 0,
    WhatsAppMessageStatus.SENT: 1,
    WhatsAppMessageStatus.DELIVERED: 2,
    WhatsAppMessageStatus.READ: 3,
}


class ConversationValidationError(ValueError):
    pass


def record_inbound_conversation_message(
    *,
    webhook_event: WhatsAppWebhookEvent,
    integration: WhatsAppIntegration,
    channel_message: ChannelMessage,
) -> WhatsAppConversation:
    occurred_at = _provider_datetime(webhook_event.payload.get("timestamp"))
    contact = _contact(
        tenant_id=integration.tenant_id,
        wa_user_id=str(webhook_event.payload.get("from") or "").strip(),
        profile_name=webhook_event.payload.get("senderName"),
        occurred_at=occurred_at,
    )
    conversation = _conversation(contact, integration, occurred_at)
    existing = db.session.execute(
        select(WhatsAppMessage).where(
            WhatsAppMessage.tenant_id == integration.tenant_id,
            WhatsAppMessage.provider_message_id == webhook_event.provider_message_id,
            WhatsAppMessage.direction == WhatsAppMessageDirection.INBOUND,
        )
    ).scalar_one_or_none()
    if existing is not None:
        return conversation

    db.session.add(
        WhatsAppMessage(
            tenant_id=integration.tenant_id,
            conversation_id=conversation.id,
            channel_message_id=channel_message.id,
            provider_message_id=str(webhook_event.provider_message_id),
            direction=WhatsAppMessageDirection.INBOUND,
            message_type=str(webhook_event.payload.get("type") or "unknown")[:40],
            status=WhatsAppMessageStatus.RECEIVED,
            occurred_at=occurred_at,
        )
    )
    if (
        conversation.last_message_at is None
        or _utc(occurred_at) > _utc(conversation.last_message_at)
    ):
        conversation.last_message_at = occurred_at
    next_window = occurred_at + timedelta(hours=24)
    if (
        conversation.window_expires_at is None
        or _utc(next_window) > _utc(conversation.window_expires_at)
    ):
        conversation.window_expires_at = next_window
    conversation.unread_count += 1
    if _utc(occurred_at) > _utc(contact.last_seen_at):
        contact.last_seen_at = occurred_at
    if webhook_event.payload.get("senderName"):
        contact.profile_name = str(webhook_event.payload["senderName"])[:180]

    command = _normalized_command(channel_message.content)
    if command in OPT_OUT_COMMANDS:
        contact.opt_status = WhatsAppContactOptStatus.OPTED_OUT
        contact.opted_out_at = occurred_at
        transition_conversation(
            conversation,
            WhatsAppConversationState.OPTED_OUT,
            actor_type="CITIZEN",
            origin="WHATSAPP_INBOUND",
            reason="Comando de opt-out reconhecido.",
            correlation_id=webhook_event.correlation_id,
        )
        from app.communications.whatsapp_outbound import queue_opt_out_confirmation

        queue_opt_out_confirmation(
            conversation,
            contact,
            integration,
            correlation_id=webhook_event.correlation_id,
        )
    elif command in HUMAN_REQUESTS:
        conversation.mode = WhatsAppConversationMode.HUMAN
        transition_conversation(
            conversation,
            WhatsAppConversationState.HUMAN_HANDOFF,
            actor_type="CITIZEN",
            origin="WHATSAPP_INBOUND",
            reason="Cidadao solicitou atendimento humano.",
            correlation_id=webhook_event.correlation_id,
        )
    elif conversation.state == WhatsAppConversationState.NEW:
        transition_conversation(
            conversation,
            WhatsAppConversationState.PRIVACY_NOTICE,
            actor_type="SYSTEM",
            origin="WHATSAPP_INBOUND",
            reason="Primeira interacao recebida; aviso de privacidade requerido.",
            correlation_id=webhook_event.correlation_id,
        )
        from app.communications.whatsapp_service_flow import (
            ensure_privacy_notice_requested,
        )

        ensure_privacy_notice_requested(
            conversation,
            contact,
            correlation_id=webhook_event.correlation_id,
        )
    return conversation


def record_provider_message_status(webhook_event: WhatsAppWebhookEvent) -> None:
    message = db.session.execute(
        select(WhatsAppMessage).where(
            WhatsAppMessage.tenant_id == webhook_event.tenant_id,
            WhatsAppMessage.provider_message_id == webhook_event.provider_message_id,
        )
    ).scalar_one_or_none()
    if message is None:
        return
    value = str(webhook_event.payload.get("status") or "").upper()
    try:
        target = WhatsAppMessageStatus(value)
    except ValueError:
        return
    if target == WhatsAppMessageStatus.FAILED:
        if message.status not in {
            WhatsAppMessageStatus.DELIVERED,
            WhatsAppMessageStatus.READ,
        }:
            message.status = target
            message.failed_at = datetime.now(UTC)
            errors = webhook_event.payload.get("errors") or []
            first_error = errors[0] if errors and isinstance(errors[0], dict) else {}
            message.error_code = str(first_error.get("code") or "META_DELIVERY_FAILED")[:120]
            message.error = str(first_error.get("message") or "Falha informada pela Meta.")[:1000]
        return
    if STATUS_ORDER.get(target, -1) > STATUS_ORDER.get(message.status, -1):
        message.status = target
        occurred_at = _provider_datetime(webhook_event.payload.get("timestamp"))
        if target == WhatsAppMessageStatus.SENT:
            message.sent_at = occurred_at
        elif target == WhatsAppMessageStatus.DELIVERED:
            message.delivered_at = occurred_at
        elif target == WhatsAppMessageStatus.READ:
            message.read_at = occurred_at


def transition_conversation(
    conversation: WhatsAppConversation,
    target: WhatsAppConversationState,
    *,
    actor_type: str,
    origin: str,
    reason: str | None = None,
    actor_id: uuid.UUID | None = None,
    correlation_id: str | None = None,
) -> None:
    if conversation.state == target:
        return
    previous = conversation.state
    conversation.state = target
    conversation.version += 1
    db.session.add(
        WhatsAppConversationTransition(
            tenant_id=conversation.tenant_id,
            conversation_id=conversation.id,
            from_state=previous,
            to_state=target,
            actor_type=actor_type,
            actor_id=actor_id,
            origin=origin,
            reason=reason[:500] if reason else None,
            rule_version=RULE_VERSION,
            correlation_id=correlation_id,
        )
    )
    db.session.add(
        OutboxEvent(
            tenant_id=conversation.tenant_id,
            event_type=CONVERSATION_STATE_CHANGED_EVENT,
            aggregate_type="whatsapp_conversation",
            aggregate_id=str(conversation.id),
            payload={
                "conversationId": str(conversation.id),
                "fromState": previous.value,
                "toState": target.value,
                "mode": conversation.mode.value,
                "ruleVersion": RULE_VERSION,
                "correlationId": correlation_id,
            },
        )
    )


def start_handoff(
    conversation: WhatsAppConversation,
    *,
    actor_id: uuid.UUID,
    assignee_id: uuid.UUID | None,
    reason: str,
) -> None:
    if conversation.state in TERMINAL_STATES:
        raise ConversationValidationError("Conversa encerrada nao permite handoff.")
    if assignee_id is not None:
        _authorized_assignee(conversation.tenant_id, assignee_id)
    conversation.assigned_user_id = assignee_id or actor_id
    conversation.mode = WhatsAppConversationMode.HUMAN
    transition_conversation(
        conversation,
        WhatsAppConversationState.HUMAN_HANDOFF,
        actor_type="USER",
        actor_id=actor_id,
        origin="INBOX_ACTION",
        reason=reason or "Atendimento humano iniciado.",
    )


def resume_bot(
    conversation: WhatsAppConversation,
    *,
    actor_id: uuid.UUID,
    reason: str,
) -> None:
    if conversation.mode != WhatsAppConversationMode.HUMAN:
        raise ConversationValidationError("A conversa ja esta em modo automatico.")
    if conversation.state in TERMINAL_STATES:
        raise ConversationValidationError("Conversa encerrada nao pode retomar automacao.")
    prior_transition = (
        db.session.execute(
            select(WhatsAppConversationTransition)
            .where(
                WhatsAppConversationTransition.tenant_id == conversation.tenant_id,
                WhatsAppConversationTransition.conversation_id == conversation.id,
                WhatsAppConversationTransition.to_state
                == WhatsAppConversationState.HUMAN_HANDOFF,
            )
            .order_by(WhatsAppConversationTransition.occurred_at.desc())
        )
        .scalars()
        .first()
    )
    target = (
        prior_transition.from_state
        if prior_transition and prior_transition.from_state not in TERMINAL_STATES
        else WhatsAppConversationState.INTENT
    )
    conversation.mode = WhatsAppConversationMode.BOT
    conversation.assigned_user_id = None
    transition_conversation(
        conversation,
        target,
        actor_type="USER",
        actor_id=actor_id,
        origin="INBOX_ACTION",
        reason=reason or "Automacao retomada explicitamente.",
    )


def assign_conversation(
    conversation: WhatsAppConversation,
    *,
    actor_id: uuid.UUID,
    assignee_id: uuid.UUID | None,
) -> None:
    if assignee_id is not None:
        _authorized_assignee(conversation.tenant_id, assignee_id)
    conversation.assigned_user_id = assignee_id
    conversation.version += 1
    db.session.add(
        WhatsAppConversationTransition(
            tenant_id=conversation.tenant_id,
            conversation_id=conversation.id,
            from_state=conversation.state,
            to_state=conversation.state,
            actor_type="USER",
            actor_id=actor_id,
            origin="ASSIGNMENT",
            reason="Responsavel da conversa atualizado.",
            rule_version=RULE_VERSION,
        )
    )


def mark_conversation_read(conversation: WhatsAppConversation) -> None:
    conversation.unread_count = 0
    conversation.last_read_at = datetime.now(UTC)


def conversation_summary_data(
    conversation: WhatsAppConversation,
    *,
    contact: WhatsAppContact,
    assignee: User | None,
    last_message: ChannelMessage | None,
) -> dict:
    now = datetime.now(UTC)
    return {
        "id": str(conversation.id),
        "estado": conversation.state.value,
        "modo": conversation.mode.value,
        "versao": conversation.version,
        "naoLidas": conversation.unread_count,
        "ultimaMensagemEm": _iso(conversation.last_message_at),
        "janelaExpiraEm": _iso(conversation.window_expires_at),
        "janelaAberta": bool(
            conversation.window_expires_at
            and _utc(conversation.window_expires_at) > now
        ),
        "responsavel": (
            {"id": str(assignee.id), "nome": assignee.name} if assignee else None
        ),
        "contato": {
            "id": str(contact.id),
            "nome": contact.profile_name or "Contato WhatsApp",
            "whatsappMascarado": _masked_whatsapp(contact.wa_user_id),
            "cidadaoId": str(contact.citizen_id) if contact.citizen_id else None,
            "optStatus": contact.opt_status.value,
        },
        "ultimaMensagem": (
            {
                "conteudo": last_message.content,
                "tipo": (last_message.metadata_data or {}).get("messageType", "unknown"),
            }
            if last_message
            else None
        ),
    }


def conversation_detail_data(
    conversation: WhatsAppConversation,
    *,
    contact: WhatsAppContact,
    assignee: User | None,
    messages: list[tuple[WhatsAppMessage, ChannelMessage | None]],
    transitions: list[WhatsAppConversationTransition],
) -> dict:
    result = conversation_summary_data(
        conversation,
        contact=contact,
        assignee=assignee,
        last_message=messages[-1][1] if messages else None,
    )
    result["mensagens"] = [
        {
            "id": str(message.id),
            "direcao": message.direction.value,
            "tipo": message.message_type,
            "status": message.status.value,
            "conteudo": channel_message.content if channel_message else message.outbound_content,
            "ocorridaEm": _iso(message.occurred_at),
            "decisaoPolitica": message.policy_decision,
            "erro": message.error if message.status == WhatsAppMessageStatus.FAILED else None,
        }
        for message, channel_message in messages
    ]
    result["transicoes"] = [
        {
            "id": str(item.id),
            "de": item.from_state.value,
            "para": item.to_state.value,
            "atorTipo": item.actor_type,
            "atorId": str(item.actor_id) if item.actor_id else None,
            "origem": item.origin,
            "motivo": item.reason,
            "ocorridaEm": _iso(item.occurred_at),
        }
        for item in transitions
    ]
    return result


def conversation_search_filter(query: str):
    escaped = query.replace("%", "\\%").replace("_", "\\_")
    return or_(
        WhatsAppContact.profile_name.ilike(f"%{escaped}%", escape="\\"),
        WhatsAppContact.wa_user_id.ilike(f"%{escaped}%", escape="\\"),
    )


def _contact(
    *, tenant_id: uuid.UUID, wa_user_id: str, profile_name: str | None, occurred_at: datetime
) -> WhatsAppContact:
    if not wa_user_id:
        raise ConversationValidationError("Identificador WhatsApp do contato ausente.")
    contact = db.session.execute(
        select(WhatsAppContact).where(
            WhatsAppContact.tenant_id == tenant_id,
            WhatsAppContact.wa_user_id == wa_user_id,
        )
    ).scalar_one_or_none()
    if contact is None:
        contact = WhatsAppContact(
            tenant_id=tenant_id,
            wa_user_id=wa_user_id,
            profile_name=str(profile_name)[:180] if profile_name else None,
            first_seen_at=occurred_at,
            last_seen_at=occurred_at,
        )
        db.session.add(contact)
        db.session.flush()
    return contact


def _conversation(
    contact: WhatsAppContact,
    integration: WhatsAppIntegration,
    occurred_at: datetime,
) -> WhatsAppConversation:
    conversation = db.session.execute(
        select(WhatsAppConversation).where(
            WhatsAppConversation.tenant_id == contact.tenant_id,
            WhatsAppConversation.contact_id == contact.id,
        )
    ).scalar_one_or_none()
    if conversation is None:
        conversation = WhatsAppConversation(
            tenant_id=contact.tenant_id,
            contact_id=contact.id,
            integration_id=integration.id,
            state=WhatsAppConversationState.NEW,
            mode=WhatsAppConversationMode.BOT,
            window_expires_at=occurred_at + timedelta(hours=24),
            last_message_at=occurred_at,
        )
        db.session.add(conversation)
        db.session.flush()
    return conversation


def _authorized_assignee(tenant_id: uuid.UUID, user_id: uuid.UUID) -> User:
    user = db.session.execute(
        select(User).where(
            User.id == user_id,
            User.tenant_id == tenant_id,
            User.status == UserStatus.ACTIVE,
        )
    ).scalar_one_or_none()
    if user is None or user.role.value == "representative":
        raise ConversationValidationError("Responsavel nao encontrado no gabinete.")
    return user


def _provider_datetime(value) -> datetime:
    try:
        return datetime.fromtimestamp(int(value), tz=UTC)
    except (TypeError, ValueError, OSError):
        return datetime.now(UTC)


def _normalized_command(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", str(value or ""))
    without_marks = "".join(char for char in normalized if not unicodedata.combining(char))
    return re.sub(r"\s+", " ", without_marks).strip().upper()


def _masked_whatsapp(value: str) -> str:
    digits = "".join(char for char in str(value) if char.isdigit())
    return f"***{digits[-4:]}" if digits else "***"


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _iso(value: datetime | None) -> str | None:
    return _utc(value).isoformat() if value else None
