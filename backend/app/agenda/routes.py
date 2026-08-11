import uuid
from datetime import UTC, date, datetime, time, timedelta
from io import BytesIO
from zoneinfo import ZoneInfo

from flask import Blueprint, jsonify, request, send_file
from flask_jwt_extended import get_jwt, get_jwt_identity, jwt_required
from sqlalchemy import select

from app.audit import add_audit
from app.agenda.exports import weekly_agenda_pdf
from app.extensions import db
from app.models import (
    AgendaEvent,
    AgendaEventStatus,
    AgendaEventType,
    Citizen,
    Organization,
    RequestSource,
    RequestStatus,
    Role,
    ServiceRequest,
    Tenant,
    Territory,
    User,
    UserStatus,
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


@agenda_bp.get("/agenda/participantes")
@jwt_required()
def list_participants():
    tenant_id, _ = _context()
    users = db.session.execute(
        select(User).where(
            User.tenant_id == tenant_id,
            User.status == UserStatus.ACTIVE,
            User.role.in_({Role.ADMIN, Role.MANAGER, Role.STAFF}),
        ).order_by(User.name)
    ).scalars()
    return jsonify(content=[{
        "id": str(item.id),
        "nome": item.name,
        "perfil": item.role.value,
    } for item in users])


@agenda_bp.get("/agenda/relatorio-semanal.pdf")
@jwt_required()
def weekly_report():
    tenant_id, user_id = _context()
    tenant = db.session.get(Tenant, tenant_id)
    user = db.session.get(User, user_id)
    try:
        reference_date = date.fromisoformat(str(request.args.get("data") or date.today()))
    except ValueError:
        return jsonify(error="validation_error", message="Data de referência inválida."), 422
    timezone = ZoneInfo(tenant.timezone or "America/Sao_Paulo")
    week_start_date = reference_date - timedelta(days=reference_date.weekday())
    starts_at = datetime.combine(week_start_date, time.min, tzinfo=timezone)
    next_week = starts_at + timedelta(days=7)
    events = list(db.session.execute(
        select(AgendaEvent).where(
            AgendaEvent.tenant_id == tenant_id,
            AgendaEvent.starts_at >= starts_at,
            AgendaEvent.starts_at < next_week,
            AgendaEvent.status != AgendaEventStatus.CANCELADO,
        ).order_by(AgendaEvent.starts_at)
    ).scalars())
    for event in events:
        db.session.expunge(event)
        event.starts_at = _aware(event.starts_at).astimezone(timezone)
        if event.ends_at:
            event.ends_at = _aware(event.ends_at).astimezone(timezone)
    content = weekly_agenda_pdf(
        tenant,
        events,
        starts_at,
        next_week - timedelta(days=1),
        user.name if user else "Usuário do gabinete",
    )
    return send_file(
        BytesIO(content),
        mimetype="application/pdf",
        as_attachment=True,
        download_name=f"agenda-executiva-{week_start_date.isoformat()}.pdf",
    )


@agenda_bp.post("/agenda/compromissos")
@jwt_required()
def create_event():
    tenant_id, user_id = _context()
    payload = request.get_json(silent=True) or {}
    try:
        values = _event_values(payload, tenant_id)
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
    if "tipo" in payload:
        try:
            event.event_type = AgendaEventType(str(payload["tipo"]).upper())
        except ValueError:
            return jsonify(error="validation_error", message="Tipo de compromisso inválido."), 422
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
    if event.ends_at and event.ends_at <= event.starts_at:
        return (
            jsonify(
                error="validation_error",
                message="A data final deve ser posterior à data inicial.",
            ),
            422,
        )
    if "presencaParlamentar" in payload:
        try:
            event.representative_presence = _boolean_value(
                payload["presencaParlamentar"], "presencaParlamentar"
            )
        except ValueError as error:
            return jsonify(error="validation_error", message=str(error)), 422
    if "participanteIds" in payload:
        try:
            event.participants = _participant_values(payload, tenant_id)
        except ValueError as error:
            return jsonify(error="validation_error", message=str(error)), 422
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
        "presencaParlamentar": item.representative_presence,
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


def _event_values(payload: dict, tenant_id: uuid.UUID) -> dict:
    title = str(payload.get("titulo", "")).strip()
    if len(title) < 3:
        raise ValueError("Informe o título do compromisso.")
    try:
        event_type = AgendaEventType(str(payload.get("tipo", "COMPROMISSO")).upper())
        starts_at = _parse_datetime(payload.get("inicio"), "Informe a data de início.")
    except ValueError as error:
        raise ValueError(str(error)) from error
    ends_at = _optional_datetime(payload.get("fim"))
    if ends_at and ends_at <= starts_at:
        raise ValueError("A data final deve ser posterior à data inicial.")
    return {
        "event_type": event_type,
        "title": title,
        "description": str(payload.get("descricao", "")).strip() or None,
        "location": str(payload.get("local", "")).strip() or None,
        "starts_at": starts_at,
        "ends_at": ends_at,
        "representative_presence": _boolean_value(
            payload.get("presencaParlamentar", False), "presencaParlamentar"
        ),
        "participants": _participant_values(payload, tenant_id),
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


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def _list_value(value, label: str) -> list:
    if value in (None, ""):
        return []
    if not isinstance(value, list):
        raise ValueError(f"{label} deve ser uma lista.")
    return value


def _participant_values(payload: dict, tenant_id: uuid.UUID) -> list:
    if "participanteIds" not in payload:
        return _list_value(payload.get("participantes", []), "participantes")
    raw_ids = payload.get("participanteIds")
    if not isinstance(raw_ids, list):
        raise ValueError("participanteIds deve ser uma lista.")
    participant_ids = []
    for value in raw_ids:
        try:
            participant_id = uuid.UUID(str(value))
        except (TypeError, ValueError) as error:
            raise ValueError("Selecione participantes válidos.") from error
        if participant_id not in participant_ids:
            participant_ids.append(participant_id)
    if not participant_ids:
        return []
    users = list(db.session.execute(
        select(User).where(
            User.tenant_id == tenant_id,
            User.id.in_(participant_ids),
            User.status == UserStatus.ACTIVE,
            User.role.in_({Role.ADMIN, Role.MANAGER, Role.STAFF}),
        )
    ).scalars())
    users_by_id = {item.id: item for item in users}
    if len(users_by_id) != len(participant_ids):
        raise ValueError("Um ou mais participantes não são funcionários ativos do gabinete.")
    return [
        {
            "id": str(user_id),
            "nome": users_by_id[user_id].name,
            "perfil": users_by_id[user_id].role.value,
        }
        for user_id in participant_ids
    ]


def _boolean_value(value, label: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{label} deve ser verdadeiro ou falso.")
    return value
