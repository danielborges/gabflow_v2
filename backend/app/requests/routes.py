import hashlib
import math
import secrets
import uuid
from datetime import UTC, datetime, timedelta

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt, get_jwt_identity, jwt_required
from sqlalchemy import func, or_, select

from app.ai.service import enqueue_triage_execution, execution_data, latest_triage_execution
from app.communications.service import scheduled_return_data
from app.extensions import db
from app.models import (
    Citizen,
    ExternalAgency,
    InteractionDirection,
    InteractionVisibility,
    NotificationType,
    Organization,
    OutboxEvent,
    RequestCategory,
    RequestHistory,
    RequestInteraction,
    RequestStatus,
    ServiceRequest,
    Territory,
    User,
    UserStatus,
)
from app.notifications.service import notify_user
from app.operations.routes import contact_attempt_data, forwarding_data
from app.requests.operations import attachment_data, task_data
from app.requests.service import (
    RequestValidationError,
    apply_update,
    creation_event,
    next_protocol,
    record_audit,
    validate_create,
)

requests_bp = Blueprint("requests", __name__)


def _context() -> tuple[uuid.UUID, uuid.UUID]:
    return uuid.UUID(get_jwt()["tenant_id"]), uuid.UUID(get_jwt_identity())


def _get_request_or_404(request_id: uuid.UUID, tenant_id: uuid.UUID) -> ServiceRequest | None:
    service_request = db.session.execute(
        select(ServiceRequest).where(
            ServiceRequest.id == request_id,
            ServiceRequest.tenant_id == tenant_id,
        )
    ).scalar_one_or_none()
    if service_request is None:
        return None
    return service_request


def _serialize(service_request: ServiceRequest, include_details: bool = False) -> dict:
    data = {
        "id": str(service_request.id),
        "protocolo": service_request.protocol,
        "origem": service_request.source.value,
        "titulo": service_request.title,
        "descricao": service_request.description,
        "status": service_request.status.value,
        "prioridade": service_request.priority.value,
        "categoria": service_request.category,
        "categoriaId": str(service_request.category_id) if service_request.category_id else None,
        "subcategoria": service_request.subcategory,
        "tema": service_request.theme,
        "territorioId": str(service_request.territory_id) if service_request.territory_id else None,
        "orgaoId": str(service_request.agency_id) if service_request.agency_id else None,
        "impacto": service_request.impact,
        "urgencia": service_request.urgency,
        "cidadaoId": str(service_request.citizen_id) if service_request.citizen_id else None,
        "organizacaoId": (
            str(service_request.organization_id) if service_request.organization_id else None
        ),
        "endereco": service_request.address,
        "latitude": service_request.latitude,
        "longitude": service_request.longitude,
        "responsavelId": (
            str(service_request.responsible_id) if service_request.responsible_id else None
        ),
        "prazo": service_request.due_at.isoformat() if service_request.due_at else None,
        "situacaoSla": _sla_status(service_request),
        "grupoDuplicidadeId": (
            str(service_request.duplicate_group_id) if service_request.duplicate_group_id else None
        ),
        "motivoEncerramento": service_request.closing_reason,
        "evidenciaEncerramento": service_request.closing_evidence,
        "encerradaEm": (
            service_request.closed_at.isoformat() if service_request.closed_at else None
        ),
        "criadaEm": service_request.created_at.isoformat(),
        "atualizadaEm": service_request.updated_at.isoformat(),
    }
    if include_details:
        data["interacoes"] = [
            {
                "id": str(item.id),
                "tipo": item.interaction_type,
                "canal": item.channel,
                "direcao": item.direction.value,
                "conteudo": item.content,
                "visibilidade": item.visibility.value,
                "autorId": str(item.author_id),
                "criadaEm": item.created_at.isoformat(),
            }
            for item in service_request.interactions
        ]
        data["historico"] = [
            {
                "id": str(item.id),
                "acao": item.action,
                "alteracoes": item.changes,
                "usuarioId": str(item.user_id),
                "criadaEm": item.created_at.isoformat(),
            }
            for item in service_request.history
        ]
        data["tarefas"] = [task_data(item) for item in service_request.tasks]
        data["anexos"] = [attachment_data(item) for item in service_request.attachments]
        data["duplicidades"] = _duplicate_requests(service_request)
        data["encaminhamentos"] = [forwarding_data(item) for item in service_request.forwardings]
        data["tentativasContato"] = [
            contact_attempt_data(item) for item in service_request.contact_attempts
        ]
        data["retornos"] = [
            scheduled_return_data(item) for item in service_request.scheduled_returns
        ]
        data["triagemIA"] = execution_data(
            latest_triage_execution(service_request.tenant_id, service_request.id)
        )
    return data


@requests_bp.get("/solicitacoes")
@jwt_required()
def list_requests():
    tenant_id, _ = _context()
    page = max(request.args.get("page", default=0, type=int), 0)
    size = min(max(request.args.get("size", default=20, type=int), 1), 100)
    status = request.args.get("status", type=str)
    search = request.args.get("q", type=str)

    filters = [ServiceRequest.tenant_id == tenant_id]
    if status:
        try:
            filters.append(ServiceRequest.status == RequestStatus(status.upper()))
        except ValueError:
            return jsonify(error="validation_error", message="Status inválido."), 422
    if search and search.strip():
        pattern = f"%{search.strip()}%"
        filters.append(
            or_(
                ServiceRequest.protocol.ilike(pattern),
                ServiceRequest.title.ilike(pattern),
                ServiceRequest.description.ilike(pattern),
            )
        )

    total = db.session.execute(select(func.count(ServiceRequest.id)).where(*filters)).scalar_one()
    items = db.session.execute(
        select(ServiceRequest)
        .where(*filters)
        .order_by(ServiceRequest.created_at.desc())
        .offset(page * size)
        .limit(size)
    ).scalars()

    return jsonify(
        content=[_serialize(item) for item in items],
        page=page,
        size=size,
        totalElements=total,
        totalPages=math.ceil(total / size) if total else 0,
    )


@requests_bp.post("/solicitacoes")
@jwt_required()
def create_request():
    tenant_id, user_id = _context()
    payload = request.get_json(silent=True) or {}
    try:
        values = validate_create(payload)
    except RequestValidationError as error:
        return jsonify(error="validation_error", message=str(error)), 422

    category = _tenant_entity(RequestCategory, payload.get("categoriaId"), tenant_id)
    citizen = _tenant_entity(Citizen, payload.get("cidadaoId"), tenant_id)
    organization = _tenant_entity(Organization, payload.get("organizacaoId"), tenant_id)
    territory = _tenant_entity(Territory, payload.get("territorioId"), tenant_id)
    agency = _tenant_entity(ExternalAgency, payload.get("orgaoId"), tenant_id)
    if payload.get("categoriaId") and category is None:
        return jsonify(error="validation_error", message="Categoria inválida."), 422
    if payload.get("cidadaoId") and citizen is None:
        return jsonify(error="validation_error", message="Cidadão inválido."), 422
    if payload.get("organizacaoId") and organization is None:
        return jsonify(error="validation_error", message="Organização inválida."), 422
    if payload.get("territorioId") and territory is None:
        return jsonify(error="validation_error", message="Território inválido."), 422
    if payload.get("orgaoId") and agency is None:
        return jsonify(error="validation_error", message="Órgão inválido."), 422

    responsible = _tenant_entity(User, payload.get("responsavelId"), tenant_id)
    if responsible and responsible.status != UserStatus.ACTIVE:
        responsible = None
    if payload.get("responsavelId") and responsible is None:
        return jsonify(error="validation_error", message="Responsável inválido."), 422

    now = datetime.now(UTC)
    public_key = secrets.token_urlsafe(24)
    service_request = ServiceRequest(
        tenant_id=tenant_id,
        created_by_id=user_id,
        protocol=next_protocol(tenant_id),
        category_id=category.id if category else None,
        citizen_id=citizen.id if citizen else None,
        organization_id=organization.id if organization else None,
        territory_id=territory.id if territory else None,
        agency_id=agency.id if agency else None,
        responsible_id=responsible.id if responsible else None,
        due_at=now + timedelta(hours=category.sla_hours) if category else None,
        public_access_key_hash=hashlib.sha256(public_key.encode()).hexdigest(),
        **values,
    )
    if category:
        service_request.category = category.name
    db.session.add(service_request)
    db.session.flush()
    service_request.history.append(_creation_history(service_request, user_id))
    db.session.add(creation_event(service_request))
    if category is None:
        enqueue_triage_execution(service_request, user_id)
    notify_user(
        tenant_id,
        service_request.responsible_id,
        NotificationType.ATRIBUICAO,
        "Solicitação atribuída",
        f"A solicitação {service_request.protocol} foi atribuída a você.",
        "service_request",
        service_request.id,
    )
    record_audit(
        service_request,
        user_id,
        "request.created",
        before=None,
        after={"protocolo": service_request.protocol, "status": service_request.status.value},
    )
    db.session.commit()
    response = _serialize(service_request, include_details=True)
    response["chaveAcompanhamento"] = public_key
    return jsonify(response), 201


@requests_bp.get("/solicitacoes/<uuid:request_id>")
@jwt_required()
def get_request(request_id: uuid.UUID):
    tenant_id, _ = _context()
    service_request = _get_request_or_404(request_id, tenant_id)
    if service_request is None:
        return jsonify(error="resource_not_found", message="Solicitação não encontrada."), 404
    return jsonify(_serialize(service_request, include_details=True))


@requests_bp.patch("/solicitacoes/<uuid:request_id>")
@jwt_required()
def update_request(request_id: uuid.UUID):
    tenant_id, user_id = _context()
    service_request = _get_request_or_404(request_id, tenant_id)
    if service_request is None:
        return jsonify(error="resource_not_found", message="Solicitação não encontrada."), 404

    payload = request.get_json(silent=True) or {}
    relationship_changes = {}
    before_assignment = service_request.responsible_id
    assignment_changed = False
    if "responsavelId" in payload:
        responsible = _tenant_entity(User, payload.get("responsavelId"), tenant_id)
        if payload.get("responsavelId") and (
            responsible is None or responsible.status != UserStatus.ACTIVE
        ):
            return jsonify(error="validation_error", message="Responsável inválido."), 422
        service_request.responsible_id = responsible.id if responsible else None
        assignment_changed = before_assignment != service_request.responsible_id

    if "categoriaId" in payload:
        old_category_id = service_request.category_id
        category = _tenant_entity(RequestCategory, payload.get("categoriaId"), tenant_id)
        if payload.get("categoriaId") and category is None:
            return jsonify(error="validation_error", message="Categoria inválida."), 422
        service_request.category_id = category.id if category else None
        service_request.category = category.name if category else None
        service_request.due_at = (
            service_request.created_at + timedelta(hours=category.sla_hours) if category else None
        )
        if old_category_id != service_request.category_id:
            relationship_changes["category_id"] = {
                "antes": str(old_category_id) if old_category_id else None,
                "depois": str(service_request.category_id) if service_request.category_id else None,
            }

    for field_name, model, attribute, label in (
        ("cidadaoId", Citizen, "citizen_id", "Cidadão"),
        ("organizacaoId", Organization, "organization_id", "Organização"),
        ("territorioId", Territory, "territory_id", "Território"),
        ("orgaoId", ExternalAgency, "agency_id", "Órgão"),
    ):
        if field_name in payload:
            old_value = getattr(service_request, attribute)
            entity = _tenant_entity(model, payload.get(field_name), tenant_id)
            if payload.get(field_name) and entity is None:
                return jsonify(error="validation_error", message=f"{label} inválido."), 422
            setattr(service_request, attribute, entity.id if entity else None)
            new_value = getattr(service_request, attribute)
            if old_value != new_value:
                relationship_changes[attribute] = {
                    "antes": str(old_value) if old_value else None,
                    "depois": str(new_value) if new_value else None,
                }

    try:
        changes = apply_update(service_request, payload, user_id)
    except RequestValidationError as error:
        return jsonify(error="validation_error", message=str(error)), 422

    if assignment_changed:
        assignment_change = {
            "antes": str(before_assignment) if before_assignment else None,
            "depois": (
                str(service_request.responsible_id) if service_request.responsible_id else None
            ),
        }
        changes["responsible_id"] = assignment_change
        service_request.history.append(
            RequestHistory(
                tenant_id=tenant_id,
                user_id=user_id,
                action="request.responsible.changed",
                changes={"responsible_id": assignment_change},
            )
        )
        notify_user(
            tenant_id,
            service_request.responsible_id,
            NotificationType.ATRIBUICAO,
            "Solicitação atribuída",
            f"A solicitação {service_request.protocol} foi atribuída a você.",
            "service_request",
            service_request.id,
        )

    if relationship_changes:
        changes.update(relationship_changes)
        service_request.history.append(
            RequestHistory(
                tenant_id=tenant_id,
                user_id=user_id,
                action="request.relationships.changed",
                changes=relationship_changes,
            )
        )

    if changes:
        before = {key: value["antes"] for key, value in changes.items()}
        after = {key: value["depois"] for key, value in changes.items()}
        record_audit(service_request, user_id, "request.updated", before, after)
        db.session.add(
            OutboxEvent(
                tenant_id=tenant_id,
                event_type="SolicitacaoAtualizada",
                aggregate_type="Solicitacao",
                aggregate_id=str(service_request.id),
                payload={
                    "id": str(service_request.id),
                    "tenantId": str(tenant_id),
                    "alteracoes": after,
                },
            )
        )
        db.session.commit()
    return jsonify(_serialize(service_request, include_details=True))


@requests_bp.post("/solicitacoes/<uuid:request_id>/interacoes")
@jwt_required()
def create_interaction(request_id: uuid.UUID):
    tenant_id, user_id = _context()
    service_request = _get_request_or_404(request_id, tenant_id)
    if service_request is None:
        return jsonify(error="resource_not_found", message="Solicitação não encontrada."), 404

    payload = request.get_json(silent=True) or {}
    content = str(payload.get("conteudo", "")).strip()
    interaction_type = str(payload.get("tipo", "")).strip()
    channel = str(payload.get("canal", "")).strip()
    if not content or not interaction_type or not channel:
        return (
            jsonify(
                error="validation_error",
                message="Informe tipo, canal e conteúdo da interação.",
            ),
            422,
        )

    try:
        direction = InteractionDirection(str(payload.get("direcao", "")).upper())
        visibility = InteractionVisibility(str(payload.get("visibilidade", "INTERNA")).upper())
    except ValueError:
        return jsonify(error="validation_error", message="Direção ou visibilidade inválida."), 422

    interaction = RequestInteraction(
        tenant_id=tenant_id,
        request_id=service_request.id,
        interaction_type=interaction_type,
        channel=channel,
        direction=direction,
        content=content,
        visibility=visibility,
        author_id=user_id,
    )
    db.session.add(interaction)
    db.session.flush()
    record_audit(
        service_request,
        user_id,
        "request.interaction.created",
        before=None,
        after={"interacaoId": str(interaction.id), "direcao": direction.value},
    )
    db.session.commit()
    return jsonify(_serialize(service_request, include_details=True)), 201


def _creation_history(service_request: ServiceRequest, user_id: uuid.UUID):
    return RequestHistory(
        tenant_id=service_request.tenant_id,
        user_id=user_id,
        action="request.created",
        changes={
            "protocolo": {"antes": None, "depois": service_request.protocol},
            "status": {"antes": None, "depois": service_request.status.value},
        },
    )


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


def _sla_status(service_request: ServiceRequest) -> str | None:
    if service_request.due_at is None:
        return None
    due_at = _as_utc(service_request.due_at)
    closed_at = _as_utc(service_request.closed_at)
    if closed_at:
        return "CONCLUIDO_NO_PRAZO" if closed_at <= due_at else "CONCLUIDO_ATRASADO"
    remaining = due_at - datetime.now(UTC)
    if remaining.total_seconds() < 0:
        return "ATRASADO"
    if remaining.total_seconds() <= 24 * 3600:
        return "PROXIMO_DO_PRAZO"
    return "NO_PRAZO"


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def _duplicate_requests(service_request: ServiceRequest) -> list[dict]:
    if service_request.duplicate_group_id is None:
        return []
    items = db.session.execute(
        select(ServiceRequest)
        .where(
            ServiceRequest.tenant_id == service_request.tenant_id,
            ServiceRequest.duplicate_group_id == service_request.duplicate_group_id,
            ServiceRequest.id != service_request.id,
        )
        .order_by(ServiceRequest.created_at)
    ).scalars()
    return [
        {
            "id": str(item.id),
            "protocolo": item.protocol,
            "titulo": item.title,
            "status": item.status.value,
        }
        for item in items
    ]
