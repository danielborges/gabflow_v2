import hashlib
import json
import re
import secrets
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select

from app.communications.whatsapp_conversations import (
    TERMINAL_STATES,
    ConversationValidationError,
    transition_conversation,
)
from app.communications.whatsapp_service_flow import (
    WhatsAppServiceFlowError,
    citizen_suggestions,
    confirm_request_draft,
    identify_citizen,
    save_request_draft,
)
from app.extensions import db
from app.models import (
    OutboxEvent,
    WhatsAppContact,
    WhatsAppContactOptStatus,
    WhatsAppConversation,
    WhatsAppConversationMode,
    WhatsAppConversationState,
    WhatsAppFlowDefinition,
    WhatsAppFlowSession,
    WhatsAppFlowSubmission,
    WhatsAppPrivacyRecord,
    WhatsAppRequestDraft,
    WhatsAppWebhookEvent,
)

FLOW_KEYS = {
    "citizen_registration",
    "new_service_request",
    "request_complement",
}
FLOW_ENVIRONMENTS = {"SANDBOX", "STAGING", "PRODUCTION"}
FLOW_STATUSES = {"DRAFT", "ACTIVE", "RETIRED"}
FLOW_SESSION_MINUTES = 30
FLOW_LAUNCH_EVENT = "WhatsappFlowLaunchRequested"
FLOW_FALLBACK_EVENT = "WhatsappGuidedCollectionStarted"
FLOW_SUBMITTED_EVENT = "WhatsappFlowSubmitted"
META_FLOW_ID_PATTERN = re.compile(r"^[A-Za-z0-9_.:-]{4,100}$")


class WhatsAppFlowError(ValueError):
    pass


BUILTIN_FLOWS = {
    "citizen_registration": {
        "name": "Cadastro do cidadão",
        "schema": {
            "required": ["nome", "ciencia_privacidade", "confirmado"],
            "properties": {
                "nome": {"type": "string", "minLength": 2, "maxLength": 180},
                "forma_tratamento": {"type": "string", "maxLength": 80},
                "cidade": {"type": "string", "maxLength": 120},
                "bairro": {"type": "string", "maxLength": 120},
                "ciencia_privacidade": {"type": "boolean", "const": True},
                "confirmado": {"type": "boolean", "const": True},
            },
        },
        "screens": ["IDENTIFICATION", "ADDRESS", "REVIEW"],
    },
    "new_service_request": {
        "name": "Nova solicitação",
        "schema": {
            "required": ["assunto", "descricao", "confirmado"],
            "properties": {
                "categoria_id": {"type": "uuid"},
                "assunto": {"type": "string", "minLength": 2, "maxLength": 180},
                "descricao": {"type": "string", "minLength": 3, "maxLength": 5000},
                "local": {"type": "string", "maxLength": 500},
                "urgencia": {
                    "type": "string",
                    "enum": ["BAIXO", "MEDIO", "ALTO", "CRITICO"],
                },
                "confirmado": {"type": "boolean", "const": True},
            },
        },
        "screens": ["CATEGORY", "DETAILS", "LOCATION", "REVIEW"],
    },
    "request_complement": {
        "name": "Complemento de solicitação",
        "schema": {
            "required": ["confirmado"],
            "atLeastOne": ["assunto", "descricao", "local", "categoria_id", "urgencia"],
            "properties": {
                "categoria_id": {"type": "uuid"},
                "assunto": {"type": "string", "minLength": 2, "maxLength": 180},
                "descricao": {"type": "string", "minLength": 3, "maxLength": 5000},
                "local": {"type": "string", "maxLength": 500},
                "urgencia": {
                    "type": "string",
                    "enum": ["BAIXO", "MEDIO", "ALTO", "CRITICO"],
                },
                "confirmado": {"type": "boolean", "const": True},
            },
        },
        "screens": ["MISSING_DATA", "REVIEW"],
    },
}


def bootstrap_flow_definitions(
    tenant_id: uuid.UUID,
    actor_id: uuid.UUID,
    *,
    environment: str,
) -> list[WhatsAppFlowDefinition]:
    environment = _environment(environment)
    result = []
    for flow_key in sorted(FLOW_KEYS):
        existing = db.session.execute(
            select(WhatsAppFlowDefinition).where(
                WhatsAppFlowDefinition.tenant_id == tenant_id,
                WhatsAppFlowDefinition.flow_key == flow_key,
                WhatsAppFlowDefinition.version == 1,
                WhatsAppFlowDefinition.environment == environment,
            )
        ).scalar_one_or_none()
        if existing is not None:
            result.append(existing)
            continue
        result.append(_new_definition(tenant_id, actor_id, flow_key, 1, environment))
    return result


def create_flow_version(
    tenant_id: uuid.UUID,
    actor_id: uuid.UUID,
    *,
    flow_key: str,
    environment: str,
) -> WhatsAppFlowDefinition:
    flow_key = _flow_key(flow_key)
    environment = _environment(environment)
    latest = db.session.scalar(
        select(func.max(WhatsAppFlowDefinition.version)).where(
            WhatsAppFlowDefinition.tenant_id == tenant_id,
            WhatsAppFlowDefinition.flow_key == flow_key,
            WhatsAppFlowDefinition.environment == environment,
        )
    )
    return _new_definition(
        tenant_id,
        actor_id,
        flow_key,
        int(latest or 0) + 1,
        environment,
    )


def activate_flow_definition(
    definition: WhatsAppFlowDefinition,
    *,
    meta_flow_id: str,
) -> None:
    meta_flow_id = str(meta_flow_id or "").strip()
    if not META_FLOW_ID_PATTERN.fullmatch(meta_flow_id):
        raise WhatsAppFlowError("Informe o identificador do Flow publicado na Meta.")
    if definition.status == "RETIRED":
        raise WhatsAppFlowError("Versao aposentada nao pode ser reativada.")
    if definition.schema_hash != _definition_hash(
        definition.schema_json, definition.definition_json
    ):
        raise WhatsAppFlowError("A definicao foi alterada depois do versionamento.")
    now = datetime.now(UTC)
    active = db.session.scalars(
        select(WhatsAppFlowDefinition).where(
            WhatsAppFlowDefinition.tenant_id == definition.tenant_id,
            WhatsAppFlowDefinition.flow_key == definition.flow_key,
            WhatsAppFlowDefinition.environment == definition.environment,
            WhatsAppFlowDefinition.status == "ACTIVE",
            WhatsAppFlowDefinition.id != definition.id,
        )
    )
    for item in active:
        item.status = "RETIRED"
        item.retired_at = now
    definition.meta_flow_id = meta_flow_id
    definition.status = "ACTIVE"
    definition.activated_at = now


def launch_flow(
    conversation: WhatsAppConversation,
    contact: WhatsAppContact,
    *,
    actor_id: uuid.UUID,
    flow_key: str,
    environment: str,
) -> tuple[str, WhatsAppFlowSession | None]:
    _assert_conversation_active(conversation, contact)
    flow_key = _flow_key(flow_key)
    environment = _environment(environment)
    _validate_launch_prerequisites(conversation, contact, flow_key)
    definition = (
        db.session.execute(
            select(WhatsAppFlowDefinition)
            .where(
                WhatsAppFlowDefinition.tenant_id == conversation.tenant_id,
                WhatsAppFlowDefinition.flow_key == flow_key,
                WhatsAppFlowDefinition.environment == environment,
                WhatsAppFlowDefinition.status == "ACTIVE",
            )
            .order_by(WhatsAppFlowDefinition.version.desc())
        )
        .scalars()
        .first()
    )
    if definition is None:
        transition_conversation(
            conversation,
            WhatsAppConversationState.DATA_COLLECTION,
            actor_type="USER",
            actor_id=actor_id,
            origin="INBOX_FLOW_FALLBACK",
            reason=f"Flow {flow_key} indisponivel; coleta guiada iniciada.",
        )
        db.session.add(
            OutboxEvent(
                tenant_id=conversation.tenant_id,
                event_type=FLOW_FALLBACK_EVENT,
                aggregate_type="whatsapp_conversation",
                aggregate_id=str(conversation.id),
                payload={"conversationId": str(conversation.id), "flowKey": flow_key},
            )
        )
        return "GUIDED", None

    for pending in db.session.scalars(
        select(WhatsAppFlowSession).where(
            WhatsAppFlowSession.tenant_id == conversation.tenant_id,
            WhatsAppFlowSession.conversation_id == conversation.id,
            WhatsAppFlowSession.status == "PENDING",
        )
    ):
        pending.status = "SUPERSEDED"
    raw_token = secrets.token_urlsafe(32)
    session = WhatsAppFlowSession(
        tenant_id=conversation.tenant_id,
        definition_id=definition.id,
        conversation_id=conversation.id,
        token_hash=_token_hash(raw_token),
        status="PENDING",
        initiated_by_id=actor_id,
        expires_at=datetime.now(UTC) + timedelta(minutes=FLOW_SESSION_MINUTES),
    )
    db.session.add(session)
    db.session.flush()
    transition_conversation(
        conversation,
        WhatsAppConversationState.DATA_COLLECTION,
        actor_type="USER",
        actor_id=actor_id,
        origin="INBOX_FLOW_LAUNCH",
        reason=f"Flow {flow_key} v{definition.version} preparado.",
    )
    db.session.add(
        OutboxEvent(
            tenant_id=conversation.tenant_id,
            event_type=FLOW_LAUNCH_EVENT,
            aggregate_type="whatsapp_flow_session",
            aggregate_id=str(session.id),
            payload={
                "sessionId": str(session.id),
                "conversationId": str(conversation.id),
                "flowKey": definition.flow_key,
                "flowVersion": definition.version,
                "metaFlowId": definition.meta_flow_id,
                "flowToken": raw_token,
                "environment": definition.environment,
            },
        )
    )
    return "FLOW", session


def process_flow_reply(
    *,
    webhook_event: WhatsAppWebhookEvent,
    conversation: WhatsAppConversation,
    contact: WhatsAppContact,
    flow_reply: dict,
    actor_id: uuid.UUID,
) -> WhatsAppFlowSubmission | None:
    response = flow_reply.get("responseJson")
    if not isinstance(response, dict):
        _reject_without_session(webhook_event, conversation, "INVALID_RESPONSE_JSON")
        return None
    token = str(response.get("flow_token") or response.get("flowToken") or "").strip()
    if not token:
        _reject_without_session(webhook_event, conversation, "FLOW_TOKEN_MISSING")
        return None
    session = db.session.execute(
        select(WhatsAppFlowSession).where(
            WhatsAppFlowSession.token_hash == _token_hash(token),
            WhatsAppFlowSession.tenant_id == conversation.tenant_id,
        )
    ).scalar_one_or_none()
    if session is None or session.conversation_id != conversation.id:
        _reject_without_session(webhook_event, conversation, "FLOW_TOKEN_INVALID")
        return None
    existing = db.session.execute(
        select(WhatsAppFlowSubmission).where(
            WhatsAppFlowSubmission.tenant_id == conversation.tenant_id,
            WhatsAppFlowSubmission.provider_message_id == webhook_event.provider_message_id,
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing
    definition = db.session.execute(
        select(WhatsAppFlowDefinition).where(
            WhatsAppFlowDefinition.tenant_id == conversation.tenant_id,
            WhatsAppFlowDefinition.id == session.definition_id,
        )
    ).scalar_one()
    values = {
        key: value
        for key, value in response.items()
        if key not in {"flow_token", "flowToken", "screen", "submission_id"}
    }
    response_hash = _response_hash(session.id, values)
    repeated_response = db.session.execute(
        select(WhatsAppFlowSubmission).where(
            WhatsAppFlowSubmission.tenant_id == conversation.tenant_id,
            WhatsAppFlowSubmission.response_hash == response_hash,
        )
    ).scalar_one_or_none()
    if repeated_response is not None:
        return repeated_response
    submission = WhatsAppFlowSubmission(
        tenant_id=conversation.tenant_id,
        session_id=session.id,
        definition_id=definition.id,
        conversation_id=conversation.id,
        webhook_event_id=webhook_event.id,
        provider_message_id=str(webhook_event.provider_message_id),
        response_hash=response_hash,
        values=values,
        status="RECEIVED",
    )
    db.session.add(submission)
    db.session.flush()
    if session.status != "PENDING":
        return _reject_submission(submission, "FLOW_SESSION_NOT_PENDING")
    if _as_utc(session.expires_at) <= datetime.now(UTC):
        session.status = "EXPIRED"
        return _reject_submission(submission, "FLOW_SESSION_EXPIRED")
    try:
        normalized = validate_flow_values(definition.schema_json, values)
        request_id = _apply_submission(
            definition,
            session,
            submission,
            conversation,
            contact,
            normalized,
            actor_id,
        )
    except (WhatsAppFlowError, WhatsAppServiceFlowError, ConversationValidationError) as error:
        return _reject_submission(submission, _error_code(error))
    submission.values = _minimized_submission_values(submission.values)
    if submission.status == "NEEDS_REVIEW":
        return submission
    submission.status = "APPLIED"
    submission.request_id = request_id
    submission.processed_at = datetime.now(UTC)
    session.status = "COMPLETED"
    session.completed_at = submission.processed_at
    db.session.add(
        OutboxEvent(
            tenant_id=conversation.tenant_id,
            event_type=FLOW_SUBMITTED_EVENT,
            aggregate_type="whatsapp_flow_submission",
            aggregate_id=str(submission.id),
            payload={
                "submissionId": str(submission.id),
                "conversationId": str(conversation.id),
                "flowKey": definition.flow_key,
                "flowVersion": definition.version,
                "requestId": str(request_id) if request_id else None,
                "status": submission.status,
            },
        )
    )
    return submission


def validate_flow_values(schema: dict, values: dict) -> dict:
    if not isinstance(schema, dict) or not isinstance(values, dict):
        raise WhatsAppFlowError("FLOW_SCHEMA_INVALID")
    properties = schema.get("properties") or {}
    unknown = set(values) - set(properties)
    if unknown:
        raise WhatsAppFlowError("FLOW_UNKNOWN_FIELD")
    for field in schema.get("required") or []:
        if field not in values or values[field] in {None, ""}:
            raise WhatsAppFlowError(f"FLOW_REQUIRED_{str(field).upper()}")
    if schema.get("atLeastOne") and not any(
        values.get(field) not in {None, ""} for field in schema["atLeastOne"]
    ):
        raise WhatsAppFlowError("FLOW_COMPLEMENT_EMPTY")
    normalized = {}
    for field, value in values.items():
        rule = properties[field]
        value_type = rule.get("type")
        if value_type == "boolean":
            if not isinstance(value, bool):
                raise WhatsAppFlowError(f"FLOW_TYPE_{field.upper()}")
            normalized[field] = value
        elif value_type == "uuid":
            try:
                normalized[field] = str(uuid.UUID(str(value)))
            except ValueError as error:
                raise WhatsAppFlowError(f"FLOW_TYPE_{field.upper()}") from error
        elif value_type == "string":
            if not isinstance(value, str):
                raise WhatsAppFlowError(f"FLOW_TYPE_{field.upper()}")
            clean = " ".join(value.split())
            if len(clean) < int(rule.get("minLength", 0)) or len(clean) > int(
                rule.get("maxLength", 10000)
            ):
                raise WhatsAppFlowError(f"FLOW_LENGTH_{field.upper()}")
            normalized[field] = clean
        else:
            raise WhatsAppFlowError("FLOW_SCHEMA_UNSUPPORTED")
        if "const" in rule and normalized[field] != rule["const"]:
            raise WhatsAppFlowError(f"FLOW_CONST_{field.upper()}")
        if "enum" in rule and normalized[field] not in rule["enum"]:
            raise WhatsAppFlowError(f"FLOW_ENUM_{field.upper()}")
    return normalized


def flow_definition_data(item: WhatsAppFlowDefinition) -> dict:
    return {
        "id": str(item.id),
        "chave": item.flow_key,
        "nome": item.display_name,
        "versao": item.version,
        "ambiente": item.environment,
        "status": item.status,
        "metaFlowId": item.meta_flow_id,
        "schemaHash": item.schema_hash,
        "telas": item.definition_json.get("screens", []),
        "ativadaEm": item.activated_at.isoformat() if item.activated_at else None,
        "criadaEm": item.created_at.isoformat(),
    }


def flow_state_data(conversation: WhatsAppConversation) -> dict:
    session = db.session.execute(
        select(WhatsAppFlowSession, WhatsAppFlowDefinition)
        .join(
            WhatsAppFlowDefinition,
            (WhatsAppFlowDefinition.tenant_id == WhatsAppFlowSession.tenant_id)
            & (WhatsAppFlowDefinition.id == WhatsAppFlowSession.definition_id),
        )
        .where(
            WhatsAppFlowSession.tenant_id == conversation.tenant_id,
            WhatsAppFlowSession.conversation_id == conversation.id,
        )
        .order_by(WhatsAppFlowSession.created_at.desc())
    ).first()
    if session is None:
        return {"sessao": None, "fallbackDisponivel": True}
    item, definition = session
    submission = db.session.execute(
        select(WhatsAppFlowSubmission)
        .where(
            WhatsAppFlowSubmission.tenant_id == conversation.tenant_id,
            WhatsAppFlowSubmission.session_id == item.id,
        )
        .order_by(WhatsAppFlowSubmission.received_at.desc())
        .limit(1)
    ).scalar_one_or_none()
    return {
        "sessao": {
            "id": str(item.id),
            "chave": definition.flow_key,
            "nome": definition.display_name,
            "versao": definition.version,
            "status": item.status,
            "expiraEm": _as_utc(item.expires_at).isoformat(),
        },
        "ultimaSubmissao": (
            {
                "status": submission.status,
                "erro": submission.error_code,
                "recebidaEm": submission.received_at.isoformat(),
            }
            if submission
            else None
        ),
        "fallbackDisponivel": item.status in {"EXPIRED", "FAILED", "SUPERSEDED"},
    }


def _new_definition(
    tenant_id: uuid.UUID,
    actor_id: uuid.UUID,
    flow_key: str,
    version: int,
    environment: str,
) -> WhatsAppFlowDefinition:
    builtin = BUILTIN_FLOWS[flow_key]
    schema = json.loads(json.dumps(builtin["schema"]))
    definition = {
        "flowKey": flow_key,
        "version": version,
        "screens": list(builtin["screens"]),
        "terminal": "REVIEW",
    }
    item = WhatsAppFlowDefinition(
        tenant_id=tenant_id,
        flow_key=flow_key,
        display_name=builtin["name"],
        version=version,
        environment=environment,
        status="DRAFT",
        schema_json=schema,
        definition_json=definition,
        schema_hash=_definition_hash(schema, definition),
        created_by_id=actor_id,
    )
    db.session.add(item)
    return item


def _apply_submission(
    definition: WhatsAppFlowDefinition,
    session: WhatsAppFlowSession,
    submission: WhatsAppFlowSubmission,
    conversation: WhatsAppConversation,
    contact: WhatsAppContact,
    values: dict,
    actor_id: uuid.UUID,
) -> uuid.UUID | None:
    if definition.flow_key == "citizen_registration":
        if not values.get("ciencia_privacidade") or not values.get("confirmado"):
            raise WhatsAppFlowError("FLOW_PRIVACY_NOT_ACKNOWLEDGED")
        if contact.citizen_id is None and citizen_suggestions(contact):
            submission.status = "NEEDS_REVIEW"
            submission.processed_at = datetime.now(UTC)
            session.status = "COMPLETED"
            session.completed_at = submission.processed_at
            conversation.mode = WhatsAppConversationMode.HUMAN
            transition_conversation(
                conversation,
                WhatsAppConversationState.HUMAN_HANDOFF,
                actor_type="SYSTEM",
                origin="WHATSAPP_FLOW",
                reason="Cadastro recebido por Flow possui correspondencia existente.",
            )
            return None
        citizen, created = identify_citizen(
            conversation,
            contact,
            actor_id=actor_id,
            citizen_id=contact.citizen_id,
            name=values.get("nome"),
            confirmed=True,
            actor_type="CITIZEN",
            origin="WHATSAPP_FLOW",
        )
        if created and (values.get("cidade") or values.get("bairro")):
            citizen.addresses = [
                {
                    "cidade": values.get("cidade"),
                    "bairro": values.get("bairro"),
                    "confirmado": True,
                    "origem": "WHATSAPP_FLOW",
                }
            ]
        return None
    if contact.citizen_id is None:
        raise WhatsAppFlowError("FLOW_CITIZEN_REQUIRED")
    if definition.flow_key == "request_complement":
        current_draft = db.session.execute(
            select(WhatsAppRequestDraft).where(
                WhatsAppRequestDraft.tenant_id == conversation.tenant_id,
                WhatsAppRequestDraft.conversation_id == conversation.id,
            )
        ).scalar_one_or_none()
        if current_draft is None:
            raise WhatsAppFlowError("FLOW_DRAFT_REQUIRED")
        values = {
            "assunto": values.get("assunto") or current_draft.title,
            "descricao": values.get("descricao") or current_draft.description,
            "local": values.get("local") or current_draft.address,
            "categoria_id": values.get("categoria_id")
            or (str(current_draft.category_id) if current_draft.category_id else None),
            "urgencia": values.get("urgencia") or current_draft.declared_urgency,
            "confirmado": values.get("confirmado"),
        }
    save_request_draft(
        conversation,
        contact,
        actor_id=actor_id,
        title=values.get("assunto"),
        description=values.get("descricao"),
        address=values.get("local"),
        category_id=(uuid.UUID(values["categoria_id"]) if values.get("categoria_id") else None),
        declared_urgency=values.get("urgencia"),
        actor_type="CITIZEN",
        origin="WHATSAPP_FLOW",
    )
    if not values.get("confirmado"):
        return None
    request_item, _, _ = confirm_request_draft(
        conversation,
        contact,
        actor_id=actor_id,
        idempotency_key=f"flow-{session.id}",
        confirmed=True,
        actor_type="CITIZEN",
        origin="WHATSAPP_FLOW",
    )
    return request_item.id


def _validate_launch_prerequisites(
    conversation: WhatsAppConversation,
    contact: WhatsAppContact,
    flow_key: str,
) -> None:
    privacy = db.session.execute(
        select(WhatsAppPrivacyRecord.id).where(
            WhatsAppPrivacyRecord.tenant_id == conversation.tenant_id,
            WhatsAppPrivacyRecord.conversation_id == conversation.id,
            WhatsAppPrivacyRecord.action == "ACKNOWLEDGED",
        )
    ).scalar_one_or_none()
    if privacy is None:
        raise WhatsAppFlowError("Registre a privacidade antes de iniciar o Flow.")
    if flow_key != "citizen_registration" and contact.citizen_id is None:
        raise WhatsAppFlowError("Identifique o cidadao antes de iniciar este Flow.")


def _reject_submission(
    submission: WhatsAppFlowSubmission, error_code: str
) -> WhatsAppFlowSubmission:
    submission.values = _minimized_submission_values(submission.values)
    submission.status = "REJECTED"
    submission.error_code = error_code[:80]
    submission.processed_at = datetime.now(UTC)
    return submission


def _minimized_submission_values(values: dict) -> dict:
    return {
        "fieldNames": sorted(str(key) for key in values),
        "redacted": True,
    }


def _reject_without_session(
    event: WhatsAppWebhookEvent,
    conversation: WhatsAppConversation,
    error_code: str,
) -> None:
    event.last_error_code = error_code
    db.session.add(
        OutboxEvent(
            tenant_id=conversation.tenant_id,
            event_type="WhatsappFlowRejected",
            aggregate_type="whatsapp_conversation",
            aggregate_id=str(conversation.id),
            payload={
                "conversationId": str(conversation.id),
                "webhookEventId": str(event.id),
                "errorCode": error_code,
            },
        )
    )


def _assert_conversation_active(
    conversation: WhatsAppConversation, contact: WhatsAppContact
) -> None:
    if (
        conversation.state in TERMINAL_STATES
        or contact.opt_status != WhatsAppContactOptStatus.ACTIVE
    ):
        raise WhatsAppFlowError("Conversa encerrada nao permite iniciar Flow.")


def _flow_key(value: str) -> str:
    result = str(value or "").strip().lower()
    if result not in FLOW_KEYS:
        raise WhatsAppFlowError("Tipo de Flow invalido.")
    return result


def _environment(value: str) -> str:
    result = str(value or "SANDBOX").strip().upper()
    if result not in FLOW_ENVIRONMENTS:
        raise WhatsAppFlowError("Ambiente de Flow invalido.")
    return result


def _definition_hash(schema: dict, definition: dict) -> str:
    payload = json.dumps(
        {"schema": schema, "definition": definition},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    return hashlib.sha256(payload.encode()).hexdigest()


def _response_hash(session_id: uuid.UUID, values: dict) -> str:
    payload = json.dumps(values, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(f"{session_id}:{payload}".encode()).hexdigest()


def _token_hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _error_code(error: Exception) -> str:
    message = str(error).strip().upper().replace(" ", "_")
    return re.sub(r"[^A-Z0-9_]", "", message)[:80] or "FLOW_REJECTED"


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
