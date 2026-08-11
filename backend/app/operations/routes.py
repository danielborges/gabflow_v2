import hashlib
import secrets
import threading
import time
import uuid
from calendar import monthrange
from collections import Counter
from datetime import UTC, datetime, timedelta
from io import BytesIO
from math import cos, pi, sin
from statistics import median

from flask import Blueprint, current_app, jsonify, request, send_file
from flask_jwt_extended import get_jwt, get_jwt_identity, jwt_required
from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import selectinload

from app.audit import add_audit
from app.auth.permissions import roles_required
from app.extensions import db, limiter
from app.models import (
    Citizen,
    ContactAttempt,
    ContactAttemptOutcome,
    ExternalAgency,
    ForwardingStatus,
    InteractionDirection,
    InteractionVisibility,
    LegislativeDraft,
    LegislativeDraftRequest,
    RequestForwarding,
    RequestHistory,
    RequestInteraction,
    RequestStatus,
    RequestTask,
    Role,
    ScheduledReturn,
    ScheduledReturnStatus,
    ServiceRequest,
    TaskStatus,
    Tenant,
    TerritorialAction,
    TerritorialSavedView,
    Territory,
    User,
)
from app.operations.report_exports import executive_report_pdf
from app.requests.access import request_visibility_filters

operations_bp = Blueprint("operations", __name__)
public_bp = Blueprint("public_requests", __name__)
_DASHBOARD_CACHE: dict[tuple, tuple[float, dict]] = {}
_DASHBOARD_CACHE_LOCKS: dict[tuple, threading.Lock] = {}
_DASHBOARD_CACHE_GUARD = threading.Lock()

CLOSED_STATUSES = {
    RequestStatus.RESOLVIDA,
    RequestStatus.ENCERRADA,
    RequestStatus.CANCELADA,
}
RECURRENCE_WINDOW_DAYS = 30
RECURRENCE_MIN_REQUESTS = 3
ANOMALY_CURRENT_WINDOW_DAYS = 7
ANOMALY_BASELINE_WINDOW_DAYS = 28
ANOMALY_MIN_CURRENT_REQUESTS = 3
ANOMALY_GROWTH_FACTOR = 2.0
MIN_ANALYTICS_GROUP_SIZE = 3


def _context() -> tuple[uuid.UUID, uuid.UUID]:
    return uuid.UUID(get_jwt()["tenant_id"]), uuid.UUID(get_jwt_identity())


def _service_request(request_id: uuid.UUID, tenant_id: uuid.UUID) -> ServiceRequest | None:
    return db.session.execute(
        select(ServiceRequest).where(
            ServiceRequest.id == request_id,
            *request_visibility_filters(tenant_id),
        )
    ).scalar_one_or_none()


def _parse_datetime(value) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError("Prazo inválido.") from error
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def forwarding_data(item: RequestForwarding) -> dict:
    agency = db.session.get(ExternalAgency, item.agency_id)
    return {
        "id": str(item.id),
        "orgaoId": str(item.agency_id),
        "orgao": agency.name if agency else "Órgão removido",
        "protocoloExterno": item.external_protocol,
        "observacoes": item.notes,
        "status": item.status.value,
        "resposta": item.response,
        "respondidoEm": item.response_at.isoformat() if item.response_at else None,
        "prazo": item.due_at.isoformat() if item.due_at else None,
        "criadoEm": item.created_at.isoformat(),
    }


def contact_attempt_data(item: ContactAttempt) -> dict:
    return {
        "id": str(item.id),
        "canal": item.channel,
        "destino": item.destination,
        "resultado": item.outcome.value,
        "observacoes": item.notes,
        "justificativaCanal": item.channel_override_reason,
        "tentadaEm": item.attempted_at.isoformat(),
        "proximaTentativaEm": (item.next_attempt_at.isoformat() if item.next_attempt_at else None),
        "responsavelId": str(item.created_by_id),
    }


@operations_bp.post("/solicitacoes/<uuid:request_id>/encaminhamentos")
@roles_required("admin", "manager", "staff")
def create_forwarding(request_id: uuid.UUID):
    tenant_id, user_id = _context()
    service_request = _service_request(request_id, tenant_id)
    if service_request is None:
        return jsonify(error="resource_not_found", message="Solicitação não encontrada."), 404
    payload = request.get_json(silent=True) or {}
    try:
        agency_id = uuid.UUID(str(payload.get("orgaoId", "")))
        due_at = _parse_datetime(payload.get("prazo"))
    except (TypeError, ValueError) as error:
        return jsonify(error="validation_error", message=str(error)), 422
    agency = db.session.execute(
        select(ExternalAgency).where(
            ExternalAgency.id == agency_id,
            ExternalAgency.tenant_id == tenant_id,
            ExternalAgency.active.is_(True),
        )
    ).scalar_one_or_none()
    if agency is None:
        return jsonify(error="validation_error", message="Órgão inválido."), 422

    item = RequestForwarding(
        tenant_id=tenant_id,
        request_id=service_request.id,
        agency_id=agency.id,
        external_protocol=str(payload.get("protocoloExterno", "")).strip() or None,
        notes=str(payload.get("observacoes", "")).strip() or None,
        due_at=due_at,
        created_by_id=user_id,
        status=ForwardingStatus.AGUARDANDO_RETORNO,
    )
    db.session.add(item)
    service_request.agency_id = agency.id
    service_request.status = RequestStatus.AGUARDANDO_ORGAO
    db.session.flush()
    changes = {"encaminhamentoId": {"antes": None, "depois": str(item.id)}}
    service_request.history.append(
        RequestHistory(
            tenant_id=tenant_id,
            user_id=user_id,
            action="request.forwarded",
            changes=changes,
        )
    )
    add_audit(
        tenant_id,
        user_id,
        "request.forwarded",
        "request_forwarding",
        item.id,
        after=forwarding_data(item),
    )
    db.session.commit()
    return jsonify(forwarding_data(item)), 201


@operations_bp.patch("/encaminhamentos/<uuid:forwarding_id>")
@roles_required("admin", "manager", "staff")
def update_forwarding(forwarding_id: uuid.UUID):
    tenant_id, user_id = _context()
    item = db.session.execute(
        select(RequestForwarding).where(
            RequestForwarding.id == forwarding_id,
            RequestForwarding.tenant_id == tenant_id,
        )
    ).scalar_one_or_none()
    if item is None:
        return jsonify(error="resource_not_found", message="Encaminhamento não encontrado."), 404
    payload = request.get_json(silent=True) or {}
    before = forwarding_data(item)
    response_text = str(payload.get("resposta", "")).strip()
    if "resposta" in payload and not response_text:
        return jsonify(error="validation_error", message="Informe a resposta recebida."), 422
    if response_text:
        item.response = response_text
        item.response_at = datetime.now(UTC)
        item.status = ForwardingStatus.RESPONDIDO
        item.request.status = RequestStatus.EM_ATENDIMENTO
        item.request.interactions.append(
            RequestInteraction(
                tenant_id=tenant_id,
                interaction_type="RESPOSTA_ORGAO",
                channel="ORGAO_EXTERNO",
                direction=InteractionDirection.ENTRADA,
                content=response_text,
                visibility=InteractionVisibility.INTERNA,
                author_id=user_id,
            )
        )
    if "protocoloExterno" in payload:
        item.external_protocol = str(payload["protocoloExterno"]).strip() or None
    after = forwarding_data(item)
    add_audit(
        tenant_id,
        user_id,
        "request.forwarding.updated",
        "request_forwarding",
        item.id,
        before,
        after,
    )
    db.session.commit()
    return jsonify(after)


@operations_bp.post("/solicitacoes/<uuid:request_id>/reabrir")
@roles_required("admin", "manager", "staff")
def reopen_request(request_id: uuid.UUID):
    tenant_id, user_id = _context()
    service_request = _service_request(request_id, tenant_id)
    if service_request is None:
        return jsonify(error="resource_not_found", message="Solicitação não encontrada."), 404
    reason = str((request.get_json(silent=True) or {}).get("motivo", "")).strip()
    if service_request.status not in CLOSED_STATUSES:
        return jsonify(error="validation_error", message="A solicitação não está encerrada."), 422
    if len(reason) < 3:
        return jsonify(error="validation_error", message="Informe o motivo da reabertura."), 422
    previous = service_request.status.value
    service_request.status = RequestStatus.EM_ATENDIMENTO
    service_request.closed_at = None
    service_request.history.append(
        RequestHistory(
            tenant_id=tenant_id,
            user_id=user_id,
            action="request.reopened",
            changes={
                "status": {"antes": previous, "depois": RequestStatus.EM_ATENDIMENTO.value},
                "motivo": {"antes": None, "depois": reason},
            },
        )
    )
    add_audit(
        tenant_id,
        user_id,
        "request.reopened",
        "service_request",
        service_request.id,
        before={"status": previous},
        after={"status": service_request.status.value, "motivo": reason},
    )
    db.session.commit()
    return jsonify(status=service_request.status.value, motivo=reason)


@operations_bp.post("/solicitacoes/<uuid:request_id>/chave-publica")
@roles_required("admin", "manager", "staff")
def rotate_public_key(request_id: uuid.UUID):
    tenant_id, user_id = _context()
    service_request = _service_request(request_id, tenant_id)
    if service_request is None:
        return jsonify(error="resource_not_found", message="Solicitação não encontrada."), 404
    key = secrets.token_urlsafe(24)
    service_request.public_access_key_hash = hashlib.sha256(key.encode()).hexdigest()
    add_audit(
        tenant_id,
        user_id,
        "request.public_key.rotated",
        "service_request",
        service_request.id,
        after={"protocolo": service_request.protocol},
    )
    db.session.commit()
    return jsonify(protocolo=service_request.protocol, chave=key)


@operations_bp.post("/solicitacoes/<uuid:request_id>/tentativas-contato")
@roles_required("admin", "manager", "staff")
def create_contact_attempt(request_id: uuid.UUID):
    tenant_id, user_id = _context()
    service_request = _service_request(request_id, tenant_id)
    if service_request is None:
        return jsonify(error="resource_not_found", message="Solicitação não encontrada."), 404
    payload = request.get_json(silent=True) or {}
    citizen = (
        db.session.get(Citizen, service_request.citizen_id) if service_request.citizen_id else None
    )
    preferred_channel = (
        citizen.preferred_channel.upper() if citizen and citizen.preferred_channel else None
    )
    channel = str(payload.get("canal") or preferred_channel or "").strip().upper()
    if channel not in {"WHATSAPP", "TELEFONE", "EMAIL", "PRESENCIAL"}:
        return jsonify(error="validation_error", message="Canal de contato inválido."), 422
    override_reason = str(payload.get("justificativaCanal", "")).strip() or None
    if preferred_channel and channel != preferred_channel and not override_reason:
        return (
            jsonify(
                error="validation_error",
                message="Informe a justificativa para usar canal diferente do preferencial.",
            ),
            422,
        )
    destination = str(payload.get("destino", "")).strip() or _contact_destination(citizen, channel)
    if not destination:
        return jsonify(error="validation_error", message="Informe o destino do contato."), 422
    try:
        outcome = ContactAttemptOutcome(str(payload.get("resultado", "")).upper())
        attempted_at = _parse_datetime(payload.get("tentadaEm")) or datetime.now(UTC)
        next_attempt_at = _parse_datetime(payload.get("proximaTentativaEm"))
    except ValueError as error:
        return jsonify(error="validation_error", message=str(error)), 422
    if outcome == ContactAttemptOutcome.AGENDADO and next_attempt_at is None:
        return (
            jsonify(
                error="validation_error",
                message="Informe a data da próxima tentativa.",
            ),
            422,
        )
    item = ContactAttempt(
        tenant_id=tenant_id,
        request_id=service_request.id,
        citizen_id=service_request.citizen_id,
        channel=channel,
        destination=destination,
        outcome=outcome,
        notes=str(payload.get("observacoes", "")).strip() or None,
        channel_override_reason=override_reason,
        attempted_at=attempted_at,
        next_attempt_at=next_attempt_at,
        created_by_id=user_id,
    )
    db.session.add(item)
    db.session.flush()
    if outcome in {
        ContactAttemptOutcome.SEM_RESPOSTA,
        ContactAttemptOutcome.AGENDADO,
    }:
        service_request.status = RequestStatus.AGUARDANDO_CIDADAO
    service_request.interactions.append(
        RequestInteraction(
            tenant_id=tenant_id,
            interaction_type="TENTATIVA_CONTATO",
            channel=channel,
            direction=InteractionDirection.SAIDA,
            content=_attempt_summary(item),
            visibility=InteractionVisibility.INTERNA,
            author_id=user_id,
        )
    )
    service_request.history.append(
        RequestHistory(
            tenant_id=tenant_id,
            user_id=user_id,
            action="request.contact_attempt.created",
            changes={"tentativaContatoId": {"antes": None, "depois": str(item.id)}},
        )
    )
    add_audit(
        tenant_id,
        user_id,
        "request.contact_attempt.created",
        "contact_attempt",
        item.id,
        after={
            "canal": item.channel,
            "resultado": item.outcome.value,
            "proximaTentativaEm": (
                item.next_attempt_at.isoformat() if item.next_attempt_at else None
            ),
        },
    )
    db.session.commit()
    return jsonify(contact_attempt_data(item)), 201


@operations_bp.get("/painel/operacional")
@jwt_required()
def operational_dashboard():
    tenant_id, user_id = _context()
    from app.communications.service import generate_return_reminders

    if generate_return_reminders(tenant_id, user_id):
        db.session.commit()
    claims = get_jwt()
    cache_key = (
        str(tenant_id),
        claims.get("role"),
        bool(claims.get("is_chief_of_staff")),
        tuple(sorted(request.args.items(multi=True))),
    )
    with _DASHBOARD_CACHE_GUARD:
        key_lock = _DASHBOARD_CACHE_LOCKS.setdefault(cache_key, threading.Lock())
    with key_lock:
        now = time.monotonic()
        cached = _DASHBOARD_CACHE.get(cache_key)
        if cached and cached[0] > now:
            return jsonify(cached[1])
        response = _build_operational_dashboard()
        if isinstance(response, tuple):
            return response
        payload = response.get_json()
        ttl = current_app.config["OPERATIONAL_DASHBOARD_CACHE_SECONDS"]
        _DASHBOARD_CACHE[cache_key] = (now + ttl, payload)
        if len(_DASHBOARD_CACHE) > 200:
            expired = [key for key, value in _DASHBOARD_CACHE.items() if value[0] <= now]
            for key in expired:
                _DASHBOARD_CACHE.pop(key, None)
                _DASHBOARD_CACHE_LOCKS.pop(key, None)
        return response


def _build_operational_dashboard():
    tenant_id, _ = _context()
    now = datetime.now(UTC)
    from app.communications.service import scheduled_return_data

    all_items = list(
        db.session.execute(
            select(ServiceRequest)
            .where(ServiceRequest.tenant_id == tenant_id)
            .options(
                selectinload(ServiceRequest.interactions),
                selectinload(ServiceRequest.history),
                selectinload(ServiceRequest.forwardings),
            )
            .order_by(ServiceRequest.created_at.desc())
        ).scalars()
    )
    try:
        filters = _dashboard_filters(request.args)
    except ValueError as error:
        return jsonify(error="validation_error", message=str(error)), 422
    items = _apply_dashboard_filters(all_items, filters)
    comparison_filters = _comparison_dashboard_filters(filters)
    comparison_items = _apply_dashboard_filters(all_items, comparison_filters)
    open_items = [item for item in items if item.status not in CLOSED_STATUSES]
    overdue = [item for item in open_items if item.due_at and _utc(item.due_at) < now]
    near_due = [
        item
        for item in open_items
        if item.due_at and 0 <= (_utc(item.due_at) - now).total_seconds() <= 86400
    ]
    operational_metrics = _operational_metrics(items)
    territory_names = {
        item.id: item.name
        for item in db.session.execute(
            select(Territory).where(Territory.tenant_id == tenant_id)
        ).scalars()
    }
    agency_names = {
        item.id: item.name
        for item in db.session.execute(
            select(ExternalAgency).where(ExternalAgency.tenant_id == tenant_id)
        ).scalars()
    }
    responsible_names = {
        item.id: item.name
        for item in db.session.execute(select(User).where(User.tenant_id == tenant_id)).scalars()
    }
    if filters["territorioId"] and filters["territorioId"] not in territory_names:
        return (
            jsonify(error="validation_error", message="TerritÃ³rio invÃ¡lido para o gabinete."),
            422,
        )
    if filters["orgaoId"] and filters["orgaoId"] not in agency_names:
        return jsonify(error="validation_error", message="Ã“rgÃ£o invÃ¡lido para o gabinete."), 422
    tenant = db.session.get(Tenant, tenant_id)
    filtered_request_ids = {item.id for item in items}
    pending_tasks = list(
        db.session.execute(
            select(RequestTask).where(
                RequestTask.tenant_id == tenant_id,
                RequestTask.status.in_([TaskStatus.PENDENTE, TaskStatus.EM_ANDAMENTO]),
            )
        ).scalars()
    )
    if filtered_request_ids:
        pending_tasks = [item for item in pending_tasks if item.request_id in filtered_request_ids]
    elif items == []:
        pending_tasks = []
    active_returns = list(
        db.session.execute(
            select(ScheduledReturn)
            .where(
                ScheduledReturn.tenant_id == tenant_id,
                ScheduledReturn.status == ScheduledReturnStatus.AGENDADO,
            )
            .order_by(ScheduledReturn.scheduled_at)
        ).scalars()
    )
    if filtered_request_ids:
        active_returns = [
            item for item in active_returns if item.request_id in filtered_request_ids
        ]
    elif items == []:
        active_returns = []
    overdue_returns = [item for item in active_returns if _utc(item.scheduled_at) < now]
    near_returns = [
        item
        for item in active_returns
        if 0 <= (_utc(item.scheduled_at) - now).total_seconds() <= 86400
    ]
    priority = sorted(
        open_items,
        key=lambda item: (
            0 if item in overdue else 1,
            _utc(item.due_at) if item.due_at else datetime.max.replace(tzinfo=UTC),
        ),
    )[:10]
    analytics = {
        "porStatus": _private_counter(item.status.value for item in items),
        "porCategoria": _private_counter(item.category or "Sem categoria" for item in items),
        "porCanal": _private_counter(item.source.value for item in items),
        "porOrigem": _private_counter(item.source.value for item in items),
        "porOrgao": _private_counter(
            agency_names.get(item.agency_id, "Sem órgão") for item in items
        ),
        "porTerritorio": _private_counter(
            territory_names.get(item.territory_id, "Sem território") for item in items
        ),
        "porPeriodo": _private_period_counter(items, filters["granularidade"]),
    }
    privacy_summary = _privacy_summary(analytics)
    return jsonify(
        indicadores={
            "total": len(items),
            "abertas": len(open_items),
            "atrasadas": len(overdue),
            "proximasDoPrazo": len(near_due),
            "semResponsavel": sum(item.responsible_id is None for item in open_items),
            "aguardandoOrgao": sum(
                item.status == RequestStatus.AGUARDANDO_ORGAO for item in open_items
            ),
            "tarefasPendentes": len(list(pending_tasks)),
            "retornosVencidos": len(overdue_returns),
            "retornosProximos": len(near_returns),
            "tempoMedioResolucaoHoras": operational_metrics["tempoMedioResolucaoHoras"],
        },
        metricasOperacionais=operational_metrics,
        filtros=_dashboard_filter_payload(all_items, filters, territory_names, agency_names),
        privacidadeAgregacao=privacy_summary,
        porStatus=analytics["porStatus"]["items"],
        porCategoria=analytics["porCategoria"]["items"],
        porCanal=analytics["porCanal"]["items"],
        porOrigem=analytics["porOrigem"]["items"],
        porOrgao=_counter(agency_names.get(item.agency_id, "Sem órgão") for item in items),
        porTerritorio=_counter(
            territory_names.get(item.territory_id, "Sem território") for item in items
        ),
        porPeriodo=_period_counter(items, filters["granularidade"]),
        filaPrioritaria=[
            {
                "id": str(item.id),
                "protocolo": item.protocol,
                "titulo": item.title,
                "status": item.status.value,
                "prazo": item.due_at.isoformat() if item.due_at else None,
                "atrasada": item in overdue,
            }
            for item in priority
        ],
        retornosPrioritarios=[
            {
                **scheduled_return_data(item),
                "protocolo": item.request.protocol,
                "titulo": item.request.title,
                "vencido": item in overdue_returns,
            }
            for item in active_returns[:10]
        ],
        territorial=_territorial_dashboard(
            tenant_id,
            tenant,
            items,
            open_items,
            overdue,
            territory_names,
            agency_names,
            responsible_names,
            filters,
            comparison_filters,
            comparison_items,
            can_view_points=get_jwt().get("role") in {"admin", "manager"},
        ),
        alertasDemanda=_demand_alerts(
            items,
            now,
            overdue,
            territory_names,
            can_view_examples=get_jwt().get("role") in {"admin", "manager"},
        ),
    )


@operations_bp.get("/painel/relatorio-mensal")
@jwt_required()
def monthly_mandate_report():
    tenant_id, _ = _context()
    try:
        starts_at, ends_at = _monthly_report_period(request.args)
    except ValueError as error:
        return jsonify(error="validation_error", message=str(error)), 422

    all_items = list(
        db.session.execute(
            select(ServiceRequest)
            .where(ServiceRequest.tenant_id == tenant_id)
            .order_by(ServiceRequest.created_at.desc())
        ).scalars()
    )
    created_items = [item for item in all_items if starts_at <= _utc(item.created_at) < ends_at]
    closed_items = [
        item for item in all_items if item.closed_at and starts_at <= _utc(item.closed_at) < ends_at
    ]
    forwarded_items = [
        item
        for item in all_items
        if any(
            starts_at <= _utc(forwarding.created_at) < ends_at for forwarding in item.forwardings
        )
    ]
    touched_items = _unique_requests([*created_items, *closed_items, *forwarded_items])
    territory_names = {
        item.id: item.name
        for item in db.session.execute(
            select(Territory).where(Territory.tenant_id == tenant_id)
        ).scalars()
    }
    agency_names = {
        item.id: item.name
        for item in db.session.execute(
            select(ExternalAgency).where(ExternalAgency.tenant_id == tenant_id)
        ).scalars()
    }
    analytics = {
        "porStatus": _private_counter(item.status.value for item in touched_items),
        "porCategoria": _private_counter(
            item.category or "Sem categoria" for item in touched_items
        ),
        "porCanal": _private_counter(item.source.value for item in touched_items),
        "porOrgao": _private_counter(
            agency_names.get(item.agency_id, "Sem órgão") for item in touched_items
        ),
        "porTerritorio": _private_counter(
            territory_names.get(item.territory_id, "Sem território") for item in touched_items
        ),
    }
    overdue = [
        item
        for item in touched_items
        if item.status not in CLOSED_STATUSES and item.due_at and _utc(item.due_at) < ends_at
    ]
    return jsonify(
        periodo={
            "ano": starts_at.year,
            "mes": starts_at.month,
            "inicio": starts_at.date().isoformat(),
            "fim": (ends_at - timedelta(days=1)).date().isoformat(),
            "rotulo": _month_label(starts_at),
        },
        resumo={
            "solicitacoesRecebidas": len(created_items),
            "solicitacoesMovimentadas": len(touched_items),
            "encaminhadas": len(forwarded_items),
            "resolvidasOuEncerradas": len(closed_items),
            "emAbertoAoFimDoMes": sum(item.status not in CLOSED_STATUSES for item in touched_items),
            "atrasadasAoFimDoMes": len(overdue),
        },
        indicadores={
            "porStatus": analytics["porStatus"]["items"],
            "porCategoria": analytics["porCategoria"]["items"],
            "porCanal": analytics["porCanal"]["items"],
            "porOrgao": analytics["porOrgao"]["items"],
            "porTerritorio": analytics["porTerritorio"]["items"],
        },
        privacidadeAgregacao=_privacy_summary(analytics),
        destaques=_monthly_highlights(touched_items, territory_names, agency_names),
        evidencias=_monthly_evidence(
            touched_items, starts_at, ends_at, territory_names, agency_names
        ),
        alertas=_demand_alerts(
            touched_items,
            ends_at,
            overdue,
            territory_names,
            can_view_examples=get_jwt().get("role") in {"admin", "manager"},
        ),
    )


@operations_bp.get("/painel/relatorios")
@jwt_required()
def mandate_reports():
    tenant_id, _ = _context()
    try:
        starts_at, ends_at = _custom_report_period(request.args)
        report_type = _report_type(request.args.get("tipo"))
    except ValueError as error:
        return jsonify(error="validation_error", message=str(error)), 422
    return jsonify(_executive_report_payload(tenant_id, starts_at, ends_at, report_type))


@operations_bp.get("/painel/relatorios/pdf")
@jwt_required()
def mandate_reports_pdf():
    tenant_id, _ = _context()
    try:
        starts_at, ends_at = _custom_report_period(request.args)
        report_type = _report_type(request.args.get("tipo"))
    except ValueError as error:
        return jsonify(error="validation_error", message=str(error)), 422
    payload = _executive_report_payload(tenant_id, starts_at, ends_at, report_type)
    stream = BytesIO(executive_report_pdf(payload))
    suffix = "operacional" if report_type == "OPERACIONAL" else "insights-mandato"
    return send_file(
        stream,
        mimetype="application/pdf",
        as_attachment=True,
        download_name=(
            f"gabflow-relatorio-{suffix}-{starts_at.date().isoformat()}-"
            f"{(ends_at - timedelta(days=1)).date().isoformat()}.pdf"
        ),
    )


@operations_bp.get("/painel/territorial/visoes")
@jwt_required()
def list_territorial_saved_views():
    tenant_id, user_id = _context()
    items = db.session.execute(
        select(TerritorialSavedView)
        .where(
            TerritorialSavedView.tenant_id == tenant_id,
            TerritorialSavedView.user_id == user_id,
        )
        .order_by(TerritorialSavedView.name)
    ).scalars()
    return jsonify(content=[_saved_view_data(item) for item in items])


@operations_bp.post("/painel/territorial/visoes")
@jwt_required()
def save_territorial_view():
    tenant_id, user_id = _context()
    payload = request.get_json(silent=True) or {}
    name = str(payload.get("nome", "")).strip()
    if not 2 <= len(name) <= 80:
        return (
            jsonify(error="validation_error", message="Informe um nome entre 2 e 80 caracteres."),
            422,
        )
    try:
        filters = _dashboard_filters(payload.get("filtros") or {})
        _validate_dashboard_entity_filters(tenant_id, filters)
    except ValueError as error:
        return jsonify(error="validation_error", message=str(error)), 422
    item = db.session.execute(
        select(TerritorialSavedView).where(
            TerritorialSavedView.tenant_id == tenant_id,
            TerritorialSavedView.user_id == user_id,
            TerritorialSavedView.name == name,
        )
    ).scalar_one_or_none()
    if item is None:
        count = (
            db.session.execute(
                select(TerritorialSavedView).where(
                    TerritorialSavedView.tenant_id == tenant_id,
                    TerritorialSavedView.user_id == user_id,
                )
            )
            .scalars()
            .all()
        )
        if len(count) >= 10:
            return (
                jsonify(error="validation_error", message="Limite de 10 visões salvas atingido."),
                422,
            )
        item = TerritorialSavedView(tenant_id=tenant_id, user_id=user_id, name=name)
        db.session.add(item)
    item.filters = _serialize_dashboard_filters(filters)
    db.session.flush()
    add_audit(
        tenant_id,
        user_id,
        "territorial.saved_view.saved",
        "territorial_saved_view",
        item.id,
        after={"nome": name, "camposFiltro": sorted(item.filters)},
    )
    db.session.commit()
    return jsonify(_saved_view_data(item)), 201


@operations_bp.delete("/painel/territorial/visoes/<uuid:view_id>")
@jwt_required()
def delete_territorial_saved_view(view_id: uuid.UUID):
    tenant_id, user_id = _context()
    item = db.session.execute(
        select(TerritorialSavedView).where(
            TerritorialSavedView.id == view_id,
            TerritorialSavedView.tenant_id == tenant_id,
            TerritorialSavedView.user_id == user_id,
        )
    ).scalar_one_or_none()
    if item is None:
        return jsonify(error="resource_not_found", message="Visão territorial não encontrada."), 404
    add_audit(
        tenant_id,
        user_id,
        "territorial.saved_view.deleted",
        "territorial_saved_view",
        item.id,
        before={"nome": item.name},
    )
    db.session.delete(item)
    db.session.commit()
    return "", 204


@operations_bp.post("/painel/territorial/geocodificar")
@roles_required("admin", "manager", "staff")
def geocode_pending_requests():
    tenant_id, user_id = _context()
    tenant = db.session.get(Tenant, tenant_id)
    if not _has_jurisdiction_reference(tenant):
        return jsonify(
            error="jurisdiction_not_configured",
            message="Configure o centro ou os limites da jurisdiÃ§Ã£o antes de geocodificar.",
        ), 422
    territory_names = {
        item.id: item.name
        for item in db.session.execute(
            select(Territory).where(Territory.tenant_id == tenant_id)
        ).scalars()
    }
    items = list(
        db.session.execute(
            select(ServiceRequest).where(
                ServiceRequest.tenant_id == tenant_id,
                ServiceRequest.latitude.is_(None),
                ServiceRequest.longitude.is_(None),
            )
        ).scalars()
    )
    updated = []
    for item in items:
        reference = _geocode_reference(item, territory_names)
        if not reference:
            continue
        latitude, longitude = _local_coordinates(reference, tenant)
        if (
            not _coordinates_in_jurisdiction(latitude, longitude, tenant)
            and tenant.jurisdiction_center_latitude is not None
            and tenant.jurisdiction_center_longitude is not None
            and _coordinates_in_jurisdiction(
                tenant.jurisdiction_center_latitude,
                tenant.jurisdiction_center_longitude,
                tenant,
            )
        ):
            latitude = tenant.jurisdiction_center_latitude
            longitude = tenant.jurisdiction_center_longitude
        item.latitude = latitude
        item.longitude = longitude
        item.geocode_source = "TENANT_JURISDICTION"
        item.geocode_method = "LOCAL_APPROXIMATE"
        item.geocode_confidence = 0.45
        item.geocode_verified = False
        item.geocode_status = (
            "APPROXIMATE"
            if _coordinates_in_jurisdiction(latitude, longitude, tenant)
            else "OUTSIDE_JURISDICTION"
        )
        item.geocoded_at = datetime.now(UTC)
        item.history.append(
            RequestHistory(
                tenant_id=tenant_id,
                user_id=user_id,
                action="request.geocoded",
                changes={
                    "latitude": {"antes": None, "depois": latitude},
                    "longitude": {"antes": None, "depois": longitude},
                    "metodo": {"antes": None, "depois": "LOCAL_APROXIMADO"},
                    "statusGeografico": {"antes": "UNRESOLVED", "depois": item.geocode_status},
                },
            )
        )
        updated.append(item)
    if updated:
        add_audit(
            tenant_id,
            user_id,
            "territorial.geocoding.completed",
            "service_request",
            None,
            after={
                "quantidade": len(updated),
                "metodo": "LOCAL_APROXIMADO",
                "solicitacoes": [str(item.id) for item in updated],
            },
        )
        db.session.commit()
    return jsonify(
        geocodificadas=len(updated),
        pendentes=max(len(items) - len(updated), 0),
        metodo="LOCAL_APROXIMADO",
    )


@operations_bp.post("/painel/territorial/metricas-fluxo")
@jwt_required()
def record_territorial_flow_metric():
    tenant_id, user_id = _context()
    payload = request.get_json(silent=True) or {}
    metric = str(payload.get("evento", "")).upper()
    allowed = {
        "ABA_ABERTA",
        "FILTRO_APLICADO",
        "INVESTIGACAO_INICIADA",
        "ACAO_INICIADA",
    }
    if metric not in allowed:
        return jsonify(error="validation_error", message="Evento territorial invÃ¡lido."), 422
    try:
        filter_count = int(payload.get("quantidadeFiltros", 0))
    except (TypeError, ValueError):
        return jsonify(error="validation_error", message="Quantidade de filtros invÃ¡lida."), 422
    if not 0 <= filter_count <= 7:
        return jsonify(error="validation_error", message="Quantidade de filtros invÃ¡lida."), 422
    add_audit(
        tenant_id,
        user_id,
        f"territorial.flow.{metric.lower()}",
        "territorial_flow",
        None,
        after={"quantidadeFiltros": filter_count},
    )
    db.session.commit()
    return "", 204


@public_bp.get("/publico/solicitacoes/<protocol>")
@limiter.limit("20 per minute")
def public_request_status(protocol: str):
    key = str(request.args.get("chave", ""))
    if not key:
        return jsonify(error="invalid_key", message="Chave de acompanhamento inválida."), 403
    key_hash = hashlib.sha256(key.encode()).hexdigest()
    item = db.session.execute(
        select(ServiceRequest).where(
            ServiceRequest.protocol == protocol,
            ServiceRequest.public_access_key_hash == key_hash,
        )
    ).scalar_one_or_none()
    if item is None:
        return jsonify(error="invalid_key", message="Chave de acompanhamento inválida."), 403
    public_interactions = [
        {
            "conteudo": interaction.content,
            "criadaEm": interaction.created_at.isoformat(),
        }
        for interaction in item.interactions
        if interaction.visibility == InteractionVisibility.CIDADAO
    ]
    return jsonify(
        protocolo=item.protocol,
        titulo=item.title,
        status=item.status.value,
        atualizadaEm=item.updated_at.isoformat(),
        interacoes=public_interactions,
    )


def _territorial_dashboard(
    tenant_id: uuid.UUID,
    tenant: Tenant | None,
    items: list[ServiceRequest],
    open_items: list[ServiceRequest],
    overdue: list[ServiceRequest],
    territory_names: dict,
    agency_names: dict,
    responsible_names: dict,
    filters: dict,
    comparison_filters: dict,
    comparison_items: list[ServiceRequest],
    can_view_points: bool = False,
) -> dict:
    coordinate_items = [
        item for item in items if item.latitude is not None and item.longitude is not None
    ]
    geocoded = [
        item for item in coordinate_items if _location_status(item) in {"APPROXIMATE", "VERIFIED"}
    ]
    coverage = round((len(geocoded) / len(items)) * 100, 1) if items else 0
    identified = sum(item.territory_id is not None for item in items)
    approximate = sum(_location_status(item) == "APPROXIMATE" for item in items)
    verified = sum(_location_status(item) == "VERIFIED" for item in items)
    ambiguous = sum(_location_status(item) == "AMBIGUOUS" for item in items)
    outside = sum(_location_status(item) == "OUTSIDE_JURISDICTION" for item in items)
    overdue_ids = {item.id for item in overdue}
    open_ids = {item.id for item in open_items}
    territory_metrics: dict[str, dict] = {}
    for item in items:
        name = territory_names.get(item.territory_id, "Sem território")
        metric = territory_metrics.setdefault(
            name,
            {
                "id": str(item.territory_id) if item.territory_id else None,
                "nome": name,
                "total": 0,
                "abertas": 0,
                "atrasadas": 0,
                "geocodificadas": 0,
                "latitude": None,
                "longitude": None,
                "somaLatitude": 0.0,
                "somaLongitude": 0.0,
            },
        )
        metric["total"] += 1
        metric["abertas"] += int(item.id in open_ids)
        metric["atrasadas"] += int(item.id in overdue_ids)
        if item.latitude is not None and item.longitude is not None:
            metric["geocodificadas"] += 1
            metric["somaLatitude"] += item.latitude
            metric["somaLongitude"] += item.longitude
            metric["latitude"] = round(metric["somaLatitude"] / metric["geocodificadas"], 6)
            metric["longitude"] = round(metric["somaLongitude"] / metric["geocodificadas"], 6)
    for metric in territory_metrics.values():
        metric.pop("somaLatitude", None)
        metric.pop("somaLongitude", None)
    points = [
        {
            "id": str(item.id),
            "protocolo": item.protocol,
            "titulo": item.title,
            "status": item.status.value,
            "categoria": item.category,
            "territorio": territory_names.get(item.territory_id, "Sem território"),
            "territorioId": str(item.territory_id) if item.territory_id else None,
            "latitude": item.latitude,
            "longitude": item.longitude,
            "atrasada": item.id in overdue_ids,
            "qualidade": _location_status(item),
        }
        for item in geocoded
    ]
    review_priority = {"OUTSIDE_JURISDICTION": 0, "AMBIGUOUS": 1, "APPROXIMATE": 2}
    review_items = sorted(
        (item for item in items if _location_status(item) in review_priority),
        key=lambda item: (
            review_priority[_location_status(item)],
            item.geocode_confidence if item.geocode_confidence is not None else -1,
            item.updated_at,
        ),
    )
    location_reviews = (
        [
            {
                "id": str(item.id),
                "protocolo": item.protocol,
                "titulo": item.title,
                "categoria": item.category,
                "territorio": territory_names.get(item.territory_id, "Sem territÃ³rio"),
                "territorioId": str(item.territory_id) if item.territory_id else None,
                "status": _location_status(item),
                "confianca": item.geocode_confidence,
                "metodo": item.geocode_method,
                "latitude": item.latitude,
                "longitude": item.longitude,
            }
            for item in review_items[:20]
        ]
        if can_view_points
        else []
    )
    hotspots = sorted(
        territory_metrics.values(),
        key=lambda item: (item["abertas"], item["atrasadas"], item["total"]),
        reverse=True,
    )
    cell_safe_points = _privacy_points(points)
    private_points = cell_safe_points if can_view_points else []
    private_hotspots = [item for item in hotspots if item["total"] >= MIN_ANALYTICS_GROUP_SIZE]
    postgis = _postgis_heatmap(tenant_id, {item.id for item in geocoded})
    heatmap = postgis if postgis is not None else _local_heatmap(cell_safe_points)
    comparison = _territorial_comparison(
        items,
        comparison_items,
        territory_names,
        agency_names,
        responsible_names,
        filters,
        comparison_filters,
        can_view_points,
    )
    return {
        "metodo": "POSTGIS" if postgis is not None else "LOCAL_APROXIMADO",
        "versaoMetodo": "5.2.1",
        "geradoEm": datetime.now(UTC).isoformat(),
        "filtrosAplicados": {
            "inicio": filters["inicio"].isoformat() if filters["inicio"] else None,
            "fim": filters["fim"].isoformat() if filters["fim"] else None,
            "categoria": filters["categoria"],
            "canal": filters["canal"],
            "territorioId": str(filters["territorioId"]) if filters["territorioId"] else None,
            "orgaoId": str(filters["orgaoId"]) if filters["orgaoId"] else None,
            "granularidade": filters["granularidade"],
        },
        "jurisdicao": _jurisdiction_data(tenant),
        "coberturaPercentual": coverage,
        "geocodificadas": len(geocoded),
        "semCoordenadas": max(len(items) - len(coordinate_items), 0),
        "qualidadeDados": {
            "total": len(items),
            "territorioIdentificado": identified,
            "territorioIdentificadoPercentual": (
                round((identified / len(items)) * 100, 1) if items else 0
            ),
            "coordenadasAproximadas": approximate,
            "coordenadasVerificadas": verified,
            "coordenadasAmbiguas": ambiguous,
            "foraDaJurisdicao": outside,
            "semCoordenadas": max(len(items) - len(coordinate_items), 0),
        },
        "privacidade": {
            "minimoPorGrupo": MIN_ANALYTICS_GROUP_SIZE,
            "pontosSuprimidos": max(len(points) - len(private_points), 0),
            "hotspotsSuprimidos": max(len(hotspots) - len(private_hotspots), 0),
            "visualizacaoPontosPermitida": can_view_points,
        },
        "pontos": private_points[:200],
        "revisoesLocalizacao": {
            "total": len(review_items),
            "content": location_reviews,
            "detalhesTecnicosPermitidos": can_view_points,
        },
        "hotspots": private_hotspots[:8],
        "heatmap": heatmap,
        "comparacao": comparison["resumo"],
        "tabelaTerritorial": comparison["territorios"],
    }


def _territorial_comparison(
    items: list[ServiceRequest],
    comparison_items: list[ServiceRequest],
    territory_names: dict,
    agency_names: dict,
    responsible_names: dict,
    filters: dict,
    comparison_filters: dict,
    can_view_examples: bool,
) -> dict:
    current_cutoff = datetime.combine(
        filters["fim"] + timedelta(days=1), datetime.min.time(), tzinfo=UTC
    )
    comparison_cutoff = datetime.combine(
        comparison_filters["fim"] + timedelta(days=1), datetime.min.time(), tzinfo=UTC
    )
    current_overdue_ids = _overdue_ids_at(items, current_cutoff)
    current_groups = _group_requests_by_territory(items, territory_names)
    comparison_groups = _group_requests_by_territory(comparison_items, territory_names)
    alert_items = _recurrent_demands(
        items,
        datetime.now(UTC),
        current_overdue_ids,
        territory_names,
        can_view_examples,
    )
    alerts_by_territory: dict[str, list[dict]] = {}
    for alert in alert_items:
        alerts_by_territory.setdefault(alert["territorio"], []).append(alert)

    rows = []
    for key, current_group in current_groups.items():
        if len(current_group) < MIN_ANALYTICS_GROUP_SIZE:
            continue
        previous_group = comparison_groups.get(key, [])
        current_metrics = _territorial_period_metrics(current_group, current_cutoff)
        previous_metrics = _territorial_period_metrics(previous_group, comparison_cutoff)
        comparison_available = len(previous_group) >= MIN_ANALYTICS_GROUP_SIZE
        territory_id = current_group[0].territory_id
        territory_name = _territory_name(current_group[0], territory_names)
        request_filters = {
            "inicio": filters["inicio"].isoformat(),
            "fim": filters["fim"].isoformat(),
            "categoria": filters["categoria"],
            "canal": filters["canal"],
            "orgaoId": str(filters["orgaoId"]) if filters["orgaoId"] else None,
            "territorioId": str(territory_id) if territory_id else None,
            "semTerritorio": territory_id is None,
        }
        rows.append(
            {
                "id": str(territory_id) if territory_id else "sem-territorio",
                "nome": territory_name,
                **current_metrics,
                "estadoQualidade": (
                    "BAIXA_QUALIDADE"
                    if current_metrics["qualidadeGeograficaPercentual"] < 70
                    else "ADEQUADA"
                ),
                "tendencia": _territorial_trend(
                    current_metrics["total"],
                    previous_metrics["total"] if comparison_available else None,
                ),
                "comparacao": {
                    "estado": (
                        "DISPONIVEL"
                        if comparison_available
                        else "SEM_COMPARACAO"
                        if not previous_group
                        else "AMOSTRA_INSUFICIENTE"
                    ),
                    "amostraAtual": len(current_group),
                    "amostraAnterior": len(previous_group),
                    "metricasAnteriores": previous_metrics if comparison_available else None,
                    "variacaoVolumePercentual": _percent_change(
                        current_metrics["total"], previous_metrics["total"]
                    )
                    if comparison_available
                    else None,
                    "variacaoAtrasoPontosPercentuais": round(
                        current_metrics["percentualAtraso"] - previous_metrics["percentualAtraso"],
                        1,
                    )
                    if comparison_available
                    else None,
                    "variacaoSolucaoPontosPercentuais": round(
                        current_metrics["taxaSolucao"] - previous_metrics["taxaSolucao"],
                        1,
                    )
                    if comparison_available
                    else None,
                    "variacaoPrimeiraRespostaPercentual": _percent_change(
                        current_metrics["tempoMedianoPrimeiraRespostaHoras"],
                        previous_metrics["tempoMedianoPrimeiraRespostaHoras"],
                    )
                    if comparison_available
                    else None,
                    "variacaoResolucaoPercentual": _percent_change(
                        current_metrics["tempoMedianoResolucaoHoras"],
                        previous_metrics["tempoMedianoResolucaoHoras"],
                    )
                    if comparison_available
                    else None,
                },
                "detalhes": {
                    "categorias": _counter(
                        item.category or "Sem categoria" for item in current_group
                    ),
                    "orgaos": _counter(
                        agency_names.get(item.agency_id, "Sem órgão") for item in current_group
                    ),
                    "responsaveis": _counter(
                        responsible_names.get(item.responsible_id, "Fila geral")
                        for item in current_group
                    ),
                    "alertas": alerts_by_territory.get(territory_name, []),
                    "amostra": [
                        {
                            "id": str(item.id),
                            "protocolo": item.protocol,
                            "titulo": item.title or "Sem título",
                            "status": item.status.value,
                        }
                        for item in sorted(
                            current_group,
                            key=lambda request_item: _utc(request_item.created_at),
                            reverse=True,
                        )[:3]
                    ]
                    if can_view_examples
                    else [],
                },
                "filtroSolicitacoes": {
                    key: value for key, value in request_filters.items() if value is not None
                },
            }
        )

    rows.sort(key=lambda row: (row["total"], row["atrasadas"]), reverse=True)
    current_total = len(items)
    previous_total = len(comparison_items)
    return {
        "resumo": {
            "periodoAtual": {
                "inicio": filters["inicio"].isoformat(),
                "fim": filters["fim"].isoformat(),
                "amostra": current_total,
            },
            "periodoAnterior": {
                "inicio": comparison_filters["inicio"].isoformat(),
                "fim": comparison_filters["fim"].isoformat(),
                "amostra": previous_total,
            },
            "metodo": "JANELAS_EQUIVALENTES",
            "metodologia": (
                "Coortes de solicitações criadas em janelas equivalentes; cada coorte considera "
                "somente status, respostas e encerramentos conhecidos até o fim da própria janela."
            ),
            "estado": (
                "DISPONIVEL"
                if current_total >= MIN_ANALYTICS_GROUP_SIZE
                and previous_total >= MIN_ANALYTICS_GROUP_SIZE
                else "SEM_COMPARACAO"
                if previous_total == 0
                else "AMOSTRA_INSUFICIENTE"
            ),
            "variacaoVolumePercentual": (
                _percent_change(current_total, previous_total)
                if previous_total >= MIN_ANALYTICS_GROUP_SIZE
                else None
            ),
        },
        "territorios": rows,
    }


def _group_requests_by_territory(
    items: list[ServiceRequest], territory_names: dict
) -> dict[str, list[ServiceRequest]]:
    groups: dict[str, list[ServiceRequest]] = {}
    for item in items:
        key = str(item.territory_id) if item.territory_id else "sem-territorio"
        groups.setdefault(key, []).append(item)
    return groups


def _territorial_period_metrics(items: list[ServiceRequest], cutoff: datetime) -> dict:
    total = len(items)
    overdue_ids = _overdue_ids_at(items, cutoff)
    overdue_total = sum(item.id in overdue_ids for item in items)
    solved_total = sum(
        _status_at(item, cutoff) in {RequestStatus.RESOLVIDA, RequestStatus.ENCERRADA}
        for item in items
    )
    first_response_hours = []
    resolution_hours = []
    geocoded = 0
    for item in items:
        first_response = _first_citizen_response_at(item, cutoff)
        if first_response:
            first_response_hours.append(_hours_between(item.created_at, first_response))
        solved_events = [
            closed_at
            for closed_at, closed_status in _closure_events(item, cutoff)
            if closed_status in {RequestStatus.RESOLVIDA, RequestStatus.ENCERRADA}
        ]
        if solved_events:
            resolution_hours.append(_hours_between(item.created_at, min(solved_events)))
        geocoded += int(_location_status(item) in {"APPROXIMATE", "VERIFIED"})
    return {
        "total": total,
        "atrasadas": overdue_total,
        "solucionadas": solved_total,
        "percentualAtraso": round((overdue_total / total) * 100, 1) if total else 0,
        "taxaSolucao": round((solved_total / total) * 100, 1) if total else 0,
        "tempoMedianoPrimeiraRespostaHoras": _median(first_response_hours),
        "tempoMedianoResolucaoHoras": _median(resolution_hours),
        "qualidadeGeograficaPercentual": round((geocoded / total) * 100, 1) if total else 0,
    }


def _median(values: list[float]) -> float | None:
    return round(float(median(values)), 1) if values else None


def _percent_change(current: float | int | None, previous: float | int | None) -> float | None:
    if current is None or previous in {None, 0}:
        return None
    return round(((current - previous) / previous) * 100, 1)


def _territorial_trend(current: int, previous: int | None) -> str:
    if previous is None:
        return "SEM_COMPARACAO"
    variation = _percent_change(current, previous)
    if variation is None or abs(variation) < 5:
        return "ESTAVEL"
    return "CRESCIMENTO" if variation > 0 else "REDUCAO"


def _jurisdiction_data(tenant: Tenant | None) -> dict | None:
    if tenant is None or not tenant.jurisdiction_name:
        return None
    return {
        "tipoCasa": tenant.chamber_type,
        "nome": tenant.jurisdiction_name,
        "municipio": tenant.jurisdiction_city,
        "uf": tenant.jurisdiction_state,
        "codigoIbge": tenant.jurisdiction_ibge_code,
        "centro": {
            "latitude": tenant.jurisdiction_center_latitude,
            "longitude": tenant.jurisdiction_center_longitude,
        }
        if tenant.jurisdiction_center_latitude is not None
        and tenant.jurisdiction_center_longitude is not None
        else None,
        "limites": tenant.jurisdiction_bounds,
        "geojson": tenant.jurisdiction_geojson,
    }


def _postgis_heatmap(tenant_id: uuid.UUID, request_ids: set[uuid.UUID]) -> list[dict] | None:
    if db.engine.dialect.name != "postgresql":
        return None
    if not request_ids:
        return []
    try:
        enabled = db.session.execute(
            text("SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'postgis')")
        ).scalar()
        if not enabled:
            return None
        rows = db.session.execute(
            text(
                """
                SELECT
                    t.id AS territorio_id,
                    COALESCE(t.name, 'Sem território') AS territorio,
                    ROUND(
                        ST_Y(ST_Centroid(ST_Collect(sr.location_geography::geometry)))::numeric,
                        6
                    ) AS latitude,
                    ROUND(
                        ST_X(ST_Centroid(ST_Collect(sr.location_geography::geometry)))::numeric,
                        6
                    ) AS longitude,
                    COUNT(*)::int AS total,
                    COUNT(*) FILTER (
                        WHERE sr.status::text NOT IN ('RESOLVIDA', 'ENCERRADA', 'CANCELADA')
                    )::int AS abertas
                FROM service_requests sr
                LEFT JOIN territories t ON t.id = sr.territory_id
                WHERE sr.tenant_id = CAST(:tenant_id AS uuid)
                  AND sr.id = ANY(CAST(:request_ids AS uuid[]))
                  AND sr.location_geography IS NOT NULL
                GROUP BY t.id, territorio, ST_SnapToGrid(sr.location_geography::geometry, 0.01)
                HAVING COUNT(*) >= :min_group_size
                ORDER BY total DESC, abertas DESC
                LIMIT 20
                """
            ),
            {
                "tenant_id": str(tenant_id),
                "request_ids": "{" + ",".join(str(item) for item in request_ids) + "}",
                "min_group_size": MIN_ANALYTICS_GROUP_SIZE,
            },
        ).mappings()
    except SQLAlchemyError:
        db.session.rollback()
        return None

    return [
        {
            "territorioId": str(row["territorio_id"]) if row["territorio_id"] else None,
            "territorio": row["territorio"],
            "latitude": float(row["latitude"]),
            "longitude": float(row["longitude"]),
            "total": row["total"],
            "abertas": row["abertas"],
            "raioMetros": 1000,
        }
        for row in rows
    ]


def _local_heatmap(points: list[dict]) -> list[dict]:
    cells: dict[tuple[str, float, float], dict] = {}
    for point in points:
        latitude = round(float(point["latitude"]), 2)
        longitude = round(float(point["longitude"]), 2)
        key = (point["territorio"], latitude, longitude)
        cell = cells.setdefault(
            key,
            {
                "territorioId": point.get("territorioId"),
                "territorio": point["territorio"],
                "latitude": latitude,
                "longitude": longitude,
                "total": 0,
                "abertas": 0,
                "raioMetros": 1000,
            },
        )
        cell["total"] += 1
        cell["abertas"] += int(point["status"] not in {status.value for status in CLOSED_STATUSES})
    private_cells = [item for item in cells.values() if item["total"] >= MIN_ANALYTICS_GROUP_SIZE]
    return sorted(private_cells, key=lambda item: (item["total"], item["abertas"]), reverse=True)[
        :20
    ]


def _privacy_points(points: list[dict]) -> list[dict]:
    cells = Counter(
        (
            point["territorio"],
            round(float(point["latitude"]), 2),
            round(float(point["longitude"]), 2),
        )
        for point in points
    )
    return [
        point
        for point in points
        if cells[
            (
                point["territorio"],
                round(float(point["latitude"]), 2),
                round(float(point["longitude"]), 2),
            )
        ]
        >= MIN_ANALYTICS_GROUP_SIZE
    ]


def _demand_alerts(
    items: list[ServiceRequest],
    now: datetime,
    overdue: list[ServiceRequest],
    territory_names: dict,
    can_view_examples: bool = False,
) -> dict:
    overdue_ids = {item.id for item in overdue}
    return {
        "reincidencias": _recurrent_demands(
            items, now, overdue_ids, territory_names, can_view_examples
        ),
        "crescimentosAnormais": _anomalous_growth(items, now, territory_names),
        "regras": {
            "reincidencia": {
                "janelaDias": RECURRENCE_WINDOW_DAYS,
                "minimoDemandas": RECURRENCE_MIN_REQUESTS,
                "agrupamento": "categoria, território e célula geográfica aproximada de 1 km",
            },
            "crescimentoAnormal": {
                "janelaAtualDias": ANOMALY_CURRENT_WINDOW_DAYS,
                "janelaBaseDias": ANOMALY_BASELINE_WINDOW_DAYS,
                "minimoDemandasAtuais": ANOMALY_MIN_CURRENT_REQUESTS,
                "fatorMinimoCrescimento": ANOMALY_GROWTH_FACTOR,
            },
        },
    }


def _recurrent_demands(
    items: list[ServiceRequest],
    now: datetime,
    overdue_ids: set,
    territory_names: dict,
    can_view_examples: bool,
) -> list[dict]:
    starts_at = now - timedelta(days=RECURRENCE_WINDOW_DAYS)
    groups: dict[tuple[str, str, str], list[ServiceRequest]] = {}
    for item in items:
        if _utc(item.created_at) < starts_at:
            continue
        key = (
            _category_name(item),
            _territory_name(item, territory_names),
            _geo_cell(item),
        )
        groups.setdefault(key, []).append(item)

    alerts = []
    for (category, territory, cell), group in groups.items():
        if len(group) < RECURRENCE_MIN_REQUESTS:
            continue
        sorted_group = sorted(group, key=lambda item: _utc(item.created_at), reverse=True)
        alerts.append(
            {
                "categoria": category,
                "territorio": territory,
                "celula": cell,
                "total": len(group),
                "abertas": sum(item.status not in CLOSED_STATUSES for item in group),
                "atrasadas": sum(item.id in overdue_ids for item in group),
                "primeiraOcorrencia": min(_utc(item.created_at) for item in group).isoformat(),
                "ultimaOcorrencia": max(_utc(item.created_at) for item in group).isoformat(),
                "exemplos": [
                    {
                        "id": str(item.id),
                        "protocolo": item.protocol,
                        "titulo": item.title or "Sem título",
                    }
                    for item in sorted_group[:3]
                ]
                if can_view_examples
                else [],
                "regra": (
                    f"{len(group)} demandas em {RECURRENCE_WINDOW_DAYS} dias no mesmo recorte"
                ),
            }
        )

    return sorted(
        alerts,
        key=lambda item: (item["total"], item["abertas"], item["atrasadas"]),
        reverse=True,
    )[:8]


def _anomalous_growth(
    items: list[ServiceRequest],
    now: datetime,
    territory_names: dict,
) -> list[dict]:
    current_start = now - timedelta(days=ANOMALY_CURRENT_WINDOW_DAYS)
    baseline_start = current_start - timedelta(days=ANOMALY_BASELINE_WINDOW_DAYS)
    groups: dict[tuple[str, str], dict[str, int]] = {}

    for item in items:
        created_at = _utc(item.created_at)
        if created_at < baseline_start:
            continue
        key = (_category_name(item), _territory_name(item, territory_names))
        metric = groups.setdefault(key, {"atual": 0, "base": 0})
        if created_at >= current_start:
            metric["atual"] += 1
        elif created_at >= baseline_start:
            metric["base"] += 1

    alerts = []
    baseline_weeks = ANOMALY_BASELINE_WINDOW_DAYS / ANOMALY_CURRENT_WINDOW_DAYS
    for (category, territory), metric in groups.items():
        current_total = metric["atual"]
        baseline_weekly = metric["base"] / baseline_weeks if baseline_weeks else 0
        if current_total < ANOMALY_MIN_CURRENT_REQUESTS:
            continue
        if baseline_weekly == 0:
            growth_factor = None
            is_anomalous = True
        else:
            growth_factor = current_total / baseline_weekly
            is_anomalous = growth_factor >= ANOMALY_GROWTH_FACTOR
        if not is_anomalous:
            continue
        alerts.append(
            {
                "categoria": category,
                "territorio": territory,
                "atual": current_total,
                "baseSemanal": round(baseline_weekly, 1),
                "fatorCrescimento": round(growth_factor, 1) if growth_factor else None,
                "regra": (
                    f"{current_total} demandas nos últimos {ANOMALY_CURRENT_WINDOW_DAYS} dias"
                ),
            }
        )

    return sorted(
        alerts,
        key=lambda item: (
            item["fatorCrescimento"] if item["fatorCrescimento"] is not None else 999,
            item["atual"],
        ),
        reverse=True,
    )[:8]


def _category_name(item: ServiceRequest) -> str:
    return item.category or "Sem categoria"


def _territory_name(item: ServiceRequest, territory_names: dict) -> str:
    return territory_names.get(item.territory_id, "Sem território")


def _geo_cell(item: ServiceRequest) -> str:
    if item.latitude is None or item.longitude is None:
        return "sem-coordenadas"
    return f"{round(float(item.latitude), 2)},{round(float(item.longitude), 2)}"


def _operational_metrics(items: list[ServiceRequest]) -> dict:
    first_response_hours = []
    first_forwarding_hours = []
    closing_hours = []
    resolution_hours = []
    reopenings = 0

    for item in items:
        created_at = _utc(item.created_at)
        first_response = _first_citizen_response_at(item)
        if first_response:
            first_response_hours.append(_hours_between(created_at, first_response))

        if item.forwardings:
            first_forwarding_hours.append(
                _hours_between(created_at, item.forwardings[0].created_at)
            )

        for closed_at, closed_status in _closure_events(item):
            elapsed = _hours_between(created_at, closed_at)
            closing_hours.append(elapsed)
            if closed_status == RequestStatus.RESOLVIDA:
                resolution_hours.append(elapsed)

        reopenings += sum(1 for history in item.history if history.action == "request.reopened")

    return {
        "tempoMedioPrimeiraRespostaHoras": _average(first_response_hours),
        "tempoMedioPrimeiroEncaminhamentoHoras": _average(first_forwarding_hours),
        "tempoMedioEncerramentoHoras": _average(closing_hours),
        "tempoMedioResolucaoHoras": _average(resolution_hours),
        "primeirasRespostasRegistradas": len(first_response_hours),
        "encaminhamentosRegistrados": len(first_forwarding_hours),
        "encerramentosRegistrados": len(closing_hours),
        "resolucoesRegistradas": len(resolution_hours),
        "reaberturas": reopenings,
    }


def _first_citizen_response_at(
    item: ServiceRequest, cutoff: datetime | None = None
) -> datetime | None:
    for interaction in item.interactions:
        if (
            interaction.direction == InteractionDirection.SAIDA
            and interaction.visibility == InteractionVisibility.CIDADAO
            and (cutoff is None or _utc(interaction.created_at) < cutoff)
        ):
            return _utc(interaction.created_at)
    return None


def _closure_events(
    item: ServiceRequest, cutoff: datetime | None = None
) -> list[tuple[datetime, RequestStatus]]:
    events = []
    for history in item.history:
        if history.action != "request.updated":
            continue
        changes = history.changes or {}
        closed_change = changes.get("closed_at") or {}
        closed_at = _history_datetime(closed_change.get("depois"))
        if closed_at is None:
            continue
        status_value = (changes.get("status") or {}).get("depois") or item.status.value
        try:
            status = RequestStatus(status_value)
        except ValueError:
            continue
        if status in CLOSED_STATUSES:
            if cutoff is None or closed_at < cutoff:
                events.append((closed_at, status))
    if not events and item.closed_at:
        closed_at = _utc(item.closed_at)
        if cutoff is None or closed_at < cutoff:
            events.append((closed_at, item.status))
    return events


def _status_at(item: ServiceRequest, cutoff: datetime) -> RequestStatus:
    """Reconstitui o status conhecido imediatamente antes do corte exclusivo."""
    status = item.status
    transitions = []
    for history in item.history:
        if history.action != "request.updated" or _utc(history.created_at) < cutoff:
            continue
        status_change = (history.changes or {}).get("status") or {}
        before = status_change.get("antes")
        if before is not None:
            transitions.append((_utc(history.created_at), before))

    for _, before in sorted(transitions, key=lambda transition: transition[0], reverse=True):
        try:
            status = RequestStatus(before)
        except ValueError:
            continue
    return status


def _overdue_ids_at(items: list[ServiceRequest], cutoff: datetime) -> set[uuid.UUID]:
    return {
        item.id
        for item in items
        if item.due_at
        and _utc(item.due_at) < cutoff
        and _status_at(item, cutoff) not in CLOSED_STATUSES
    }


def _history_datetime(value) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return _utc(parsed)


def _hours_between(start: datetime, end: datetime) -> float:
    return max((_utc(end) - _utc(start)).total_seconds() / 3600, 0)


def _average(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 1) if values else None


def _geocode_reference(item: ServiceRequest, territory_names: dict) -> str | None:
    values = [
        item.address,
        territory_names.get(item.territory_id),
        item.title,
        item.description[:120] if item.description else None,
    ]
    reference = " | ".join(str(value).strip() for value in values if value and str(value).strip())
    return reference or None


def _has_jurisdiction_reference(tenant: Tenant | None) -> bool:
    if tenant is None:
        return False
    bounds = tenant.jurisdiction_bounds or {}
    has_bounds = all(
        isinstance(bounds.get(key), int | float)
        for key in ("minLatitude", "maxLatitude", "minLongitude", "maxLongitude")
    )
    return has_bounds or (
        tenant.jurisdiction_center_latitude is not None
        and tenant.jurisdiction_center_longitude is not None
    )


def _local_coordinates(reference: str, tenant: Tenant) -> tuple[float, float]:
    digest = hashlib.sha256(reference.encode("utf-8")).hexdigest()
    seed_a = int(digest[:8], 16) / 0xFFFFFFFF
    seed_b = int(digest[8:16], 16) / 0xFFFFFFFF
    bounds = tenant.jurisdiction_bounds or {}
    if all(
        isinstance(bounds.get(key), int | float)
        for key in ("minLatitude", "maxLatitude", "minLongitude", "maxLongitude")
    ):
        latitude = bounds["minLatitude"] + (bounds["maxLatitude"] - bounds["minLatitude"]) * (
            0.2 + seed_a * 0.6
        )
        longitude = bounds["minLongitude"] + (bounds["maxLongitude"] - bounds["minLongitude"]) * (
            0.2 + seed_b * 0.6
        )
        return round(latitude, 6), round(longitude, 6)
    angle = seed_a * 2 * pi
    radius = 0.005 + seed_b * 0.02
    latitude = float(tenant.jurisdiction_center_latitude) + sin(angle) * radius
    longitude = float(tenant.jurisdiction_center_longitude) + cos(angle) * radius
    return round(latitude, 6), round(longitude, 6)


def _coordinates_in_jurisdiction(latitude: float, longitude: float, tenant: Tenant | None) -> bool:
    if tenant is None:
        return False
    bounds = tenant.jurisdiction_bounds or {}
    if all(
        isinstance(bounds.get(key), int | float)
        for key in ("minLatitude", "maxLatitude", "minLongitude", "maxLongitude")
    ) and not (
        bounds["minLatitude"] <= latitude <= bounds["maxLatitude"]
        and bounds["minLongitude"] <= longitude <= bounds["maxLongitude"]
    ):
        return False
    polygons = _jurisdiction_polygons(tenant.jurisdiction_geojson)
    return not polygons or any(_point_in_ring(longitude, latitude, ring) for ring in polygons)


def _jurisdiction_polygons(geojson: dict | None) -> list[list]:
    if not isinstance(geojson, dict):
        return []
    geometries = []
    if geojson.get("type") == "FeatureCollection":
        geometries = [
            feature.get("geometry", {})
            for feature in geojson.get("features", [])
            if isinstance(feature, dict)
        ]
    elif geojson.get("type") == "Feature":
        geometries = [geojson.get("geometry", {})]
    else:
        geometries = [geojson]
    rings = []
    for geometry in geometries:
        coordinates = geometry.get("coordinates", []) if isinstance(geometry, dict) else []
        if geometry.get("type") == "Polygon" and coordinates:
            rings.append(coordinates[0])
        elif geometry.get("type") == "MultiPolygon":
            rings.extend(polygon[0] for polygon in coordinates if polygon)
    return rings


def _point_in_ring(longitude: float, latitude: float, ring: list) -> bool:
    inside = False
    if len(ring) < 3:
        return False
    previous = ring[-1]
    for current in ring:
        if not (
            isinstance(current, list | tuple)
            and isinstance(previous, list | tuple)
            and len(current) >= 2
            and len(previous) >= 2
        ):
            previous = current
            continue
        x1, y1 = float(previous[0]), float(previous[1])
        x2, y2 = float(current[0]), float(current[1])
        crosses = (y1 > latitude) != (y2 > latitude)
        if crosses and longitude < (x2 - x1) * (latitude - y1) / (y2 - y1) + x1:
            inside = not inside
        previous = current
    return inside


def _location_status(item: ServiceRequest) -> str:
    if item.geocode_verified:
        return "VERIFIED"
    status = str(item.geocode_status or "").upper()
    if status and status != "UNRESOLVED":
        return status
    if item.latitude is not None and item.longitude is not None:
        return "APPROXIMATE"
    return "UNRESOLVED"


def _counter(values) -> list[dict]:
    return _private_counter(values)["items"]


def _private_counter(values) -> dict:
    counter = Counter(values)
    items = [
        {"nome": name, "total": total}
        for name, total in counter.most_common()
        if total >= MIN_ANALYTICS_GROUP_SIZE
    ]
    suppressed = [
        {"nome": name, "total": total}
        for name, total in counter.items()
        if total < MIN_ANALYTICS_GROUP_SIZE
    ]
    return {
        "items": items,
        "suprimidos": {
            "grupos": len(suppressed),
            "registros": sum(item["total"] for item in suppressed),
        },
    }


def _dashboard_filters(args) -> dict:
    start = _parse_dashboard_date(args.get("inicio"))
    end = _parse_dashboard_date(args.get("fim"))
    if start is None and end is None:
        end = datetime.now(UTC).date()
        start = end - timedelta(days=29)
    elif start is None:
        start = end - timedelta(days=29)
    elif end is None:
        end = datetime.now(UTC).date()
    if start and end and start > end:
        raise ValueError("A data inicial nÃ£o pode ser posterior Ã  data final.")
    granularity = str(args.get("granularidade") or "dia").lower()
    if granularity not in {"dia", "mes"}:
        raise ValueError("Granularidade invÃ¡lida.")
    return {
        "inicio": start,
        "fim": end,
        "categoria": str(args.get("categoria") or "").strip() or None,
        "canal": str(args.get("canal") or "").strip().upper() or None,
        "territorioId": _optional_uuid(args.get("territorioId")),
        "orgaoId": _optional_uuid(args.get("orgaoId")),
        "granularidade": granularity,
    }


def _comparison_dashboard_filters(filters: dict) -> dict:
    window_days = (filters["fim"] - filters["inicio"]).days + 1
    comparison_end = filters["inicio"] - timedelta(days=1)
    comparison_start = comparison_end - timedelta(days=window_days - 1)
    return {
        **filters,
        "inicio": comparison_start,
        "fim": comparison_end,
    }


def _serialize_dashboard_filters(filters: dict) -> dict:
    return {
        "inicio": filters["inicio"].isoformat(),
        "fim": filters["fim"].isoformat(),
        "categoria": filters["categoria"] or "",
        "canal": filters["canal"] or "",
        "territorioId": str(filters["territorioId"]) if filters["territorioId"] else "",
        "orgaoId": str(filters["orgaoId"]) if filters["orgaoId"] else "",
        "granularidade": filters["granularidade"],
    }


def _saved_view_data(item: TerritorialSavedView) -> dict:
    return {
        "id": str(item.id),
        "nome": item.name,
        "filtros": item.filters,
        "criadaEm": item.created_at.isoformat(),
        "atualizadaEm": item.updated_at.isoformat(),
    }


def _validate_dashboard_entity_filters(tenant_id: uuid.UUID, filters: dict) -> None:
    if filters["territorioId"]:
        territory = db.session.execute(
            select(Territory.id).where(
                Territory.id == filters["territorioId"], Territory.tenant_id == tenant_id
            )
        ).scalar_one_or_none()
        if territory is None:
            raise ValueError("Território inválido para o gabinete.")
    if filters["orgaoId"]:
        agency = db.session.execute(
            select(ExternalAgency.id).where(
                ExternalAgency.id == filters["orgaoId"],
                ExternalAgency.tenant_id == tenant_id,
            )
        ).scalar_one_or_none()
        if agency is None:
            raise ValueError("Órgão inválido para o gabinete.")


def _parse_dashboard_date(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value)).date()
    except ValueError as error:
        raise ValueError("Data de filtro invÃ¡lida.") from error


def _optional_uuid(value) -> uuid.UUID | None:
    if not value:
        return None
    try:
        return uuid.UUID(str(value))
    except ValueError as error:
        raise ValueError("Identificador de filtro invÃ¡lido.") from error


def _apply_dashboard_filters(items: list[ServiceRequest], filters: dict) -> list[ServiceRequest]:
    filtered = items
    if filters["inicio"]:
        filtered = [item for item in filtered if _utc(item.created_at).date() >= filters["inicio"]]
    if filters["fim"]:
        filtered = [item for item in filtered if _utc(item.created_at).date() <= filters["fim"]]
    if filters["categoria"]:
        filtered = [item for item in filtered if (item.category or "") == filters["categoria"]]
    if filters["canal"]:
        filtered = [item for item in filtered if item.source.value == filters["canal"]]
    if filters["territorioId"]:
        filtered = [item for item in filtered if item.territory_id == filters["territorioId"]]
    if filters["orgaoId"]:
        filtered = [item for item in filtered if item.agency_id == filters["orgaoId"]]
    return filtered


def _dashboard_filter_payload(
    items: list[ServiceRequest],
    filters: dict,
    territory_names: dict,
    agency_names: dict,
) -> dict:
    return {
        "selecionados": {
            "inicio": filters["inicio"].isoformat() if filters["inicio"] else "",
            "fim": filters["fim"].isoformat() if filters["fim"] else "",
            "categoria": filters["categoria"] or "",
            "canal": filters["canal"] or "",
            "territorioId": str(filters["territorioId"]) if filters["territorioId"] else "",
            "orgaoId": str(filters["orgaoId"]) if filters["orgaoId"] else "",
            "granularidade": filters["granularidade"],
        },
        "opcoes": {
            "categorias": sorted({item.category for item in items if item.category}),
            "canais": sorted({item.source.value for item in items}),
            "territorios": _unique_options(
                {
                    "id": str(item.territory_id),
                    "nome": territory_names.get(item.territory_id),
                }
                for item in items
                if item.territory_id and territory_names.get(item.territory_id)
            ),
            "orgaos": _unique_options(
                {"id": str(item.agency_id), "nome": agency_names.get(item.agency_id)}
                for item in items
                if item.agency_id and agency_names.get(item.agency_id)
            ),
        },
    }


def _unique_options(items) -> list[dict]:
    unique = {}
    for item in items:
        unique[item["id"]] = item
    return sorted(unique.values(), key=lambda item: item["nome"])


def _period_counter(items: list[ServiceRequest], granularity: str) -> list[dict]:
    return _private_period_counter(items, granularity)["items"]


def _private_period_counter(items: list[ServiceRequest], granularity: str) -> dict:
    date_format = "%Y-%m" if granularity == "mes" else "%Y-%m-%d"
    counter = Counter(_utc(item.created_at).strftime(date_format) for item in items)
    items = [
        {"nome": key, "total": counter[key]}
        for key in sorted(counter)
        if counter[key] >= MIN_ANALYTICS_GROUP_SIZE
    ]
    suppressed = [total for total in counter.values() if total < MIN_ANALYTICS_GROUP_SIZE]
    return {
        "items": items,
        "suprimidos": {"grupos": len(suppressed), "registros": sum(suppressed)},
    }


def _privacy_summary(analytics: dict) -> dict:
    dimensions = {
        key: value["suprimidos"]
        for key, value in analytics.items()
        if value["suprimidos"]["grupos"] > 0
    }
    return {
        "minimoPorGrupo": MIN_ANALYTICS_GROUP_SIZE,
        "dimensoes": dimensions,
        "gruposSuprimidos": sum(item["grupos"] for item in dimensions.values()),
        "registrosSuprimidos": sum(item["registros"] for item in dimensions.values()),
    }


def _monthly_report_period(args) -> tuple[datetime, datetime]:
    now = datetime.now(UTC)
    try:
        year = int(args.get("ano") or now.year)
        month = int(args.get("mes") or now.month)
        starts_at = datetime(year, month, 1, tzinfo=UTC)
    except ValueError as error:
        raise ValueError("Informe ano e mês válidos para o relatório.") from error
    if year < 2000 or year > now.year + 1 or month < 1 or month > 12:
        raise ValueError("Informe ano e mês válidos para o relatório.")
    days = monthrange(year, month)[1]
    return starts_at, starts_at + timedelta(days=days)


def _custom_report_period(args) -> tuple[datetime, datetime]:
    today = datetime.now(UTC).date()
    default_start = today - timedelta(days=29)
    try:
        start_date = datetime.fromisoformat(str(args.get("inicio") or default_start)).date()
        end_date = datetime.fromisoformat(str(args.get("fim") or today)).date()
    except ValueError as error:
        raise ValueError("Informe datas válidas para o relatório.") from error
    if start_date > end_date:
        raise ValueError("A data inicial deve ser anterior ou igual à data final.")
    if (end_date - start_date).days > 730:
        raise ValueError("O período máximo para um relatório é de 731 dias.")
    return (
        datetime.combine(start_date, datetime.min.time(), tzinfo=UTC),
        datetime.combine(end_date + timedelta(days=1), datetime.min.time(), tzinfo=UTC),
    )


def _report_type(value) -> str:
    normalized = str(value or "operacional").strip().lower().replace("-", "_")
    report_types = {
        "operacional": "OPERACIONAL",
        "insights_mandato": "INSIGHTS_MANDATO",
        "insights": "INSIGHTS_MANDATO",
    }
    if normalized not in report_types:
        raise ValueError("Selecione um tipo de relatório válido.")
    return report_types[normalized]


def _executive_report_payload(
    tenant_id: uuid.UUID,
    starts_at: datetime,
    ends_at: datetime,
    report_type: str,
) -> dict:
    tenant = db.session.get(Tenant, tenant_id)
    all_items = list(
        db.session.execute(
            select(ServiceRequest)
            .where(ServiceRequest.tenant_id == tenant_id)
            .order_by(ServiceRequest.created_at.desc())
        ).scalars()
    )
    created_items = [item for item in all_items if starts_at <= _utc(item.created_at) < ends_at]
    closed_items = [
        item for item in all_items if item.closed_at and starts_at <= _utc(item.closed_at) < ends_at
    ]
    touched_items = [
        item
        for item in all_items
        if item in created_items
        or item in closed_items
        or any(starts_at <= _utc(entry.created_at) < ends_at for entry in item.interactions)
        or any(starts_at <= _utc(entry.created_at) < ends_at for entry in item.history)
        or any(starts_at <= _utc(entry.created_at) < ends_at for entry in item.tasks)
        or any(starts_at <= _utc(entry.created_at) < ends_at for entry in item.forwardings)
    ]
    touched_items = _unique_requests(touched_items)
    territory_names = {
        item.id: item.name
        for item in db.session.execute(
            select(Territory).where(Territory.tenant_id == tenant_id)
        ).scalars()
    }
    agency_names = {
        item.id: item.name
        for item in db.session.execute(
            select(ExternalAgency).where(ExternalAgency.tenant_id == tenant_id)
        ).scalars()
    }
    users = list(
        db.session.execute(
            select(User).where(User.tenant_id == tenant_id).order_by(User.name)
        ).scalars()
    )
    user_names = {item.id: item.name for item in users}
    representative_user_ids = {item.id for item in users if item.role == Role.REPRESENTATIVE}
    citizen_ids = {item.citizen_id for item in touched_items if item.citizen_id}
    citizens = (
        {
            item.id: item.name
            for item in db.session.execute(
                select(Citizen).where(Citizen.tenant_id == tenant_id, Citizen.id.in_(citizen_ids))
            ).scalars()
        }
        if citizen_ids
        else {}
    )

    overdue = [
        item
        for item in touched_items
        if item.status not in CLOSED_STATUSES and item.due_at and _utc(item.due_at) < ends_at
    ]
    unassigned = [item for item in touched_items if not item.responsible_id]
    forwarded = [
        forwarding
        for item in touched_items
        for forwarding in item.forwardings
        if starts_at <= _utc(forwarding.created_at) < ends_at
    ]
    completed_on_time = [
        item
        for item in closed_items
        if not item.due_at or _utc(item.closed_at) <= _utc(item.due_at)
    ]
    resolution_rate = _report_percentage(len(closed_items), len(touched_items))
    on_time_rate = _report_percentage(len(completed_on_time), len(closed_items))
    overdue_rate = _report_percentage(len(overdue), len(touched_items))
    unassigned_rate = _report_percentage(len(unassigned), len(touched_items))

    category_counter = Counter(item.category or "Sem categoria" for item in touched_items)
    territory_counter = Counter(
        territory_names.get(item.territory_id, "Sem território") for item in touched_items
    )
    agency_counter = Counter(
        agency_names.get(item.agency_id, "Sem órgão") for item in touched_items
    )
    channel_counter = Counter(item.source.value for item in touched_items)
    status_counter = Counter(item.status.value for item in touched_items)
    hour_counter = Counter(_utc(item.created_at).hour for item in created_items)
    citizen_counter = Counter(item.citizen_id for item in touched_items if item.citizen_id)

    duration_days = max((ends_at - starts_at).days, 1)
    time_format = "%Y-%m" if duration_days > 62 else "%Y-%m-%d"
    volume_counter = Counter(_utc(item.created_at).strftime(time_format) for item in created_items)
    volume_timeline = [
        {"nome": key, "total": total} for key, total in sorted(volume_counter.items())
    ]
    hourly = [
        {"hora": hour, "rotulo": f"{hour:02d}h", "total": hour_counter.get(hour, 0)}
        for hour in range(24)
    ]
    peak_hour = max(hourly, key=lambda item: item["total"], default=None)

    efficiency = _staff_efficiency(
        touched_items,
        starts_at,
        ends_at,
        user_names,
        max(len(touched_items), 1),
        representative_user_ids,
    )
    citizen_ranking = [
        {"id": str(citizen_id), "nome": citizens.get(citizen_id, "Cidadão"), "total": total}
        for citizen_id, total in citizen_counter.most_common(8)
        if citizens.get(citizen_id)
    ]
    request_ids = {item.id for item in touched_items}
    legislative = _legislative_report_data(tenant_id, request_ids)
    actions = _generated_actions_data(tenant_id, touched_items, starts_at, ends_at, forwarded)

    previous_starts_at = starts_at - (ends_at - starts_at)
    previous_created = [
        item for item in all_items if previous_starts_at <= _utc(item.created_at) < starts_at
    ]
    previous_closed = [
        item
        for item in all_items
        if item.closed_at and previous_starts_at <= _utc(item.closed_at) < starts_at
    ]
    volume_variation = _report_variation(len(created_items), len(previous_created))
    resolution_variation = _report_variation(len(closed_items), len(previous_closed))
    semaforo = _executive_traffic_lights(
        overdue_rate, unassigned_rate, resolution_rate, on_time_rate, actions["total"]
    )
    top_category = category_counter.most_common(1)
    top_territory = territory_counter.most_common(1)
    top_citizen = citizen_ranking[0] if citizen_ranking else None
    insights = _executive_insights(
        report_type,
        len(created_items),
        volume_variation,
        resolution_rate,
        resolution_variation,
        top_category,
        top_territory,
        top_citizen,
        peak_hour,
        actions,
        legislative,
    )
    analytics = {
        "porStatus": _private_counter(status_counter.elements()),
        "porCategoria": _private_counter(category_counter.elements()),
        "porCanal": _private_counter(channel_counter.elements()),
        "porOrgao": _private_counter(agency_counter.elements()),
        "porTerritorio": _private_counter(territory_counter.elements()),
    }
    return {
        "tipo": report_type,
        "titulo": (
            "Relatório Operacional Executivo"
            if report_type == "OPERACIONAL"
            else "Relatório de Insights do Mandato"
        ),
        "gabinete": {
            "nome": tenant.name if tenant else "Gabinete",
            "jurisdicao": tenant.jurisdiction_name if tenant else None,
        },
        "periodo": {
            "inicio": starts_at.date().isoformat(),
            "fim": (ends_at - timedelta(days=1)).date().isoformat(),
            "rotulo": (
                f"{starts_at.strftime('%d/%m/%Y')} a "
                f"{(ends_at - timedelta(days=1)).strftime('%d/%m/%Y')}"
            ),
            "dias": duration_days,
        },
        "resumo": {
            "solicitacoesRecebidas": len(created_items),
            "solicitacoesMovimentadas": len(touched_items),
            "encaminhadas": len(forwarded),
            "resolvidasOuEncerradas": len(closed_items),
            "emAberto": sum(item.status not in CLOSED_STATUSES for item in touched_items),
            "atrasadas": len(overdue),
            "taxaResolucaoPercentual": resolution_rate,
            "cumprimentoPrazoPercentual": on_time_rate,
            "semResponsavel": len(unassigned),
            "documentosLegislativos": legislative["total"],
            "acoesGeradas": actions["total"],
        },
        "comparacao": {
            "periodoAnteriorInicio": previous_starts_at.date().isoformat(),
            "periodoAnteriorFim": (starts_at - timedelta(days=1)).date().isoformat(),
            "variacaoVolumePercentual": volume_variation,
            "variacaoResolucaoPercentual": resolution_variation,
        },
        "semaforo": semaforo,
        "rankings": {
            "eficienciaEquipe": efficiency,
            "cidadaosAtuantes": citizen_ranking,
        },
        "graficos": {
            "volumePeriodo": volume_timeline,
            "horariosAtendimento": hourly,
            "territorios": _counter_items(territory_counter, 8),
            "demandasRecorrentes": _counter_items(category_counter, 8),
            "orgaos": _counter_items(agency_counter, 8),
            "canais": _counter_items(channel_counter, 8),
            "status": _counter_items(status_counter, 8),
            "producaoLegislativa": legislative["porTipo"],
            "acoesGeradas": actions["porTipo"],
        },
        "destaques": insights,
        "picoAtendimento": peak_hour,
        "producaoLegislativa": legislative,
        "acoesGeradas": actions,
        "privacidadeAgregacao": _privacy_summary(analytics),
        "evidencias": _monthly_evidence(
            touched_items[:20], starts_at, ends_at, territory_names, agency_names
        ),
        "geradoEm": datetime.now(UTC).isoformat(),
    }


def _staff_efficiency(
    items,
    starts_at,
    ends_at,
    user_names,
    total_requests,
    excluded_user_ids=None,
) -> list[dict]:
    stats = {}
    excluded_user_ids = set(excluded_user_ids or ())

    def row(user_id):
        if not user_id or user_id in excluded_user_ids:
            return None
        return stats.setdefault(
            user_id,
            {
                "id": str(user_id),
                "nome": user_names.get(user_id, "Equipe"),
                "demandas": 0,
                "resolvidas": 0,
                "noPrazo": 0,
                "interacoes": 0,
                "tarefasConcluidas": 0,
                "horasResolucao": [],
            },
        )

    for item in items:
        responsible = row(item.responsible_id)
        if responsible:
            responsible["demandas"] += 1
            if item.closed_at and starts_at <= _utc(item.closed_at) < ends_at:
                responsible["resolvidas"] += 1
                if not item.due_at or _utc(item.closed_at) <= _utc(item.due_at):
                    responsible["noPrazo"] += 1
                responsible["horasResolucao"].append(
                    max((_utc(item.closed_at) - _utc(item.created_at)).total_seconds() / 3600, 0)
                )
        for interaction in item.interactions:
            if starts_at <= _utc(interaction.created_at) < ends_at:
                author = row(interaction.author_id)
                if author:
                    author["interacoes"] += 1
        for task in item.tasks:
            if task.completed_at and starts_at <= _utc(task.completed_at) < ends_at:
                assignee = row(task.assignee_id)
                if assignee:
                    assignee["tarefasConcluidas"] += 1

    result = []
    for item in stats.values():
        resolution = _report_percentage(item["resolvidas"], item["demandas"])
        on_time = _report_percentage(item["noPrazo"], item["resolvidas"])
        activity = min(
            ((item["interacoes"] + item["tarefasConcluidas"] * 2) / total_requests) * 100,
            100,
        )
        score = round(resolution * 0.5 + on_time * 0.3 + activity * 0.2, 1)
        result.append(
            {
                **{key: value for key, value in item.items() if key != "horasResolucao"},
                "taxaResolucaoPercentual": resolution,
                "cumprimentoPrazoPercentual": on_time,
                "tempoMedioResolucaoHoras": (
                    round(sum(item["horasResolucao"]) / len(item["horasResolucao"]), 1)
                    if item["horasResolucao"]
                    else None
                ),
                "score": score,
            }
        )
    return sorted(result, key=lambda item: (-item["score"], item["nome"]))[:10]


def _legislative_report_data(tenant_id, request_ids) -> dict:
    if not request_ids:
        return {"total": 0, "demandasComDocumento": 0, "porTipo": []}
    links = list(
        db.session.execute(
            select(LegislativeDraftRequest).where(
                LegislativeDraftRequest.tenant_id == tenant_id,
                LegislativeDraftRequest.request_id.in_(request_ids),
            )
        ).scalars()
    )
    draft_ids = {item.draft_id for item in links}
    drafts = (
        list(
            db.session.execute(
                select(LegislativeDraft).where(
                    LegislativeDraft.tenant_id == tenant_id,
                    LegislativeDraft.id.in_(draft_ids),
                )
            ).scalars()
        )
        if draft_ids
        else []
    )
    counter = Counter(item.document_type.value for item in drafts)
    return {
        "total": len(drafts),
        "demandasComDocumento": len({item.request_id for item in links}),
        "porTipo": _counter_items(counter, 10),
    }


def _generated_actions_data(tenant_id, items, starts_at, ends_at, forwarded) -> dict:
    tasks = [
        task
        for item in items
        for task in item.tasks
        if starts_at <= _utc(task.created_at) < ends_at
    ]
    returns = [
        scheduled
        for item in items
        for scheduled in item.scheduled_returns
        if starts_at <= _utc(scheduled.created_at) < ends_at
    ]
    request_ids = {str(item.id) for item in items}
    territorial = [
        item
        for item in db.session.execute(
            select(TerritorialAction).where(
                TerritorialAction.tenant_id == tenant_id,
                TerritorialAction.created_at >= starts_at,
                TerritorialAction.created_at < ends_at,
            )
        ).scalars()
        if request_ids.intersection(set(item.request_ids or []))
    ]
    values = [
        {"nome": "Tarefas", "total": len(tasks)},
        {"nome": "Encaminhamentos", "total": len(forwarded)},
        {"nome": "Retornos agendados", "total": len(returns)},
        {"nome": "Ações territoriais", "total": len(territorial)},
    ]
    return {"total": sum(item["total"] for item in values), "porTipo": values}


def _executive_traffic_lights(overdue, unassigned, resolution, on_time, actions) -> list[dict]:
    result = []
    result.append(
        {
            "nivel": "problema" if overdue >= 20 else "aviso" if overdue >= 10 else "positivo",
            "titulo": "Demandas em atraso",
            "descricao": (
                f"{overdue:.1f}% das demandas movimentadas terminaram o período em atraso."
            ),
            "valor": f"{overdue:.1f}%",
        }
    )
    result.append(
        {
            "nivel": "problema" if unassigned >= 15 else "aviso" if unassigned > 0 else "positivo",
            "titulo": "Cobertura de responsáveis",
            "descricao": (
                f"{unassigned:.1f}% das demandas movimentadas estão sem responsável definido."
            ),
            "valor": f"{unassigned:.1f}%",
        }
    )
    result.append(
        {
            "nivel": "positivo"
            if resolution >= 70
            else "aviso"
            if resolution >= 45
            else "problema",
            "titulo": "Capacidade de resolução",
            "descricao": (
                f"O gabinete resolveu ou encerrou {resolution:.1f}% das demandas movimentadas."
            ),
            "valor": f"{resolution:.1f}%",
        }
    )
    result.append(
        {
            "nivel": "positivo" if on_time >= 80 else "aviso" if on_time >= 60 else "problema",
            "titulo": "Cumprimento de prazo",
            "descricao": f"{on_time:.1f}% das demandas concluídas respeitaram o prazo acordado.",
            "valor": f"{on_time:.1f}%",
        }
    )
    if actions:
        result.append(
            {
                "nivel": "positivo",
                "titulo": "Desdobramentos concretos",
                "descricao": (
                    f"As demandas originaram {actions} ações, tarefas ou "
                    "encaminhamentos no período."
                ),
                "valor": str(actions),
            }
        )
    return result


def _executive_insights(
    report_type,
    received,
    volume_variation,
    resolution,
    resolution_variation,
    top_category,
    top_territory,
    top_citizen,
    peak_hour,
    actions,
    legislative,
) -> list[dict]:
    insights = [
        {
            "tom": "neutro",
            "titulo": "Leitura do período",
            "descricao": (
                f"Foram recebidas {received} demandas, uma variação de "
                f"{volume_variation:+.1f}% em relação ao período anterior equivalente."
            ),
        }
    ]
    if top_category:
        insights.append(
            {
                "tom": "atencao",
                "titulo": "Pauta dominante",
                "descricao": (
                    f"{top_category[0][0]} liderou o período com {top_category[0][1]} demandas."
                ),
            }
        )
    if top_territory:
        insights.append(
            {
                "tom": "territorio",
                "titulo": "Pressão territorial",
                "descricao": (
                    f"{top_territory[0][0]} concentrou {top_territory[0][1]} demandas movimentadas."
                ),
            }
        )
    if report_type == "INSIGHTS_MANDATO" and top_citizen:
        insights.append(
            {
                "tom": "relacionamento",
                "titulo": "Engajamento cidadão",
                "descricao": (
                    f"{top_citizen['nome']} foi o cidadão mais atuante, com "
                    f"{top_citizen['total']} demandas no recorte."
                ),
            }
        )
    if peak_hour and peak_hour["total"]:
        insights.append(
            {
                "tom": "operacao",
                "titulo": "Pico de atendimento",
                "descricao": (
                    f"O maior volume de entradas ocorreu às {peak_hour['rotulo']}, "
                    f"com {peak_hour['total']} registros."
                ),
            }
        )
    insights.append(
        {
            "tom": "resultado",
            "titulo": "Entrega e mobilização",
            "descricao": (
                f"Taxa de resolução de {resolution:.1f}% "
                f"({resolution_variation:+.1f}% vs. período anterior), "
                f"{actions['total']} ações derivadas e {legislative['total']} "
                "documentos legislativos vinculados."
            ),
        }
    )
    return insights


def _counter_items(counter: Counter, limit: int) -> list[dict]:
    return [{"nome": str(name), "total": total} for name, total in counter.most_common(limit)]


def _report_percentage(numerator: int, denominator: int) -> float:
    return round((numerator / denominator) * 100, 1) if denominator else 0.0


def _report_variation(current: int, previous: int) -> float:
    if not previous:
        return 100.0 if current else 0.0
    return round(((current - previous) / previous) * 100, 1)


def _month_label(starts_at: datetime) -> str:
    return starts_at.strftime("%m/%Y")


def _unique_requests(items: list[ServiceRequest]) -> list[ServiceRequest]:
    unique = {}
    for item in items:
        unique[item.id] = item
    return sorted(unique.values(), key=lambda item: _utc(item.created_at), reverse=True)


def _monthly_highlights(
    items: list[ServiceRequest],
    territory_names: dict,
    agency_names: dict,
) -> list[dict]:
    categories = _private_counter(item.category or "Sem categoria" for item in items)["items"]
    territories = _private_counter(
        territory_names.get(item.territory_id, "Sem território") for item in items
    )["items"]
    agencies = _private_counter(agency_names.get(item.agency_id, "Sem órgão") for item in items)[
        "items"
    ]
    highlights = []
    if categories:
        highlights.append(
            {
                "tipo": "categoria",
                "titulo": "Tema mais recorrente",
                "descricao": (
                    f"{categories[0]['nome']} concentrou {categories[0]['total']} solicitações."
                ),
            }
        )
    if territories:
        highlights.append(
            {
                "tipo": "territorio",
                "titulo": "Território com maior volume",
                "descricao": (
                    f"{territories[0]['nome']} concentrou {territories[0]['total']} solicitações."
                ),
            }
        )
    if agencies:
        highlights.append(
            {
                "tipo": "orgao",
                "titulo": "Órgão mais acionado",
                "descricao": (
                    f"{agencies[0]['nome']} aparece em {agencies[0]['total']} solicitações."
                ),
            }
        )
    return highlights


def _monthly_evidence(
    items: list[ServiceRequest],
    starts_at: datetime,
    ends_at: datetime,
    territory_names: dict,
    agency_names: dict,
) -> list[dict]:
    evidence = []
    for item in items:
        events = _monthly_evidence_events(item, starts_at, ends_at, agency_names)
        if not events:
            continue
        evidence.append(
            {
                "protocolo": item.protocol,
                "titulo": item.title or "Sem título",
                "status": item.status.value,
                "categoria": item.category or "Sem categoria",
                "territorio": territory_names.get(item.territory_id, "Sem território"),
                "orgao": agency_names.get(item.agency_id, "Sem órgão"),
                "eventos": events,
            }
        )
    return evidence[:10]


def _monthly_evidence_events(
    item: ServiceRequest,
    starts_at: datetime,
    ends_at: datetime,
    agency_names: dict,
) -> list[dict]:
    events = []
    if item.closed_at and starts_at <= _utc(item.closed_at) < ends_at:
        events.append(
            {
                "tipo": "encerramento",
                "data": _utc(item.closed_at).isoformat(),
                "descricao": (
                    item.closing_evidence or item.closing_reason or "Encerramento registrado."
                ),
            }
        )
    for forwarding in item.forwardings:
        if starts_at <= _utc(forwarding.created_at) < ends_at:
            events.append(
                {
                    "tipo": "encaminhamento",
                    "data": _utc(forwarding.created_at).isoformat(),
                    "descricao": (
                        "Encaminhado para "
                        f"{agency_names.get(forwarding.agency_id, 'órgão externo')}"
                    ),
                    "protocoloExterno": forwarding.external_protocol,
                }
            )
        if forwarding.response_at and starts_at <= _utc(forwarding.response_at) < ends_at:
            events.append(
                {
                    "tipo": "resposta_orgao",
                    "data": _utc(forwarding.response_at).isoformat(),
                    "descricao": forwarding.response or "Resposta do órgão registrada.",
                    "protocoloExterno": forwarding.external_protocol,
                }
            )
    for interaction in item.interactions:
        if interaction.direction != InteractionDirection.SAIDA:
            continue
        if starts_at <= _utc(interaction.created_at) < ends_at:
            events.append(
                {
                    "tipo": "comunicacao_cidadao",
                    "data": _utc(interaction.created_at).isoformat(),
                    "descricao": _truncate(interaction.content, 180),
                    "canal": interaction.channel,
                }
            )
    return sorted(events, key=lambda event: event["data"])[:5]


def _truncate(value: str, limit: int) -> str:
    clean = " ".join(str(value or "").split())
    if len(clean) <= limit:
        return clean
    return f"{clean[: limit - 1].rstrip()}…"


def _utc(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def _contact_destination(citizen: Citizen | None, channel: str) -> str | None:
    if citizen is None:
        return None
    accepted_types = {
        "WHATSAPP": {"WHATSAPP", "TELEFONE", "CELULAR"},
        "TELEFONE": {"TELEFONE", "CELULAR", "WHATSAPP"},
        "EMAIL": {"EMAIL"},
    }.get(channel, set())
    for contact in citizen.contacts or []:
        if str(contact.get("tipo", "")).upper() in accepted_types:
            return str(contact.get("valor", "")).strip() or None
    if channel == "PRESENCIAL" and citizen.addresses:
        address = citizen.addresses[0]
        return str(address.get("endereco") or address.get("logradouro") or "").strip() or None
    return None


def _attempt_summary(item: ContactAttempt) -> str:
    result = item.outcome.value.replace("_", " ").lower()
    summary = f"Tentativa via {item.channel}: {result}."
    if item.notes:
        summary += f" {item.notes}"
    return summary
