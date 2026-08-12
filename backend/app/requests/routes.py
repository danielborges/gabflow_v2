import hashlib
import math
import secrets
import uuid
from datetime import UTC, datetime, timedelta

from flask import Blueprint, current_app, jsonify, request
from flask_jwt_extended import get_jwt, get_jwt_identity, jwt_required
from sqlalchemy import func, or_, select

from app.ai.service import (
    enqueue_triage_execution,
    execution_data,
    latest_assistance_execution,
    latest_triage_execution,
)
from app.audit import add_audit
from app.auth.permissions import roles_required
from app.communications.service import scheduled_return_data
from app.extensions import db, limiter
from app.geocoding.benchmark import normalize_benchmark_geometry
from app.geocoding.contract import GeocodeQuery, GeocodeStatus
from app.geocoding.providers import GeoapifyAdapter, GeocodingProviderError
from app.models import (
    AuditLog,
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
    RequestPriority,
    RequestSource,
    RequestStatus,
    ServiceRequest,
    Tenant,
    Territory,
    User,
    UserStatus,
)
from app.notifications.service import notify_user
from app.operations.routes import contact_attempt_data, forwarding_data
from app.requests.access import can_distribute_requests, request_visibility_filters
from app.requests.operations import attachment_data, task_data
from app.requests.service import (
    RequestValidationError,
    apply_update,
    creation_event,
    new_public_protocol,
    next_protocol,
    record_audit,
    validate_create,
)
from app.territory_geometry import geometry_contains

requests_bp = Blueprint("requests", __name__)


def _context() -> tuple[uuid.UUID, uuid.UUID]:
    return uuid.UUID(get_jwt()["tenant_id"]), uuid.UUID(get_jwt_identity())


def _get_request_or_404(
    request_id: uuid.UUID, tenant_id: uuid.UUID, user_id: uuid.UUID
) -> ServiceRequest | None:
    service_request = db.session.execute(
        select(ServiceRequest).where(
            ServiceRequest.id == request_id,
            *request_visibility_filters(tenant_id, user_id),
        )
    ).scalar_one_or_none()
    if service_request is None:
        return None
    return service_request


def _serialize(service_request: ServiceRequest, include_details: bool = False) -> dict:
    data = {
        "id": str(service_request.id),
        "protocolo": service_request.protocol,
        "protocoloPublico": service_request.public_protocol,
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
        "qualidadeGeografica": {
            "origem": service_request.geocode_source,
            "metodo": service_request.geocode_method,
            "confianca": service_request.geocode_confidence,
            "verificada": service_request.geocode_verified,
            "status": service_request.geocode_status,
            "atualizadaEm": (
                service_request.geocoded_at.isoformat() if service_request.geocoded_at else None
            ),
            "atribuicoes": (
                ["Geoapify", "OpenStreetMap contributors"]
                if service_request.geocode_source == "GEOAPIFY"
                else []
            ),
            "revisaoPendente": (
                service_request.geocode_source == "GEOAPIFY"
                and service_request.geocode_method == "HOMOLOGATION_EXTERNAL"
                and not service_request.geocode_verified
            ),
        },
        "responsavelId": (
            str(service_request.responsible_id) if service_request.responsible_id else None
        ),
        "responsavel": service_request.responsible.name if service_request.responsible else None,
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
        data["geocodificacaoHomologacao"] = _geocoding_homologation_state(
            service_request.tenant_id
        )
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
        data["assistenciaIA"] = execution_data(
            latest_assistance_execution(service_request.tenant_id, service_request.id)
        )
    return data


def _geocoding_homologation_state(tenant_id: uuid.UUID) -> dict:
    environment = str(current_app.config.get("APP_ENV", "development")).lower()
    flag_enabled = bool(current_app.config.get("GEOCODING_HOMOLOGATION_ENABLED", False))
    credential_configured = bool(str(current_app.config.get("GEOAPIFY_API_KEY", "")).strip())
    allowed_environment = environment != "production"
    daily_limit = max(
        int(current_app.config.get("GEOCODING_HOMOLOGATION_DAILY_LIMIT", 100)), 0
    )
    starts_at = datetime.combine(datetime.now(UTC).date(), datetime.min.time(), tzinfo=UTC)
    used = db.session.execute(
        select(func.count(AuditLog.id)).where(
            AuditLog.tenant_id == tenant_id,
            AuditLog.action == "request.geocoding.geoapify.executed",
            AuditLog.created_at >= starts_at,
        )
    ).scalar_one()
    enabled = flag_enabled and credential_configured and allowed_environment
    role = str(get_jwt().get("role", "")).lower()
    unavailable_reason = None
    if not allowed_environment:
        unavailable_reason = "A integração de homologação é proibida em produção."
    elif not flag_enabled:
        unavailable_reason = "A feature flag de homologação está desabilitada."
    elif not credential_configured:
        unavailable_reason = "A credencial do Geoapify não está configurada."
    return {
        "habilitada": enabled,
        "podeOperar": enabled and role in {"admin", "manager"},
        "ambiente": environment,
        "provedor": "GEOAPIFY",
        "limiteDiario": daily_limit,
        "utilizadasHoje": used,
        "restantesHoje": max(daily_limit - used, 0),
        "motivoIndisponivel": unavailable_reason,
    }


def _homologation_bbox(tenant: Tenant) -> tuple[float, float, float, float] | None:
    bounds = tenant.jurisdiction_bounds
    if not isinstance(bounds, dict):
        return None
    try:
        return (
            float(bounds["minLongitude"]),
            float(bounds["minLatitude"]),
            float(bounds["maxLongitude"]),
            float(bounds["maxLatitude"]),
        )
    except (KeyError, TypeError, ValueError):
        return None


def _geocoding_feature_error(state: dict):
    if not state["habilitada"]:
        return jsonify(
            error="geocoding_homologation_disabled",
            message=state["motivoIndisponivel"] or "Integração indisponível.",
        ), 403
    if state["restantesHoje"] <= 0:
        return jsonify(
            error="geocoding_quota_exceeded",
            message="A cota diária de geocodificação do gabinete foi atingida.",
        ), 429
    return None


@requests_bp.get("/solicitacoes")
@jwt_required()
def list_requests():
    tenant_id, user_id = _context()
    page = max(request.args.get("page", default=0, type=int), 0)
    size = min(max(request.args.get("size", default=20, type=int), 1), 100)
    status = request.args.get("status", type=str)
    search = request.args.get("q", type=str)
    protocol = request.args.get("protocolo", type=str)
    request_search = request.args.get("solicitacao", type=str)
    source = request.args.get("origem", type=str)
    priority = request.args.get("prioridade", type=str)
    responsible = request.args.get("responsavel", type=str)
    category = request.args.get("categoria", type=str)
    territory_id = request.args.get("territorioId", type=str)
    agency_id = request.args.get("orgaoId", type=str)
    starts_on = request.args.get("inicio", type=str)
    ends_on = request.args.get("fim", type=str)
    without_territory = str(request.args.get("semTerritorio", "")).lower() == "true"
    sort = request.args.get("sort", default="criadaEm", type=str)
    direction = request.args.get("direction", default="desc", type=str).lower()

    filters = request_visibility_filters(tenant_id, user_id)
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
    if protocol and protocol.strip():
        filters.append(ServiceRequest.protocol.ilike(f"%{protocol.strip()}%"))
    if request_search and request_search.strip():
        pattern = f"%{request_search.strip()}%"
        filters.append(
            or_(
                ServiceRequest.title.ilike(pattern),
                ServiceRequest.description.ilike(pattern),
                ServiceRequest.category.ilike(pattern),
            )
        )
    if source:
        try:
            filters.append(ServiceRequest.source == RequestSource(source.upper()))
        except ValueError:
            return jsonify(error="validation_error", message="Origem inválida."), 422
    if priority:
        try:
            filters.append(ServiceRequest.priority == RequestPriority(priority.upper()))
        except ValueError:
            return jsonify(error="validation_error", message="Prioridade inválida."), 422
    if responsible and responsible.strip():
        filters.append(User.name.ilike(f"%{responsible.strip()}%"))
    if category and category.strip():
        filters.append(ServiceRequest.category == category.strip())
    try:
        if starts_on:
            start_date = datetime.fromisoformat(starts_on).date()
            filters.append(
                ServiceRequest.created_at
                >= datetime.combine(start_date, datetime.min.time(), tzinfo=UTC)
            )
        if ends_on:
            end_date = datetime.fromisoformat(ends_on).date() + timedelta(days=1)
            filters.append(
                ServiceRequest.created_at
                < datetime.combine(end_date, datetime.min.time(), tzinfo=UTC)
            )
        territory_uuid = uuid.UUID(territory_id) if territory_id else None
        agency_uuid = uuid.UUID(agency_id) if agency_id else None
    except ValueError:
        return jsonify(error="validation_error", message="Filtro territorial inválido."), 422
    if starts_on and ends_on and start_date > datetime.fromisoformat(ends_on).date():
        return jsonify(error="validation_error", message="Período territorial inválido."), 422
    if territory_uuid:
        territory = _tenant_entity(Territory, territory_uuid, tenant_id)
        if territory is None:
            return jsonify(error="validation_error", message="Território inválido."), 422
        filters.append(ServiceRequest.territory_id == territory_uuid)
    elif without_territory:
        filters.append(ServiceRequest.territory_id.is_(None))
    if agency_uuid:
        agency = _tenant_entity(ExternalAgency, agency_uuid, tenant_id)
        if agency is None:
            return jsonify(error="validation_error", message="Órgão inválido."), 422
        filters.append(ServiceRequest.agency_id == agency_uuid)

    sort_columns = {
        "protocolo": ServiceRequest.protocol,
        "solicitacao": ServiceRequest.title,
        "origem": ServiceRequest.source,
        "prioridade": ServiceRequest.priority,
        "status": ServiceRequest.status,
        "responsavel": User.name,
        "criadaEm": ServiceRequest.created_at,
    }
    if sort not in sort_columns or direction not in {"asc", "desc"}:
        return jsonify(error="validation_error", message="Ordenação inválida."), 422
    sort_expression = getattr(sort_columns[sort], direction)().nulls_last()

    base_query = select(ServiceRequest).outerjoin(
        User, ServiceRequest.responsible_id == User.id
    ).where(*filters)
    total = db.session.execute(
        select(func.count(ServiceRequest.id))
        .select_from(ServiceRequest)
        .outerjoin(User, ServiceRequest.responsible_id == User.id)
        .where(*filters)
    ).scalar_one()
    items = db.session.execute(
        base_query
        .order_by(sort_expression, ServiceRequest.created_at.desc(), ServiceRequest.id)
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
@roles_required("admin", "manager", "staff")
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

    if payload.get("responsavelId") and not can_distribute_requests():
        return (
            jsonify(error="forbidden", message="Somente a liderança pode distribuir solicitações."),
            403,
        )

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
        public_protocol=new_public_protocol(),
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
    if service_request.latitude is not None and service_request.longitude is not None:
        tenant = db.session.get(Tenant, tenant_id)
        service_request.geocode_source = "REQUEST_FORM"
        service_request.geocode_method = "MANUAL_INPUT"
        service_request.geocode_confidence = 0.8
        service_request.geocode_verified = False
        service_request.geocode_status = (
            "OUTSIDE_JURISDICTION"
            if _outside_jurisdiction_bounds(service_request, tenant)
            else "APPROXIMATE"
        )
        service_request.geocoded_at = now
    if category:
        service_request.category = category.name
    db.session.add(service_request)
    db.session.flush()
    service_request.history.append(_creation_history(service_request, user_id))
    db.session.add(creation_event(service_request))
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


def _outside_jurisdiction_bounds(
    service_request: ServiceRequest, tenant: Tenant | None
) -> bool:
    bounds = tenant.jurisdiction_bounds if tenant else None
    if not isinstance(bounds, dict):
        return False
    try:
        return not (
            float(bounds["minLatitude"])
            <= float(service_request.latitude)
            <= float(bounds["maxLatitude"])
            and float(bounds["minLongitude"])
            <= float(service_request.longitude)
            <= float(bounds["maxLongitude"])
        )
    except (KeyError, TypeError, ValueError):
        return False


@requests_bp.get("/solicitacoes/<uuid:request_id>")
@jwt_required()
def get_request(request_id: uuid.UUID):
    tenant_id, user_id = _context()
    service_request = _get_request_or_404(request_id, tenant_id, user_id)
    if service_request is None:
        return jsonify(error="resource_not_found", message="Solicitação não encontrada."), 404
    return jsonify(_serialize(service_request, include_details=True))


@requests_bp.post("/solicitacoes/<uuid:request_id>/geocodificacao/geoapify")
@limiter.limit("10 per minute")
@roles_required("admin", "manager")
def geocode_request_with_geoapify(request_id: uuid.UUID):
    tenant_id, user_id = _context()
    service_request = _get_request_or_404(request_id, tenant_id, user_id)
    if service_request is None:
        return jsonify(error="resource_not_found", message="Solicitação não encontrada."), 404

    state = _geocoding_homologation_state(tenant_id)
    if feature_error := _geocoding_feature_error(state):
        return feature_error
    payload = request.get_json(silent=True) or {}
    if payload.get("confirmacaoDadosTeste") is not True:
        return jsonify(
            error="test_data_confirmation_required",
            message=(
                "Confirme que o endereço pertence à homologação e não contém vínculo pessoal "
                "indevido antes de consultar o provedor externo."
            ),
        ), 422
    if not service_request.address or not service_request.address.strip():
        return jsonify(
            error="address_required",
            message="Informe um endereço na solicitação antes de geocodificar.",
        ), 422
    if service_request.geocode_verified:
        return jsonify(
            error="verified_geocoding_protected",
            message=(
                "A localização já foi verificada por uma pessoa e não pode ser substituída "
                "por nova consulta automática."
            ),
        ), 409

    tenant = db.session.get(Tenant, tenant_id)
    bbox = _homologation_bbox(tenant)
    if bbox is None and not tenant.jurisdiction_geojson:
        return jsonify(
            error="jurisdiction_not_configured",
            message="Configure os limites ou a geometria oficial da jurisdição.",
        ), 422
    reference = ", ".join(
        value
        for value in (
            service_request.address.strip(),
            tenant.jurisdiction_city,
            tenant.jurisdiction_state,
        )
        if value
    )
    query = GeocodeQuery(reference, jurisdiction_bbox=bbox)
    provider = GeoapifyAdapter(
        str(current_app.config["GEOAPIFY_API_KEY"]).strip(),
        timeout_seconds=float(
            current_app.config.get("GEOCODING_HOMOLOGATION_TIMEOUT_SECONDS", 12)
        ),
    )
    try:
        result = provider.geocode(query)
    except GeocodingProviderError:
        return jsonify(
            error="geocoding_provider_unavailable",
            message="O Geoapify não respondeu de forma válida. Tente novamente mais tarde.",
        ), 502

    status = result.status
    if (
        result.latitude is not None
        and result.longitude is not None
        and tenant.jurisdiction_geojson
    ):
        geometry = normalize_benchmark_geometry(tenant.jurisdiction_geojson)
        if not geometry_contains(geometry, result.latitude, result.longitude):
            status = GeocodeStatus.OUTSIDE_JURISDICTION
    if status == GeocodeStatus.VERIFIED:
        status = GeocodeStatus.APPROXIMATE

    before = {
        "latitude": service_request.latitude,
        "longitude": service_request.longitude,
        "statusGeografico": service_request.geocode_status,
        "verificada": service_request.geocode_verified,
        "metodo": service_request.geocode_method,
    }
    service_request.latitude = result.latitude
    service_request.longitude = result.longitude
    service_request.geocode_source = result.provider
    service_request.geocode_method = "HOMOLOGATION_EXTERNAL"
    service_request.geocode_confidence = result.confidence
    service_request.geocode_verified = False
    service_request.geocode_status = status.value
    service_request.geocoded_at = datetime.now(UTC)
    service_request.history.append(
        RequestHistory(
            tenant_id=tenant_id,
            user_id=user_id,
            action="request.geocoded.geoapify",
            changes={
                "latitude": {"antes": before["latitude"], "depois": result.latitude},
                "longitude": {"antes": before["longitude"], "depois": result.longitude},
                "statusGeografico": {
                    "antes": before["statusGeografico"],
                    "depois": status.value,
                },
                "verificada": {"antes": before["verificada"], "depois": False},
                "metodo": {
                    "antes": before["metodo"],
                    "depois": "HOMOLOGATION_EXTERNAL",
                },
                "atribuicoes": list(result.attribution),
                "revisaoHumana": "PENDENTE",
            },
        )
    )
    add_audit(
        tenant_id,
        user_id,
        "request.geocoding.geoapify.executed",
        "service_request",
        service_request.id,
        before={"statusGeografico": before["statusGeografico"]},
        after={
            "provedor": "GEOAPIFY",
            "statusGeografico": status.value,
            "revisaoHumana": "PENDENTE",
        },
    )
    db.session.commit()
    return jsonify(_serialize(service_request, include_details=True))


@requests_bp.post("/solicitacoes/<uuid:request_id>/geocodificacao/revisao")
@roles_required("admin", "manager")
def review_geocoded_request(request_id: uuid.UUID):
    tenant_id, user_id = _context()
    service_request = _get_request_or_404(request_id, tenant_id, user_id)
    if service_request is None:
        return jsonify(error="resource_not_found", message="Solicitação não encontrada."), 404
    state = _geocoding_homologation_state(tenant_id)
    if not state["habilitada"]:
        return _geocoding_feature_error(state)
    if (
        service_request.geocode_source != "GEOAPIFY"
        or service_request.geocode_method != "HOMOLOGATION_EXTERNAL"
        or service_request.geocode_verified
    ):
        return jsonify(
            error="geocoding_review_not_pending",
            message="A solicitação não possui resultado pendente de revisão do Geoapify.",
        ), 409

    payload = request.get_json(silent=True) or {}
    decision = str(payload.get("decisao", "")).upper()
    justification = str(payload.get("justificativa", "")).strip()
    if decision not in {"APROVAR", "REJEITAR"} or len(justification) < 3:
        return jsonify(
            error="validation_error",
            message="Informe decisão APROVAR ou REJEITAR e uma justificativa.",
        ), 422
    if decision == "APROVAR" and (
        service_request.latitude is None
        or service_request.longitude is None
        or service_request.geocode_status in {"UNRESOLVED", "OUTSIDE_JURISDICTION"}
    ):
        return jsonify(
            error="geocoding_result_not_approvable",
            message="Resultados sem coordenadas ou fora da jurisdição não podem ser aprovados.",
        ), 422

    before_status = service_request.geocode_status
    before_verified = service_request.geocode_verified
    if decision == "APROVAR":
        service_request.geocode_status = "VERIFIED"
        service_request.geocode_verified = True
        service_request.geocode_method = "HOMOLOGATION_HUMAN_REVIEW"
    else:
        service_request.latitude = None
        service_request.longitude = None
        service_request.geocode_status = "UNRESOLVED"
        service_request.geocode_verified = False
        service_request.geocode_method = "HOMOLOGATION_REJECTED"
    service_request.geocoded_at = datetime.now(UTC)
    service_request.history.append(
        RequestHistory(
            tenant_id=tenant_id,
            user_id=user_id,
            action="request.geocoding.reviewed",
            changes={
                "decisao": decision,
                "justificativa": justification,
                "statusGeografico": {
                    "antes": before_status,
                    "depois": service_request.geocode_status,
                },
                "verificada": {
                    "antes": before_verified,
                    "depois": service_request.geocode_verified,
                },
            },
        )
    )
    add_audit(
        tenant_id,
        user_id,
        "request.geocoding.reviewed",
        "service_request",
        service_request.id,
        before={"statusGeografico": before_status, "verificada": before_verified},
        after={
            "decisao": decision,
            "statusGeografico": service_request.geocode_status,
            "verificada": service_request.geocode_verified,
        },
    )
    db.session.commit()
    return jsonify(_serialize(service_request, include_details=True))


@requests_bp.patch("/solicitacoes/<uuid:request_id>")
@roles_required("admin", "manager", "representative", "staff")
def update_request(request_id: uuid.UUID):
    tenant_id, user_id = _context()
    service_request = _get_request_or_404(request_id, tenant_id, user_id)
    if service_request is None:
        return jsonify(error="resource_not_found", message="Solicitação não encontrada."), 404

    payload = request.get_json(silent=True) or {}
    if get_jwt().get("role") == "representative" and set(payload) - {"responsavelId"}:
        return (
            jsonify(
                error="forbidden",
                message="O parlamentar pode alterar apenas a distribuição da solicitação.",
            ),
            403,
        )
    if "responsavelId" in payload and not can_distribute_requests():
        return (
            jsonify(error="forbidden", message="Somente a liderança pode distribuir solicitações."),
            403,
        )
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
@roles_required("admin", "manager", "staff")
def create_interaction(request_id: uuid.UUID):
    tenant_id, user_id = _context()
    service_request = _get_request_or_404(request_id, tenant_id, user_id)
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
