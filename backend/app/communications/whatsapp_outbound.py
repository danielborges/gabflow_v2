import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from flask import current_app
from sqlalchemy import select

from app.extensions import db
from app.models import (
    OutboxEvent,
    WhatsAppContact,
    WhatsAppContactOptStatus,
    WhatsAppConversation,
    WhatsAppIntegration,
    WhatsAppIntegrationStatus,
    WhatsAppMessage,
    WhatsAppMessageDirection,
    WhatsAppMessageStatus,
    WhatsAppMessageTemplate,
)

WHATSAPP_OUTBOUND_EVENT = "SendWhatsappMessageRequested"
WHATSAPP_TEMPLATE_SYNC_EVENT = "SyncWhatsappTemplateRequested"
OPT_OUT_CONFIRMATION = (
    "Seu pedido de saída foi registrado. Você não receberá novas mensagens deste gabinete "
    "por este canal."
)
TEMPLATE_NAME = re.compile(r"^[a-z0-9_]{1,160}$")


class WhatsAppOutboundError(RuntimeError):
    def __init__(self, code: str, message: str, *, retryable: bool = True):
        super().__init__(message)
        self.code = code
        self.retryable = retryable


@dataclass(frozen=True)
class OutboundResult:
    provider_message_id: str


@dataclass(frozen=True)
class TemplateSyncResult:
    status: str
    provider_template_id: str | None = None
    rejection_reason: str | None = None
    components: list | None = None


class WhatsAppOutboundAdapter(Protocol):
    def send(
        self, integration: WhatsAppIntegration, recipient: str, payload: dict
    ) -> OutboundResult: ...

    def sync_template(
        self, integration: WhatsAppIntegration, template: WhatsAppMessageTemplate
    ) -> TemplateSyncResult: ...


class UnconfiguredWhatsAppOutboundAdapter:
    def send(self, integration, recipient, payload):
        del integration, recipient, payload
        raise WhatsAppOutboundError(
            "OUTBOUND_RUNTIME_CREDENTIAL_UNAVAILABLE",
            "O dispatcher seguro da Cloud API não está configurado.",
        )

    def sync_template(self, integration, template):
        del integration, template
        raise WhatsAppOutboundError(
            "TEMPLATE_RUNTIME_CREDENTIAL_UNAVAILABLE",
            "A sincronização segura de templates não está configurada.",
        )


def outbound_adapter() -> WhatsAppOutboundAdapter:
    return current_app.extensions.get("whatsapp_outbound_adapter") or (
        UnconfiguredWhatsAppOutboundAdapter()
    )


def queue_outbound_message(
    conversation: WhatsAppConversation,
    *,
    actor_id: uuid.UUID,
    idempotency_key: str,
    text: str | None = None,
    template_id: uuid.UUID | None = None,
    parameters: list[str] | None = None,
) -> tuple[WhatsAppMessage, bool]:
    key = str(idempotency_key or "").strip()
    if not key or len(key) > 128:
        raise WhatsAppOutboundError(
            "IDEMPOTENCY_KEY_REQUIRED", "Informe uma chave de idempotência válida.", retryable=False
        )
    existing = db.session.scalar(
        select(WhatsAppMessage).where(
            WhatsAppMessage.tenant_id == conversation.tenant_id,
            WhatsAppMessage.idempotency_key == key,
        )
    )
    if existing:
        if existing.conversation_id != conversation.id:
            raise WhatsAppOutboundError(
                "IDEMPOTENCY_CONFLICT", "A chave já foi usada em outra conversa.", retryable=False
            )
        clean_text = str(text or "").strip() or None
        clean_parameters = [str(value)[:1000] for value in (parameters or [])]
        if (
            existing.template_id != template_id
            or (template_id is None and existing.outbound_content != clean_text)
            or (template_id is not None and existing.template_parameters != clean_parameters)
        ):
            raise WhatsAppOutboundError(
                "IDEMPOTENCY_CONFLICT",
                "A chave já foi usada com outro conteúdo.",
                retryable=False,
            )
        return existing, False

    contact = _contact(conversation)
    template = _template(conversation, template_id) if template_id else None
    if parameters is not None and not isinstance(parameters, list):
        raise WhatsAppOutboundError(
            "TEMPLATE_PARAMETERS_INVALID", "Os parâmetros devem ser uma lista.", retryable=False
        )
    clean_parameters = [str(value)[:1000] for value in (parameters or [])]
    rendered, decision = outbound_policy(
        conversation,
        contact,
        text=text,
        template=template,
        parameters=clean_parameters,
        opt_out_confirmation=False,
    )
    message_id = uuid.uuid4()
    message = WhatsAppMessage(
        id=message_id,
        tenant_id=conversation.tenant_id,
        conversation_id=conversation.id,
        provider_message_id=f"pending:{message_id}",
        direction=WhatsAppMessageDirection.OUTBOUND,
        message_type="template" if template else "text",
        status=WhatsAppMessageStatus.QUEUED,
        occurred_at=datetime.now(UTC),
        outbound_content=rendered,
        template_id=template.id if template else None,
        template_parameters=clean_parameters,
        idempotency_key=key,
        requested_by_id=actor_id,
        policy_decision=decision,
    )
    db.session.add(message)
    db.session.add(_send_event(message))
    return message, True


def queue_opt_out_confirmation(
    conversation: WhatsAppConversation,
    contact: WhatsAppContact,
    integration: WhatsAppIntegration,
    *,
    correlation_id: str | None,
) -> WhatsAppMessage:
    existing = db.session.scalar(
        select(WhatsAppMessage).where(
            WhatsAppMessage.tenant_id == conversation.tenant_id,
            WhatsAppMessage.conversation_id == conversation.id,
            WhatsAppMessage.opt_out_confirmation.is_(True),
        )
    )
    if existing:
        return existing
    message_id = uuid.uuid4()
    message = WhatsAppMessage(
        id=message_id,
        tenant_id=conversation.tenant_id,
        conversation_id=conversation.id,
        provider_message_id=f"pending:{message_id}",
        direction=WhatsAppMessageDirection.OUTBOUND,
        message_type="text",
        status=WhatsAppMessageStatus.QUEUED,
        occurred_at=datetime.now(UTC),
        outbound_content=OPT_OUT_CONFIRMATION,
        template_parameters=[],
        idempotency_key=f"optout:{conversation.id}",
        requested_by_id=integration.created_by_id,
        policy_decision="OPT_OUT_CONFIRMATION",
        opt_out_confirmation=True,
        correlation_id=correlation_id,
    )
    db.session.add(message)
    db.session.add(_send_event(message))
    return message


def outbound_policy(
    conversation: WhatsAppConversation,
    contact: WhatsAppContact,
    *,
    text: str | None,
    template: WhatsAppMessageTemplate | None,
    parameters: list[str],
    opt_out_confirmation: bool,
) -> tuple[str, str]:
    from app.communications.whatsapp_pilot import outbound_is_paused

    if outbound_is_paused(conversation.tenant_id) and not opt_out_confirmation:
        raise WhatsAppOutboundError(
            "PILOT_OUTBOUND_PAUSED",
            "As saidas do WhatsApp estao pausadas por controle operacional.",
            retryable=False,
        )
    if contact.opt_status != WhatsAppContactOptStatus.ACTIVE and not opt_out_confirmation:
        raise WhatsAppOutboundError(
            "CONTACT_OPTED_OUT", "O contato não permite novas mensagens.", retryable=False
        )
    if opt_out_confirmation:
        return OPT_OUT_CONFIRMATION, "OPT_OUT_CONFIRMATION"
    now = datetime.now(UTC)
    window_open = bool(
        conversation.window_expires_at and _utc(conversation.window_expires_at) > now
    )
    if template is None:
        clean_text = str(text or "").strip()
        if not clean_text or len(clean_text) > 4096:
            raise WhatsAppOutboundError(
                "OUTBOUND_TEXT_INVALID",
                "A mensagem deve possuir até 4096 caracteres.",
                retryable=False,
            )
        if not window_open:
            raise WhatsAppOutboundError(
                "FREE_TEXT_WINDOW_CLOSED",
                "A janela de atendimento encerrou. Selecione um template aprovado.",
                retryable=False,
            )
        return clean_text, "FREE_TEXT_WINDOW_OPEN"
    if not template.active or template.status != "APPROVED":
        raise WhatsAppOutboundError(
            "TEMPLATE_NOT_APPROVED", "O template não está aprovado pela Meta.", retryable=False
        )
    if template.category == "MARKETING":
        raise WhatsAppOutboundError(
            "MARKETING_DISABLED",
            "Templates de marketing político permanecem desabilitados.",
            retryable=False,
        )
    if len(parameters) != len(template.variables):
        raise WhatsAppOutboundError(
            "TEMPLATE_PARAMETERS_INVALID",
            "Preencha todos os parâmetros do template.",
            retryable=False,
        )
    rendered = template.body
    for index, value in enumerate(parameters, start=1):
        rendered = rendered.replace("{{" + str(index) + "}}", value)
    return rendered, "APPROVED_TEMPLATE"


def dispatch_outbound_message(message: WhatsAppMessage) -> None:
    if message.status in {
        WhatsAppMessageStatus.SENT,
        WhatsAppMessageStatus.DELIVERED,
        WhatsAppMessageStatus.READ,
    }:
        return
    conversation = db.session.scalar(
        select(WhatsAppConversation).where(
            WhatsAppConversation.id == message.conversation_id,
            WhatsAppConversation.tenant_id == message.tenant_id,
        )
    )
    if conversation is None:
        raise WhatsAppOutboundError(
            "CONVERSATION_NOT_FOUND", "Conversa não encontrada.", retryable=False
        )
    contact = _contact(conversation)
    integration = db.session.scalar(
        select(WhatsAppIntegration).where(
            WhatsAppIntegration.id == conversation.integration_id,
            WhatsAppIntegration.tenant_id == message.tenant_id,
            WhatsAppIntegration.status == WhatsAppIntegrationStatus.ACTIVE,
        )
    )
    if integration is None:
        raise WhatsAppOutboundError("INTEGRATION_INACTIVE", "Integração inativa.", retryable=False)
    template = _template(conversation, message.template_id) if message.template_id else None
    outbound_policy(
        conversation,
        contact,
        text=message.outbound_content,
        template=template,
        parameters=message.template_parameters or [],
        opt_out_confirmation=message.opt_out_confirmation,
    )
    payload = (
        {
            "type": "template",
            "template": {
                "name": template.name,
                "language": {"code": template.language},
                "parameters": message.template_parameters or [],
            },
        }
        if template
        else {"type": "text", "text": {"body": message.outbound_content}}
    )
    result = outbound_adapter().send(integration, contact.wa_user_id, payload)
    provider_id = str(result.provider_message_id or "").strip()
    if not provider_id:
        raise WhatsAppOutboundError("PROVIDER_MESSAGE_ID_MISSING", "Resposta inválida da Meta.")
    message.provider_message_id = provider_id
    message.status = WhatsAppMessageStatus.SENT
    message.sent_at = datetime.now(UTC)
    message.error = None
    message.error_code = None
    conversation.last_message_at = message.sent_at


def fail_outbound_message(message: WhatsAppMessage, code: str, error: str) -> None:
    message.status = WhatsAppMessageStatus.FAILED
    message.error_code = code[:120]
    message.error = error[:1000]
    message.failed_at = datetime.now(UTC)


def create_template(
    *,
    tenant_id: uuid.UUID,
    integration_id: uuid.UUID,
    actor_id: uuid.UUID,
    name: str,
    language: str,
    category: str,
    body: str,
    variables: list[str],
) -> WhatsAppMessageTemplate:
    clean_name = str(name or "").strip().lower()
    clean_language = str(language or "").strip()
    clean_category = str(category or "").strip().upper()
    clean_body = str(body or "").strip()
    if not isinstance(variables, list):
        raise WhatsAppOutboundError(
            "TEMPLATE_VARIABLES_INVALID", "As variáveis devem ser uma lista.", retryable=False
        )
    clean_variables = [str(value).strip()[:80] for value in variables if str(value).strip()]
    placeholders = {int(value) for value in re.findall(r"\{\{(\d+)\}\}", clean_body)}
    if placeholders != set(range(1, len(clean_variables) + 1)):
        raise WhatsAppOutboundError(
            "TEMPLATE_VARIABLES_INVALID",
            "Use marcadores sequenciais {{1}}, {{2}} para todas as variáveis.",
            retryable=False,
        )
    if not TEMPLATE_NAME.fullmatch(clean_name):
        raise WhatsAppOutboundError(
            "TEMPLATE_NAME_INVALID",
            "Use nome minúsculo com letras, números e underscore.",
            retryable=False,
        )
    if clean_category not in {"UTILITY", "AUTHENTICATION"}:
        raise WhatsAppOutboundError(
            "TEMPLATE_CATEGORY_INVALID",
            "Apenas templates transacionais são permitidos.",
            retryable=False,
        )
    if not clean_language or not clean_body or len(clean_body) > 4096:
        raise WhatsAppOutboundError(
            "TEMPLATE_INVALID", "Idioma e conteúdo válido são obrigatórios.", retryable=False
        )
    integration = db.session.scalar(
        select(WhatsAppIntegration).where(
            WhatsAppIntegration.id == integration_id,
            WhatsAppIntegration.tenant_id == tenant_id,
        )
    )
    if integration is None:
        raise WhatsAppOutboundError(
            "INTEGRATION_NOT_FOUND", "Integração não encontrada.", retryable=False
        )
    latest = db.session.scalar(
        select(WhatsAppMessageTemplate)
        .where(
            WhatsAppMessageTemplate.tenant_id == tenant_id,
            WhatsAppMessageTemplate.name == clean_name,
            WhatsAppMessageTemplate.language == clean_language,
        )
        .order_by(WhatsAppMessageTemplate.version.desc())
    )
    item = WhatsAppMessageTemplate(
        tenant_id=tenant_id,
        integration_id=integration_id,
        name=clean_name,
        language=clean_language,
        category=clean_category,
        status="DRAFT",
        version=(latest.version + 1) if latest else 1,
        body=clean_body,
        variables=clean_variables,
        created_by_id=actor_id,
    )
    db.session.add(item)
    db.session.flush()
    db.session.add(
        OutboxEvent(
            tenant_id=tenant_id,
            event_type=WHATSAPP_TEMPLATE_SYNC_EVENT,
            aggregate_type="whatsapp_message_template",
            aggregate_id=str(item.id),
            payload={"templateId": str(item.id)},
        )
    )
    item.status = "PENDING"
    return item


def sync_template(template: WhatsAppMessageTemplate) -> None:
    integration = db.session.scalar(
        select(WhatsAppIntegration).where(
            WhatsAppIntegration.id == template.integration_id,
            WhatsAppIntegration.tenant_id == template.tenant_id,
            WhatsAppIntegration.status == WhatsAppIntegrationStatus.ACTIVE,
        )
    )
    if integration is None:
        raise WhatsAppOutboundError("INTEGRATION_INACTIVE", "Integração inativa.", retryable=False)
    result = outbound_adapter().sync_template(integration, template)
    status = str(result.status or "").upper()
    if status not in {"PENDING", "APPROVED", "REJECTED", "PAUSED", "DISABLED"}:
        raise WhatsAppOutboundError(
            "TEMPLATE_STATUS_INVALID", "Status inválido retornado pela Meta."
        )
    template.status = status
    template.provider_template_id = result.provider_template_id or template.provider_template_id
    template.rejection_reason = result.rejection_reason
    template.provider_components = result.components or template.provider_components
    template.synced_at = datetime.now(UTC)


def template_data(template: WhatsAppMessageTemplate) -> dict:
    return {
        "id": str(template.id),
        "nome": template.name,
        "idioma": template.language,
        "categoria": template.category,
        "status": template.status,
        "versao": template.version,
        "conteudo": template.body,
        "variaveis": template.variables,
        "metaTemplateId": template.provider_template_id,
        "motivoRejeicao": template.rejection_reason,
        "ativa": template.active,
        "sincronizadaEm": template.synced_at.isoformat() if template.synced_at else None,
    }


def message_data(message: WhatsAppMessage) -> dict:
    return {
        "id": str(message.id),
        "status": message.status.value,
        "tipo": message.message_type,
        "conteudo": message.outbound_content,
        "decisaoPolitica": message.policy_decision,
        "templateId": str(message.template_id) if message.template_id else None,
        "criadaEm": message.occurred_at.isoformat(),
        "erro": message.error if message.status == WhatsAppMessageStatus.FAILED else None,
    }


def _send_event(message: WhatsAppMessage) -> OutboxEvent:
    return OutboxEvent(
        tenant_id=message.tenant_id,
        event_type=WHATSAPP_OUTBOUND_EVENT,
        aggregate_type="whatsapp_message",
        aggregate_id=str(message.id),
        payload={"messageId": str(message.id)},
    )


def _contact(conversation: WhatsAppConversation) -> WhatsAppContact:
    contact = db.session.scalar(
        select(WhatsAppContact).where(
            WhatsAppContact.id == conversation.contact_id,
            WhatsAppContact.tenant_id == conversation.tenant_id,
        )
    )
    if contact is None:
        raise WhatsAppOutboundError("CONTACT_NOT_FOUND", "Contato não encontrado.", retryable=False)
    return contact


def _template(
    conversation: WhatsAppConversation, template_id: uuid.UUID | None
) -> WhatsAppMessageTemplate | None:
    if template_id is None:
        return None
    template = db.session.scalar(
        select(WhatsAppMessageTemplate).where(
            WhatsAppMessageTemplate.id == template_id,
            WhatsAppMessageTemplate.tenant_id == conversation.tenant_id,
            WhatsAppMessageTemplate.integration_id == conversation.integration_id,
        )
    )
    if template is None:
        raise WhatsAppOutboundError(
            "TEMPLATE_NOT_FOUND", "Template não encontrado.", retryable=False
        )
    return template


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
