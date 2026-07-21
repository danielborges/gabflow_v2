import uuid
from datetime import UTC, datetime

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt, get_jwt_identity, jwt_required
from sqlalchemy import select

from app.audit import add_audit
from app.extensions import db
from app.models import ExternalAgency, OversightAction, OversightActionStatus, ServiceRequest

oversight_bp = Blueprint("oversight", __name__)


def _context() -> tuple[uuid.UUID, uuid.UUID]:
    return uuid.UUID(get_jwt()["tenant_id"]), uuid.UUID(get_jwt_identity())


@oversight_bp.get("/fiscalizacoes")
@jwt_required()
def list_actions():
    tenant_id, _ = _context()
    items = db.session.execute(
        select(OversightAction)
        .where(OversightAction.tenant_id == tenant_id)
        .order_by(OversightAction.created_at.desc())
    ).scalars()
    return jsonify(content=[action_data(item) for item in items])


@oversight_bp.post("/fiscalizacoes")
@jwt_required()
def create_action():
    tenant_id, user_id = _context()
    payload = request.get_json(silent=True) or {}
    try:
        values = _action_values(payload)
    except ValueError as error:
        return jsonify(error="validation_error", message=str(error)), 422
    relationships = _relationships(payload, tenant_id)
    if isinstance(relationships, tuple):
        return relationships
    item = OversightAction(
        tenant_id=tenant_id,
        created_by_id=user_id,
        **values,
        **relationships,
    )
    db.session.add(item)
    db.session.flush()
    add_audit(
        tenant_id,
        user_id,
        "oversight.action.created",
        "oversight_action",
        item.id,
        after=action_data(item),
    )
    db.session.commit()
    return jsonify(action_data(item)), 201


@oversight_bp.patch("/fiscalizacoes/<uuid:action_id>")
@jwt_required()
def update_action(action_id: uuid.UUID):
    tenant_id, user_id = _context()
    item = _action_or_none(action_id, tenant_id)
    if item is None:
        return jsonify(error="resource_not_found", message="Fiscalização não encontrada."), 404
    payload = request.get_json(silent=True) or {}
    before = action_data(item)
    if "status" in payload:
        try:
            item.status = OversightActionStatus(str(payload["status"]).upper())
        except ValueError:
            return jsonify(error="validation_error", message="Status inválido."), 422
    for field_name, attr in (
        ("titulo", "title"),
        ("descricao", "description"),
        ("local", "location"),
        ("relatorio", "report"),
    ):
        if field_name in payload:
            setattr(item, attr, str(payload[field_name]).strip() or None)
    if "realizadaEm" in payload:
        item.occurred_at = _optional_datetime(payload["realizadaEm"])
    for field_name, attr in (
        ("achados", "findings"),
        ("fotos", "photos"),
        ("responsaveis", "responsible_parties"),
        ("providencias", "follow_up_actions"),
    ):
        if field_name in payload:
            try:
                setattr(item, attr, _list_value(payload[field_name], field_name))
            except ValueError as error:
                return jsonify(error="validation_error", message=str(error)), 422
    after = action_data(item)
    add_audit(
        tenant_id,
        user_id,
        "oversight.action.updated",
        "oversight_action",
        item.id,
        before,
        after,
    )
    db.session.commit()
    return jsonify(after)


@oversight_bp.get("/fiscalizacoes/<uuid:action_id>/relatorio")
@jwt_required()
def action_report(action_id: uuid.UUID):
    tenant_id, _ = _context()
    item = _action_or_none(action_id, tenant_id)
    if item is None:
        return jsonify(error="resource_not_found", message="Fiscalização não encontrada."), 404
    return jsonify(
        titulo=item.title,
        status=item.status.value,
        local=item.location,
        realizadaEm=item.occurred_at.isoformat() if item.occurred_at else None,
        relatorio=item.report or _generated_report(item),
        achados=item.findings,
        responsaveis=item.responsible_parties,
        providencias=item.follow_up_actions,
    )


def action_data(item: OversightAction) -> dict:
    return {
        "id": str(item.id),
        "status": item.status.value,
        "titulo": item.title,
        "descricao": item.description,
        "local": item.location,
        "realizadaEm": item.occurred_at.isoformat() if item.occurred_at else None,
        "orgaoId": str(item.agency_id) if item.agency_id else None,
        "solicitacaoId": str(item.request_id) if item.request_id else None,
        "achados": item.findings,
        "fotos": item.photos,
        "responsaveis": item.responsible_parties,
        "relatorio": item.report,
        "providencias": item.follow_up_actions,
        "criadaEm": item.created_at.isoformat(),
    }


def _action_values(payload: dict) -> dict:
    title = str(payload.get("titulo", "")).strip()
    if len(title) < 3:
        raise ValueError("Informe o título da fiscalização.")
    try:
        status = OversightActionStatus(str(payload.get("status", "PLANEJADA")).upper())
    except ValueError as error:
        raise ValueError("Status inválido.") from error
    return {
        "status": status,
        "title": title,
        "description": str(payload.get("descricao", "")).strip() or None,
        "location": str(payload.get("local", "")).strip() or None,
        "occurred_at": _optional_datetime(payload.get("realizadaEm")),
        "findings": _list_value(payload.get("achados", []), "achados"),
        "photos": _list_value(payload.get("fotos", []), "fotos"),
        "responsible_parties": _list_value(payload.get("responsaveis", []), "responsaveis"),
        "report": str(payload.get("relatorio", "")).strip() or None,
        "follow_up_actions": _list_value(payload.get("providencias", []), "providencias"),
    }


def _relationships(payload: dict, tenant_id: uuid.UUID):
    agency = _tenant_entity(ExternalAgency, payload.get("orgaoId"), tenant_id)
    service_request = _tenant_entity(ServiceRequest, payload.get("solicitacaoId"), tenant_id)
    if payload.get("orgaoId") and agency is None:
        return jsonify(error="validation_error", message="Órgão inválido."), 422
    if payload.get("solicitacaoId") and service_request is None:
        return jsonify(error="validation_error", message="Solicitação inválida."), 422
    return {
        "agency_id": agency.id if agency else None,
        "request_id": service_request.id if service_request else None,
    }


def _action_or_none(action_id: uuid.UUID, tenant_id: uuid.UUID) -> OversightAction | None:
    return db.session.execute(
        select(OversightAction).where(
            OversightAction.id == action_id,
            OversightAction.tenant_id == tenant_id,
        )
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


def _optional_datetime(value) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError("Data inválida.") from error
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _list_value(value, label: str) -> list:
    if value in (None, ""):
        return []
    if not isinstance(value, list):
        raise ValueError(f"{label} deve ser uma lista.")
    return value


def _generated_report(item: OversightAction) -> str:
    lines = [item.title]
    if item.location:
        lines.append(f"Local: {item.location}")
    if item.findings:
        lines.append("Achados: " + "; ".join(str(value) for value in item.findings))
    if item.follow_up_actions:
        lines.append("Providências: " + "; ".join(str(value) for value in item.follow_up_actions))
    return "\n".join(lines)
