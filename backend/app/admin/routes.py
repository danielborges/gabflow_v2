import uuid

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt, get_jwt_identity
from sqlalchemy import select

from app.audit import add_audit
from app.auth.permissions import roles_required
from app.extensions import db
from app.models import ExternalAgency, RequestCategory, Territory

admin_bp = Blueprint("admin", __name__)


def _context() -> tuple[uuid.UUID, uuid.UUID]:
    return uuid.UUID(get_jwt()["tenant_id"]), uuid.UUID(get_jwt_identity())


def _serialize(item: RequestCategory) -> dict:
    return {
        "id": str(item.id),
        "nome": item.name,
        "categoriaPaiId": str(item.parent_id) if item.parent_id else None,
        "slaHoras": item.sla_hours,
        "ativa": item.active,
    }


def _simple_data(item) -> dict:
    data = {"id": str(item.id), "nome": item.name, "ativa": item.active}
    if isinstance(item, ExternalAgency):
        data["emailContato"] = item.contact_email
    return data


@admin_bp.get("/categorias")
@roles_required("admin", "manager", "staff")
def list_categories():
    tenant_id, _ = _context()
    items = db.session.execute(
        select(RequestCategory)
        .where(RequestCategory.tenant_id == tenant_id)
        .order_by(RequestCategory.name)
    ).scalars()
    return jsonify(content=[_serialize(item) for item in items])


@admin_bp.post("/categorias")
@roles_required("admin", "manager")
def create_category():
    tenant_id, user_id = _context()
    payload = request.get_json(silent=True) or {}
    name = str(payload.get("nome", "")).strip()
    sla_hours = payload.get("slaHoras", 72)
    if len(name) < 2:
        return jsonify(error="validation_error", message="Informe o nome da categoria."), 422
    try:
        sla_hours = int(sla_hours)
    except (TypeError, ValueError):
        return jsonify(error="validation_error", message="SLA inválido."), 422
    if not 1 <= sla_hours <= 8760:
        return jsonify(
            error="validation_error", message="SLA deve estar entre 1 e 8760 horas."
        ), 422

    parent_id = payload.get("categoriaPaiId")
    parent_uuid = uuid.UUID(parent_id) if parent_id else None
    if parent_uuid:
        parent = db.session.execute(
            select(RequestCategory).where(
                RequestCategory.id == parent_uuid,
                RequestCategory.tenant_id == tenant_id,
            )
        ).scalar_one_or_none()
        if parent is None:
            return jsonify(error="validation_error", message="Categoria pai inválida."), 422

    item = RequestCategory(
        tenant_id=tenant_id,
        name=name,
        parent_id=parent_uuid,
        sla_hours=sla_hours,
    )
    db.session.add(item)
    db.session.flush()
    add_audit(
        tenant_id,
        user_id,
        "category.created",
        "request_category",
        item.id,
        after=_serialize(item),
    )
    db.session.commit()
    return jsonify(_serialize(item)), 201


@admin_bp.patch("/categorias/<uuid:category_id>")
@roles_required("admin", "manager")
def update_category(category_id: uuid.UUID):
    tenant_id, user_id = _context()
    item = db.session.execute(
        select(RequestCategory).where(
            RequestCategory.id == category_id,
            RequestCategory.tenant_id == tenant_id,
        )
    ).scalar_one_or_none()
    if item is None:
        return jsonify(error="resource_not_found", message="Categoria não encontrada."), 404
    payload = request.get_json(silent=True) or {}
    before = _serialize(item)
    if "nome" in payload:
        name = str(payload["nome"]).strip()
        if len(name) < 2:
            return jsonify(error="validation_error", message="Informe o nome da categoria."), 422
        item.name = name
    if "slaHoras" in payload:
        try:
            sla_hours = int(payload["slaHoras"])
        except (TypeError, ValueError):
            return jsonify(error="validation_error", message="SLA inválido."), 422
        if not 1 <= sla_hours <= 8760:
            return jsonify(
                error="validation_error", message="SLA deve estar entre 1 e 8760 horas."
            ), 422
        item.sla_hours = sla_hours
    if "ativa" in payload:
        item.active = bool(payload["ativa"])
    after = _serialize(item)
    add_audit(
        tenant_id,
        user_id,
        "category.updated",
        "request_category",
        item.id,
        before,
        after,
    )
    db.session.commit()
    return jsonify(after)


@admin_bp.get("/territorios")
@roles_required("admin", "manager", "staff")
def list_territories():
    tenant_id, _ = _context()
    items = db.session.execute(
        select(Territory).where(Territory.tenant_id == tenant_id).order_by(Territory.name)
    ).scalars()
    return jsonify(content=[_simple_data(item) for item in items])


@admin_bp.post("/territorios")
@roles_required("admin", "manager")
def create_territory():
    tenant_id, user_id = _context()
    name = str((request.get_json(silent=True) or {}).get("nome", "")).strip()
    if len(name) < 2:
        return jsonify(error="validation_error", message="Informe o nome do território."), 422
    item = Territory(tenant_id=tenant_id, name=name)
    db.session.add(item)
    db.session.flush()
    add_audit(
        tenant_id, user_id, "territory.created", "territory", item.id, after=_simple_data(item)
    )
    db.session.commit()
    return jsonify(_simple_data(item)), 201


@admin_bp.get("/orgaos")
@roles_required("admin", "manager", "staff")
def list_agencies():
    tenant_id, _ = _context()
    items = db.session.execute(
        select(ExternalAgency)
        .where(ExternalAgency.tenant_id == tenant_id)
        .order_by(ExternalAgency.name)
    ).scalars()
    return jsonify(content=[_simple_data(item) for item in items])


@admin_bp.post("/orgaos")
@roles_required("admin", "manager")
def create_agency():
    tenant_id, user_id = _context()
    payload = request.get_json(silent=True) or {}
    name = str(payload.get("nome", "")).strip()
    email = str(payload.get("emailContato", "")).strip() or None
    if len(name) < 2:
        return jsonify(error="validation_error", message="Informe o nome do órgão."), 422
    item = ExternalAgency(tenant_id=tenant_id, name=name, contact_email=email)
    db.session.add(item)
    db.session.flush()
    add_audit(
        tenant_id, user_id, "agency.created", "external_agency", item.id, after=_simple_data(item)
    )
    db.session.commit()
    return jsonify(_simple_data(item)), 201
