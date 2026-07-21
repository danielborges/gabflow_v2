import uuid

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt, jwt_required
from sqlalchemy import or_, select

from app.extensions import db
from app.models import (
    AgendaEvent,
    ChannelMessage,
    Citizen,
    LegislativeDraft,
    Organization,
    OversightAction,
    ServiceRequest,
    Tenant,
)
from app.modules import normalize_modules

search_bp = Blueprint("search", __name__)


@search_bp.get("/busca")
@jwt_required()
def global_search():
    tenant_id = uuid.UUID(get_jwt()["tenant_id"])
    tenant = db.session.get(Tenant, tenant_id)
    enabled_modules = set(normalize_modules(tenant.enabled_modules if tenant else []))
    query = str(request.args.get("q", "")).strip()
    if len(query) < 2:
        return jsonify(content=[])
    pattern = f"%{query[:100]}%"
    results = []
    if "solicitacoes" in enabled_modules:
        results.extend(_request_results(tenant_id, pattern))
    if "cidadaos" in enabled_modules:
        results.extend(_citizen_results(tenant_id, pattern))
        results.extend(_organization_results(tenant_id, pattern))
    if "agenda" in enabled_modules:
        results.extend(_agenda_results(tenant_id, pattern))
    if "fiscalizacao" in enabled_modules:
        results.extend(_oversight_results(tenant_id, pattern))
    if "canais" in enabled_modules:
        results.extend(_channel_results(tenant_id, pattern))
    if "documentos" in enabled_modules:
        results.extend(_draft_results(tenant_id, pattern))
    return jsonify(content=results[:20])


def _request_results(tenant_id: uuid.UUID, pattern: str) -> list[dict]:
    items = db.session.execute(
        select(ServiceRequest)
        .where(
            ServiceRequest.tenant_id == tenant_id,
            or_(
                ServiceRequest.protocol.ilike(pattern),
                ServiceRequest.title.ilike(pattern),
                ServiceRequest.description.ilike(pattern),
                ServiceRequest.address.ilike(pattern),
            ),
        )
        .order_by(ServiceRequest.updated_at.desc())
        .limit(5)
    ).scalars()
    return [
        _result(
            "SOLICITACAO",
            "Solicitações",
            "requests",
            item.id,
            item.protocol,
            item.title or item.description,
            item.status.value,
            search=item.protocol,
        )
        for item in items
    ]


def _citizen_results(tenant_id: uuid.UUID, pattern: str) -> list[dict]:
    items = db.session.execute(
        select(Citizen)
        .where(
            Citizen.tenant_id == tenant_id,
            Citizen.anonymized_at.is_(None),
            or_(Citizen.name.ilike(pattern), Citizen.social_name.ilike(pattern)),
        )
        .order_by(Citizen.updated_at.desc())
        .limit(4)
    ).scalars()
    return [
        _result("CIDADAO", "Cidadãos", "citizens", item.id, item.name, item.social_name, "Cadastro")
        for item in items
    ]


def _organization_results(tenant_id: uuid.UUID, pattern: str) -> list[dict]:
    items = db.session.execute(
        select(Organization)
        .where(
            Organization.tenant_id == tenant_id,
            or_(Organization.name.ilike(pattern), Organization.territory.ilike(pattern)),
        )
        .order_by(Organization.updated_at.desc())
        .limit(4)
    ).scalars()
    return [
        _result(
            "ORGANIZACAO",
            "Organizações",
            "citizens",
            item.id,
            item.name,
            item.territory,
            item.organization_type,
        )
        for item in items
    ]


def _agenda_results(tenant_id: uuid.UUID, pattern: str) -> list[dict]:
    items = db.session.execute(
        select(AgendaEvent)
        .where(
            AgendaEvent.tenant_id == tenant_id,
            or_(
                AgendaEvent.title.ilike(pattern),
                AgendaEvent.description.ilike(pattern),
                AgendaEvent.location.ilike(pattern),
            ),
        )
        .order_by(AgendaEvent.starts_at.desc())
        .limit(4)
    ).scalars()
    return [
        _result(
            "AGENDA",
            "Agenda",
            "agenda",
            item.id,
            item.title,
            item.location,
            item.status.value,
        )
        for item in items
    ]


def _oversight_results(tenant_id: uuid.UUID, pattern: str) -> list[dict]:
    items = db.session.execute(
        select(OversightAction)
        .where(
            OversightAction.tenant_id == tenant_id,
            or_(
                OversightAction.title.ilike(pattern),
                OversightAction.description.ilike(pattern),
                OversightAction.location.ilike(pattern),
                OversightAction.report.ilike(pattern),
            ),
        )
        .order_by(OversightAction.updated_at.desc())
        .limit(4)
    ).scalars()
    return [
        _result(
            "FISCALIZACAO",
            "Fiscalização",
            "oversight",
            item.id,
            item.title,
            item.location,
            item.status.value,
        )
        for item in items
    ]


def _channel_results(tenant_id: uuid.UUID, pattern: str) -> list[dict]:
    items = db.session.execute(
        select(ChannelMessage)
        .where(
            ChannelMessage.tenant_id == tenant_id,
            or_(
                ChannelMessage.sender_name.ilike(pattern),
                ChannelMessage.sender_contact.ilike(pattern),
                ChannelMessage.subject.ilike(pattern),
                ChannelMessage.content.ilike(pattern),
                ChannelMessage.external_id.ilike(pattern),
            ),
        )
        .order_by(ChannelMessage.received_at.desc())
        .limit(4)
    ).scalars()
    return [
        _result(
            "CANAL",
            "Canais",
            "channels",
            item.id,
            item.subject or item.sender_name or item.channel.value,
            item.content,
            item.channel.value,
        )
        for item in items
    ]


def _draft_results(tenant_id: uuid.UUID, pattern: str) -> list[dict]:
    items = db.session.execute(
        select(LegislativeDraft)
        .where(
            LegislativeDraft.tenant_id == tenant_id,
            or_(
                LegislativeDraft.title.ilike(pattern),
                LegislativeDraft.content.ilike(pattern),
                LegislativeDraft.protocol_number.ilike(pattern),
            ),
        )
        .order_by(LegislativeDraft.updated_at.desc())
        .limit(4)
    ).scalars()
    return [
        _result(
            "MINUTA",
            "Documentos",
            "documents",
            item.id,
            item.title,
            item.protocol_number,
            item.status.value,
        )
        for item in items
    ]


def _result(
    kind: str,
    category: str,
    view: str,
    item_id,
    title: str | None,
    subtitle: str | None,
    meta: str | None,
    *,
    search: str | None = None,
) -> dict:
    return {
        "tipo": kind,
        "categoria": category,
        "view": view,
        "id": str(item_id),
        "titulo": str(title or "Sem título")[:180],
        "subtitulo": str(subtitle or "")[:240] or None,
        "meta": str(meta or "")[:80] or None,
        "pesquisa": search,
    }
