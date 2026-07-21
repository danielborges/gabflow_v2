import uuid
from datetime import UTC, datetime

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt, get_jwt_identity, jwt_required
from sqlalchemy import select

from app.audit import add_audit
from app.extensions import db
from app.models import (
    AgendaEvent,
    AgendaEventStatus,
    AgendaEventType,
    Citizen,
    Organization,
    RequestSource,
    RequestStatus,
    ServiceRequest,
    Territory,
)
from app.requests.service import creation_event, next_protocol

agenda_bp = Blueprint("agenda", __name__)
CLOSED_STATUSES = {
    RequestStatus.RESOLVIDA,
    RequestStatus.ENCERRADA,
    RequestStatus.CANCELADA,
}


def _context() -> tuple[uuid.UUID, uuid.UUID]:
    return uuid.UUID(get_jwt()["tenant_id"]), uuid.UUID(get_jwt_identity())


@agenda_bp.get("/agenda/compromissos")
@jwt_required()
def list_events():
    tenant_id, _ = _context()
    status = request.args.get("status", type=str)
    filters = [AgendaEvent.tenant_id == tenant_id]
    if status:
        try:
            filters.append(AgendaEvent.status == AgendaEventStatus(status.upper()))
        except ValueError:
            return jsonify(error="validation_error", message="Status inválido."), 422
    items = db.session.execute(
        select(AgendaEvent).where(*filters).order_by(AgendaEvent.starts_at.desc())
    ).scalars()
    return jsonify(content=[event_data(item) for item in items])


@agenda_bp.post("/agenda/compromissos")
@jwt_required()
def create_event():
    tenant_id, user_id = _context()
    payload = request.get_json(silent=True) or {}
    try:
        values = _event_values(payload)
    except ValueError as error:
        return jsonify(error="validation_error", message=str(error)), 422
    relationships = _event_relationships(payload, tenant_id)
    if isinstance(relationships, tuple):
        return relationships
    event = AgendaEvent(
        tenant_id=tenant_id,
        created_by_id=user_id,
        **values,
        **relationships,
    )
    db.session.add(event)
    db.session.flush()
    add_audit(
        tenant_id,
        user_id,
        "agenda.event.created",
        "agenda_event",
        event.id,
        after=event_data(event),
    )
    db.session.commit()
    return jsonify(event_data(event)), 201


@agenda_bp.get("/agenda/roteiros-visita")
@jwt_required()
def suggest_visit_routes():
    tenant_id, _ = _context()
    territories = {
        item.id: item.name
        for item in db.session.execute(
            select(Territory).where(Territory.tenant_id == tenant_id)
        ).scalars()
    }
    requests = list(
        db.session.execute(
            select(ServiceRequest)
            .where(
                ServiceRequest.tenant_id == tenant_id,
                ServiceRequest.status.not_in(CLOSED_STATUSES),
            )
            .order_by(ServiceRequest.created_at.desc())
        ).scalars()
    )
    groups = {}
    for item in requests:
        key = str(item.territory_id) if item.territory_id else item.address or "sem-territorio"
        name = territories.get(item.territory_id) or item.address or "Sem território"
        group = groups.setdefault(
            key,
            {
                "territorioId": str(item.territory_id) if item.territory_id else None,
                "territorio": name,
                "totalDemandas": 0,
                "prioridadeAlta": 0,
                "solicitacoes": [],
            },
        )
        group["totalDemandas"] += 1
        if item.priority.value in {"ALTA", "CRITICA"}:
            group["prioridadeAlta"] += 1
        if len(group["solicitacoes"]) < 5:
            group["solicitacoes"].append(
                {
                    "id": str(item.id),
                    "protocolo": item.protocol,
                    "titulo": item.title or "Sem título",
                    "prioridade": item.priority.value,
                }
            )
    suggestions = sorted(
        groups.values(),
        key=lambda value: (value["prioridadeAlta"], value["totalDemandas"]),
        reverse=True,
    )[:8]
    for item in suggestions:
        item["justificativa"] = (
            f"{item['totalDemandas']} demanda(s) aberta(s), "
            f"{item['prioridadeAlta']} de alta prioridade."
        )
    return jsonify(content=suggestions)


@agenda_bp.get("/agenda/compromissos/<uuid:event_id>")
@jwt_required()
def get_event(event_id: uuid.UUID):
    tenant_id, _ = _context()
    event = _event_or_none(event_id, tenant_id)
    if event is None:
        return jsonify(error="resource_not_found", message="Compromisso não encontrado."), 404
    return jsonify(event_data(event))


@agenda_bp.patch("/agenda/compromissos/<uuid:event_id>")
@jwt_required()
def update_event(event_id: uuid.UUID):
    tenant_id, user_id = _context()
    event = _event_or_none(event_id, tenant_id)
    if event is None:
        return jsonify(error="resource_not_found", message="Compromisso não encontrado."), 404
    payload = request.get_json(silent=True) or {}
    before = event_data(event)
    if "status" in payload:
        try:
            event.status = AgendaEventStatus(str(payload["status"]).upper())
        except ValueError:
            return jsonify(error="validation_error", message="Status inválido."), 422
    for field_name, attr in (
        ("titulo", "title"),
        ("descricao", "description"),
        ("local", "location"),
        ("ata", "minutes"),
    ):
        if field_name in payload:
            value = str(payload[field_name]).strip()
            setattr(event, attr, value or None)
    if "inicio" in payload:
        try:
            event.starts_at = _parse_datetime(payload["inicio"], "Informe a data de início.")
        except ValueError as error:
            return jsonify(error="validation_error", message=str(error)), 422
    if "fim" in payload:
        event.ends_at = _optional_datetime(payload["fim"])
    for field_name, attr in (
        ("fotos", "photos"),
        ("participantes", "participants"),
        ("pendencias", "pending_items"),
    ):
        if field_name in payload:
            try:
                setattr(event, attr, _list_value(payload[field_name], field_name))
            except ValueError as error:
                return jsonify(error="validation_error", message=str(error)), 422
    after = event_data(event)
    add_audit(tenant_id, user_id, "agenda.event.updated", "agenda_event", event.id, before, after)
    db.session.commit()
    return jsonify(after)


@agenda_bp.post("/agenda/compromissos/<uuid:event_id>/registro")
@jwt_required()
def record_event(event_id: uuid.UUID):
    tenant_id, user_id = _context()
    event = _event_or_none(event_id, tenant_id)
    if event is None:
        return jsonify(error="resource_not_found", message="Compromisso não encontrado."), 404
    payload = request.get_json(silent=True) or {}
    minutes = str(payload.get("ata", "")).strip()
    if len(minutes) < 3:
        return (
            jsonify(error="validation_error", message="Informe a ata ou registro da visita."),
            422,
        )
    before = event_data(event)
    event.minutes = minutes
    try:
        event.photos = _list_value(payload.get("fotos", event.photos), "fotos")
        event.participants = _list_value(
            payload.get("participantes", event.participants),
            "participantes",
        )
        event.pending_items = _list_value(
            payload.get("pendencias", event.pending_items),
            "pendencias",
        )
    except ValueError as error:
        return jsonify(error="validation_error", message=str(error)), 422
    event.status = AgendaEventStatus.REALIZADO
    after = event_data(event)
    add_audit(tenant_id, user_id, "agenda.event.recorded", "agenda_event", event.id, before, after)
    db.session.commit()
    return jsonify(after)


@agenda_bp.post("/agenda/compromissos/<uuid:event_id>/solicitacoes")
@jwt_required()
def create_request_from_event(event_id: uuid.UUID):
    tenant_id, user_id = _context()
    event = _event_or_none(event_id, tenant_id)
    if event is None:
        return jsonify(error="resource_not_found", message="Compromisso não encontrado."), 404
    payload = request.get_json(silent=True) or {}
    title = str(payload.get("titulo") or f"Demanda originada de {event.title}").strip()
    description = str(payload.get("descricao") or event.minutes or event.description or "").strip()
    if len(title) < 3 or len(description) < 10:
        return (
            jsonify(error="validation_error", message="Informe título e descrição da solicitação."),
            422,
        )
    service_request = ServiceRequest(
        tenant_id=tenant_id,
        created_by_id=user_id,
        protocol=next_protocol(tenant_id),
        source=RequestSource.VISITA,
        title=title,
        description=description,
        address=event.location,
        citizen_id=event.citizen_id,
        organization_id=event.organization_id,
        territory_id=event.territory_id,
    )
    db.session.add(service_request)
    db.session.flush()
    db.session.add(creation_event(service_request))
    event.request_id = service_request.id
    add_audit(
        tenant_id,
        user_id,
        "agenda.event.request.created",
        "service_request",
        service_request.id,
        after={"agendaEventoId": str(event.id), "protocolo": service_request.protocol},
    )
    db.session.commit()
    return jsonify({"id": str(service_request.id), "protocolo": service_request.protocol}), 201


def event_data(item: AgendaEvent) -> dict:
    return {
        "id": str(item.id),
        "tipo": item.event_type.value,
        "status": item.status.value,
        "titulo": item.title,
        "descricao": item.description,
        "local": item.location,
        "inicio": item.starts_at.isoformat(),
        "fim": item.ends_at.isoformat() if item.ends_at else None,
        "cidadaoId": str(item.citizen_id) if item.citizen_id else None,
        "organizacaoId": str(item.organization_id) if item.organization_id else None,
        "territorioId": str(item.territory_id) if item.territory_id else None,
        "solicitacaoId": str(item.request_id) if item.request_id else None,
        "ata": item.minutes,
        "fotos": item.photos,
        "participantes": item.participants,
        "pendencias": item.pending_items,
        "criadoEm": item.created_at.isoformat(),
    }


def _event_values(payload: dict) -> dict:
    title = str(payload.get("titulo", "")).strip()
    if len(title) < 3:
        raise ValueError("Informe o título do compromisso.")
    try:
        event_type = AgendaEventType(str(payload.get("tipo", "COMPROMISSO")).upper())
        starts_at = _parse_datetime(payload.get("inicio"), "Informe a data de início.")
    except ValueError as error:
        raise ValueError(str(error)) from error
    return {
        "event_type": event_type,
        "title": title,
        "description": str(payload.get("descricao", "")).strip() or None,
        "location": str(payload.get("local", "")).strip() or None,
        "starts_at": starts_at,
        "ends_at": _optional_datetime(payload.get("fim")),
        "participants": _list_value(payload.get("participantes", []), "participantes"),
        "pending_items": _list_value(payload.get("pendencias", []), "pendencias"),
        "photos": _list_value(payload.get("fotos", []), "fotos"),
    }


def _event_relationships(payload: dict, tenant_id: uuid.UUID):
    relationships = {}
    for field_name, model, attr, label in (
        ("cidadaoId", Citizen, "citizen_id", "Cidadão"),
        ("organizacaoId", Organization, "organization_id", "Organização"),
        ("territorioId", Territory, "territory_id", "Território"),
        ("solicitacaoId", ServiceRequest, "request_id", "Solicitação"),
    ):
        entity = _tenant_entity(model, payload.get(field_name), tenant_id)
        if payload.get(field_name) and entity is None:
            return jsonify(error="validation_error", message=f"{label} inválido."), 422
        relationships[attr] = entity.id if entity else None
    return relationships


def _event_or_none(event_id: uuid.UUID, tenant_id: uuid.UUID) -> AgendaEvent | None:
    return db.session.execute(
        select(AgendaEvent).where(AgendaEvent.id == event_id, AgendaEvent.tenant_id == tenant_id)
    ).scalar_one_or_none()


def _tenant_entity(model, value, tenant_id: uuid.UUID):
    if not value:
        return None
    try:
        entity_id = uuid.UUID(str(value))
    except ValueError:
        return None
    return db.session.execute(
        select(model).where(model.id == entity_id, model.tenant_id == tenant_id)
    ).scalar_one_or_none()


def _parse_datetime(value, message: str) -> datetime:
    if not value:
        raise ValueError(message)
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError("Data inválida.") from error
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _optional_datetime(value) -> datetime | None:
    if not value:
        return None
    return _parse_datetime(value, "Data inválida.")


def _list_value(value, label: str) -> list:
    if value in (None, ""):
        return []
    if not isinstance(value, list):
        raise ValueError(f"{label} deve ser uma lista.")
    return value
