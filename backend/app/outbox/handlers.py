import uuid

from flask import current_app
from sqlalchemy import select

from app.ai.service import AI_TRIAGE_EVENT, execute_triage
from app.communications.email import EmailDeliveryError, send_email
from app.extensions import db
from app.models import (
    AIExecution,
    AIExecutionStatus,
    AuditLog,
    ContactAttempt,
    ContactAttemptOutcome,
    OutboxEvent,
    RequestHistory,
    ServiceRequest,
)

EMAIL_RESPONSE_EVENT = "RespostaEmailSolicitacao"


class NonRetryableEventError(RuntimeError):
    pass


def handle_event(event: OutboxEvent) -> None:
    if event.event_type == AI_TRIAGE_EVENT:
        execution = _ai_execution(event)
        execute_triage(execution)
        return
    if event.event_type == EMAIL_RESPONSE_EVENT:
        _send_request_email(event)
        return

    current_app.logger.info(
        "Published domain event type=%s id=%s tenant=%s aggregate=%s:%s",
        event.event_type,
        event.id,
        event.tenant_id,
        event.aggregate_type,
        event.aggregate_id,
    )


def handle_exhausted_event(event: OutboxEvent, error_message: str) -> None:
    if event.event_type == AI_TRIAGE_EVENT:
        execution = _ai_execution(event)
        execution.status = AIExecutionStatus.FALHOU
        execution.error = error_message[:2000]
        return
    if event.event_type != EMAIL_RESPONSE_EVENT:
        return

    payload = event.payload
    request_id = _uuid(payload, "requestId")
    user_id = _uuid(payload, "userId")
    service_request = db.session.get(ServiceRequest, request_id)
    if service_request is None or service_request.tenant_id != event.tenant_id:
        return
    if _contact_attempt(event.id) is not None:
        return

    attempt = ContactAttempt(
        tenant_id=event.tenant_id,
        request_id=request_id,
        citizen_id=service_request.citizen_id,
        channel="EMAIL",
        destination=str(payload["recipient"]),
        outcome=ContactAttemptOutcome.FALHOU,
        notes=error_message[:2000],
        created_by_id=user_id,
        source_event_id=event.id,
    )
    db.session.add(attempt)
    db.session.flush()
    details = {
        "canal": "EMAIL",
        "eventoId": str(event.id),
        "tentativaContatoId": str(attempt.id),
        "tentativas": event.attempt_count,
        "erro": error_message[:500],
    }
    _record_delivery_result(
        event,
        request_id,
        user_id,
        "request.response.failed",
        details,
    )


def _send_request_email(event: OutboxEvent) -> None:
    if _contact_attempt(event.id) is not None:
        return

    payload = event.payload
    request_id = _uuid(payload, "requestId")
    user_id = _uuid(payload, "userId")
    service_request = db.session.get(ServiceRequest, request_id)
    if service_request is None or service_request.tenant_id != event.tenant_id:
        raise NonRetryableEventError("Solicitação do evento não foi encontrada.")

    try:
        delivery = send_email(
            recipient=str(payload["recipient"]),
            subject=str(payload["subject"]),
            text=str(payload["text"]),
            idempotency_key=str(payload["idempotencyKey"]),
        )
    except EmailDeliveryError as error:
        if not error.retryable:
            raise NonRetryableEventError(str(error)) from error
        raise

    attempt = ContactAttempt(
        tenant_id=event.tenant_id,
        request_id=request_id,
        citizen_id=service_request.citizen_id,
        channel="EMAIL",
        destination=str(payload["recipient"]),
        outcome=ContactAttemptOutcome.REALIZADO,
        notes=f"Mensagem aceita pelo Resend. ID: {delivery.message_id}",
        created_by_id=user_id,
        source_event_id=event.id,
    )
    db.session.add(attempt)
    db.session.flush()
    details = {
        "canal": "EMAIL",
        "eventoId": str(event.id),
        "provedor": delivery.provider,
        "mensagemExternaId": delivery.message_id,
        "tentativaContatoId": str(attempt.id),
    }
    _record_delivery_result(
        event,
        request_id,
        user_id,
        "request.response.sent",
        details,
    )
    event.payload = {**payload, "delivery": details}


def _record_delivery_result(
    event: OutboxEvent,
    request_id: uuid.UUID,
    user_id: uuid.UUID,
    action: str,
    details: dict,
) -> None:
    db.session.add(
        RequestHistory(
            tenant_id=event.tenant_id,
            request_id=request_id,
            user_id=user_id,
            action=action,
            changes=details,
        )
    )
    db.session.add(
        AuditLog(
            tenant_id=event.tenant_id,
            user_id=user_id,
            action=action,
            entity_type="service_request",
            entity_id=str(request_id),
            after=details,
        )
    )


def _contact_attempt(event_id: uuid.UUID) -> ContactAttempt | None:
    return db.session.execute(
        select(ContactAttempt).where(ContactAttempt.source_event_id == event_id)
    ).scalar_one_or_none()


def _uuid(payload: dict, key: str) -> uuid.UUID:
    try:
        return uuid.UUID(str(payload[key]))
    except (KeyError, TypeError, ValueError) as error:
        raise NonRetryableEventError(f"Payload inválido: {key}.") from error


def _ai_execution(event: OutboxEvent) -> AIExecution:
    execution_id = _uuid(event.payload, "executionId")
    execution = db.session.get(AIExecution, execution_id)
    if execution is None or execution.tenant_id != event.tenant_id:
        raise NonRetryableEventError("Execução de IA não foi encontrada.")
    return execution
