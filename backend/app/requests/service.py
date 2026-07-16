import enum
import uuid
from datetime import UTC, datetime

from flask import request
from sqlalchemy import select

from app.extensions import db
from app.models import (
    AuditLog,
    OutboxEvent,
    RequestHistory,
    RequestPriority,
    RequestSource,
    RequestStatus,
    ServiceRequest,
    Tenant,
)

CLOSED_STATUSES = {
    RequestStatus.RESOLVIDA,
    RequestStatus.ENCERRADA,
    RequestStatus.CANCELADA,
}


class RequestValidationError(ValueError):
    pass


def next_protocol(tenant_id: uuid.UUID) -> str:
    tenant = db.session.execute(
        select(Tenant).where(Tenant.id == tenant_id).with_for_update()
    ).scalar_one()
    tenant.protocol_sequence += 1
    return f"GF-{datetime.now(UTC).year}-{tenant.protocol_sequence:06d}"


def validate_create(payload: dict) -> dict:
    description = str(payload.get("descricao", "")).strip()
    title = str(payload.get("titulo", "")).strip() or None
    source_value = str(payload.get("origem", "")).strip().upper()

    if len(description) < 3:
        raise RequestValidationError("A descrição deve possuir ao menos 3 caracteres.")
    if title and len(title) > 180:
        raise RequestValidationError("O título deve possuir no máximo 180 caracteres.")

    try:
        source = RequestSource(source_value)
    except ValueError as error:
        raise RequestValidationError("Origem inválida.") from error

    latitude = _optional_float(payload.get("latitude"), "Latitude")
    longitude = _optional_float(payload.get("longitude"), "Longitude")
    if latitude is not None and not -90 <= latitude <= 90:
        raise RequestValidationError("Latitude fora do intervalo permitido.")
    if longitude is not None and not -180 <= longitude <= 180:
        raise RequestValidationError("Longitude fora do intervalo permitido.")

    return {
        "source": source,
        "title": title,
        "description": description,
        "address": str(payload.get("endereco", "")).strip() or None,
        "latitude": latitude,
        "longitude": longitude,
        "category": str(payload.get("categoria", "")).strip() or None,
        "subcategory": str(payload.get("subcategoria", "")).strip() or None,
        "theme": str(payload.get("tema", "")).strip() or None,
        "impact": _level(payload.get("impacto"), "Impacto"),
        "urgency": _level(payload.get("urgencia"), "Urgência"),
    }


def apply_update(service_request: ServiceRequest, payload: dict, user_id: uuid.UUID) -> dict:
    allowed_text = {
        "titulo": ("title", 180),
        "descricao": ("description", None),
        "endereco": ("address", 500),
        "categoria": ("category", 100),
        "subcategoria": ("subcategory", 120),
        "tema": ("theme", 120),
        "motivoEncerramento": ("closing_reason", None),
        "evidenciaEncerramento": ("closing_evidence", None),
    }
    changes: dict = {}

    for api_name, (attribute, max_length) in allowed_text.items():
        if api_name not in payload:
            continue
        value = str(payload[api_name]).strip() or None
        if attribute == "description" and (value is None or len(value) < 3):
            raise RequestValidationError("A descrição deve possuir ao menos 3 caracteres.")
        if max_length and value and len(value) > max_length:
            raise RequestValidationError(f"{api_name} excede {max_length} caracteres.")
        _set_change(service_request, attribute, value, changes)

    if "prioridade" in payload:
        try:
            priority = RequestPriority(str(payload["prioridade"]).upper())
        except ValueError as error:
            raise RequestValidationError("Prioridade inválida.") from error
        _set_change(service_request, "priority", priority, changes)

    for api_name, attribute, label in (
        ("impacto", "impact", "Impacto"),
        ("urgencia", "urgency", "Urgência"),
    ):
        if api_name in payload:
            _set_change(service_request, attribute, _level(payload[api_name], label), changes)

    if "status" in payload:
        try:
            status = RequestStatus(str(payload["status"]).upper())
        except ValueError as error:
            raise RequestValidationError("Status inválido.") from error
        _validate_closing(service_request, status)
        _set_change(service_request, "status", status, changes)
        closed_at = datetime.now(UTC) if status in CLOSED_STATUSES else None
        _set_change(service_request, "closed_at", closed_at, changes)

    if changes:
        service_request.history.append(
            RequestHistory(
                tenant_id=service_request.tenant_id,
                user_id=user_id,
                action="request.updated",
                changes=changes,
            )
        )
    return changes


def record_audit(
    service_request: ServiceRequest,
    user_id: uuid.UUID,
    action: str,
    before: dict | None,
    after: dict | None,
) -> None:
    db.session.add(
        AuditLog(
            tenant_id=service_request.tenant_id,
            user_id=user_id,
            action=action,
            entity_type="service_request",
            entity_id=str(service_request.id),
            before=before,
            after=after,
            ip_address=request.remote_addr,
            user_agent=request.user_agent.string[:512],
        )
    )


def creation_event(service_request: ServiceRequest) -> OutboxEvent:
    return OutboxEvent(
        tenant_id=service_request.tenant_id,
        event_type="SolicitacaoCriada",
        aggregate_type="Solicitacao",
        aggregate_id=str(service_request.id),
        payload={
            "id": str(service_request.id),
            "tenantId": str(service_request.tenant_id),
            "protocolo": service_request.protocol,
            "status": service_request.status.value,
            "origem": service_request.source.value,
        },
    )


def _validate_closing(service_request: ServiceRequest, status: RequestStatus) -> None:
    if status not in CLOSED_STATUSES:
        return
    if not service_request.closing_reason:
        raise RequestValidationError("Informe o motivo do encerramento.")
    if status == RequestStatus.RESOLVIDA and not service_request.closing_evidence:
        raise RequestValidationError("Informe a evidência ou justificativa da resolução.")


def _set_change(entity, attribute: str, value, changes: dict) -> None:
    old_value = getattr(entity, attribute)
    if old_value == value:
        return
    changes[attribute] = {"antes": _json_value(old_value), "depois": _json_value(value)}
    setattr(entity, attribute, value)


def _json_value(value):
    if isinstance(value, enum.Enum):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def _optional_float(value, field_name: str) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError) as error:
        raise RequestValidationError(f"{field_name} inválida.") from error


def _level(value, field_name: str) -> str | None:
    if value in (None, ""):
        return None
    normalized = str(value).strip().upper()
    if normalized not in {"BAIXO", "MEDIO", "ALTO", "CRITICO"}:
        raise RequestValidationError(f"{field_name} inválido.")
    return normalized
