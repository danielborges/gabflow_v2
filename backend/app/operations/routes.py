import hashlib
import secrets
import uuid
from collections import Counter
from datetime import UTC, datetime

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt, get_jwt_identity, jwt_required
from sqlalchemy import select

from app.audit import add_audit
from app.extensions import db, limiter
from app.models import (
    Citizen,
    ContactAttempt,
    ContactAttemptOutcome,
    ExternalAgency,
    ForwardingStatus,
    InteractionDirection,
    InteractionVisibility,
    RequestForwarding,
    RequestHistory,
    RequestInteraction,
    RequestStatus,
    RequestTask,
    ScheduledReturn,
    ScheduledReturnStatus,
    ServiceRequest,
    TaskStatus,
    Territory,
)

operations_bp = Blueprint("operations", __name__)
public_bp = Blueprint("public_requests", __name__)

CLOSED_STATUSES = {
    RequestStatus.RESOLVIDA,
    RequestStatus.ENCERRADA,
    RequestStatus.CANCELADA,
}


def _context() -> tuple[uuid.UUID, uuid.UUID]:
    return uuid.UUID(get_jwt()["tenant_id"]), uuid.UUID(get_jwt_identity())


def _service_request(request_id: uuid.UUID, tenant_id: uuid.UUID) -> ServiceRequest | None:
    return db.session.execute(
        select(ServiceRequest).where(
            ServiceRequest.id == request_id,
            ServiceRequest.tenant_id == tenant_id,
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
@jwt_required()
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
@jwt_required()
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
@jwt_required()
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
@jwt_required()
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
@jwt_required()
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
    now = datetime.now(UTC)
    from app.communications.service import generate_return_reminders, scheduled_return_data

    if generate_return_reminders(tenant_id, user_id):
        db.session.commit()
    items = list(
        db.session.execute(
            select(ServiceRequest)
            .where(ServiceRequest.tenant_id == tenant_id)
            .order_by(ServiceRequest.created_at.desc())
        ).scalars()
    )
    open_items = [item for item in items if item.status not in CLOSED_STATUSES]
    overdue = [item for item in open_items if item.due_at and _utc(item.due_at) < now]
    near_due = [
        item
        for item in open_items
        if item.due_at and 0 <= (_utc(item.due_at) - now).total_seconds() <= 86400
    ]
    resolution_hours = [
        (_utc(item.closed_at) - _utc(item.created_at)).total_seconds() / 3600
        for item in items
        if item.closed_at
    ]
    territory_names = {
        item.id: item.name
        for item in db.session.execute(
            select(Territory).where(Territory.tenant_id == tenant_id)
        ).scalars()
    }
    pending_tasks = db.session.execute(
        select(RequestTask).where(
            RequestTask.tenant_id == tenant_id,
            RequestTask.status.in_([TaskStatus.PENDENTE, TaskStatus.EM_ANDAMENTO]),
        )
    ).scalars()
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
    overdue_returns = [
        item for item in active_returns if _utc(item.scheduled_at) < now
    ]
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
            "tempoMedioResolucaoHoras": (
                round(sum(resolution_hours) / len(resolution_hours), 1)
                if resolution_hours
                else None
            ),
        },
        porStatus=_counter(item.status.value for item in items),
        porCategoria=_counter(item.category or "Sem categoria" for item in items),
        porOrigem=_counter(item.source.value for item in items),
        porTerritorio=_counter(
            territory_names.get(item.territory_id, "Sem território") for item in items
        ),
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
    )


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


def _counter(values) -> list[dict]:
    return [{"nome": name, "total": total} for name, total in Counter(values).most_common()]


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
