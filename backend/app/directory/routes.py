import uuid
from datetime import UTC, datetime

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt, get_jwt_identity, jwt_required
from sqlalchemy import or_, select

from app.audit import add_audit
from app.auth.permissions import roles_required
from app.extensions import db
from app.models import Citizen, Organization, User, UserStatus
from app.privacy.service import record_consent

directory_bp = Blueprint("directory", __name__)


def _context() -> tuple[uuid.UUID, uuid.UUID]:
    return uuid.UUID(get_jwt()["tenant_id"]), uuid.UUID(get_jwt_identity())


def _validate_collection(value, field: str) -> list:
    if value is None:
        return []
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise ValueError(f"{field} deve ser uma lista de objetos.")
    return value


def _citizen_data(item: Citizen, include_history: bool = False) -> dict:
    data = {
        "id": str(item.id),
        "nome": item.name,
        "nomeSocial": item.social_name,
        "contatos": item.contacts,
        "enderecos": item.addresses,
        "canalPreferencial": item.preferred_channel,
        "consentimentoContato": item.contact_consent,
        "consentimentoDivulgacao": item.publication_consent,
        "baseLegal": item.legal_basis,
        "flagsPrivacidade": item.privacy_flags,
        "observacoes": item.notes,
        "anonimizadoEm": item.anonymized_at.isoformat() if item.anonymized_at else None,
        "criadoEm": item.created_at.isoformat(),
        "atualizadoEm": item.updated_at.isoformat(),
    }
    if include_history:
        from app.models import ServiceRequest

        requests = db.session.execute(
            select(ServiceRequest)
            .where(
                ServiceRequest.tenant_id == item.tenant_id,
                ServiceRequest.citizen_id == item.id,
            )
            .order_by(ServiceRequest.created_at.desc())
        ).scalars()
        data["solicitacoes"] = [
            {
                "id": str(service_request.id),
                "protocolo": service_request.protocol,
                "titulo": service_request.title,
                "status": service_request.status.value,
                "criadaEm": service_request.created_at.isoformat(),
            }
            for service_request in requests
        ]
    return data


def _organization_data(item: Organization) -> dict:
    return {
        "id": str(item.id),
        "tipo": item.organization_type,
        "nome": item.name,
        "contatos": item.contacts,
        "enderecos": item.addresses,
        "territorio": item.territory,
        "observacoes": item.notes,
        "criadaEm": item.created_at.isoformat(),
        "atualizadaEm": item.updated_at.isoformat(),
    }


@directory_bp.get("/usuarios")
@jwt_required()
def list_users():
    tenant_id, _ = _context()
    users = db.session.execute(
        select(User)
        .where(User.tenant_id == tenant_id, User.status == UserStatus.ACTIVE)
        .order_by(User.name)
    ).scalars()
    return jsonify(
        content=[
            {"id": str(user.id), "nome": user.name, "email": user.email, "perfil": user.role.value}
            for user in users
        ]
    )


@directory_bp.get("/cidadaos")
@jwt_required()
def list_citizens():
    tenant_id, _ = _context()
    query = str(request.args.get("q", "")).strip()
    filters = [Citizen.tenant_id == tenant_id, Citizen.anonymized_at.is_(None)]
    if query:
        pattern = f"%{query}%"
        filters.append(or_(Citizen.name.ilike(pattern), Citizen.social_name.ilike(pattern)))
    items = db.session.execute(
        select(Citizen).where(*filters).order_by(Citizen.name).limit(100)
    ).scalars()
    return jsonify(content=[_citizen_data(item) for item in items])


@directory_bp.post("/cidadaos")
@jwt_required()
def create_citizen():
    tenant_id, user_id = _context()
    payload = request.get_json(silent=True) or {}
    name = str(payload.get("nome", "")).strip()
    legal_basis = str(payload.get("baseLegal", "")).strip()
    if len(name) < 2 or not legal_basis:
        return (
            jsonify(
                error="validation_error",
                message="Informe nome e base legal para o tratamento.",
            ),
            422,
        )
    try:
        contacts = _validate_collection(payload.get("contatos"), "Contatos")
        addresses = _validate_collection(payload.get("enderecos"), "Endereços")
        privacy_flags = payload.get("flagsPrivacidade") or []
        if not isinstance(privacy_flags, list):
            raise ValueError("Flags de privacidade deve ser uma lista.")
    except ValueError as error:
        return jsonify(error="validation_error", message=str(error)), 422

    item = Citizen(
        tenant_id=tenant_id,
        name=name,
        social_name=str(payload.get("nomeSocial", "")).strip() or None,
        contacts=contacts,
        addresses=addresses,
        preferred_channel=str(payload.get("canalPreferencial", "")).strip() or None,
        contact_consent=bool(payload.get("consentimentoContato", False)),
        publication_consent=bool(payload.get("consentimentoDivulgacao", False)),
        legal_basis=legal_basis,
        privacy_flags=privacy_flags,
        notes=str(payload.get("observacoes", "")).strip() or None,
    )
    db.session.add(item)
    db.session.flush()
    record_consent(
        tenant_id=tenant_id,
        citizen_id=item.id,
        user_id=user_id,
        purpose="CONTATO",
        granted=item.contact_consent,
        legal_basis=item.legal_basis,
        source="CADASTRO",
    )
    record_consent(
        tenant_id=tenant_id,
        citizen_id=item.id,
        user_id=user_id,
        purpose="DIVULGACAO",
        granted=item.publication_consent,
        legal_basis=item.legal_basis,
        source="CADASTRO",
    )
    add_audit(
        tenant_id,
        user_id,
        "citizen.created",
        "citizen",
        item.id,
        after={"nome": item.name, "baseLegal": item.legal_basis},
    )
    db.session.commit()
    return jsonify(_citizen_data(item)), 201


@directory_bp.get("/cidadaos/<uuid:citizen_id>")
@jwt_required()
def get_citizen(citizen_id: uuid.UUID):
    tenant_id, _ = _context()
    item = db.session.execute(
        select(Citizen).where(Citizen.id == citizen_id, Citizen.tenant_id == tenant_id)
    ).scalar_one_or_none()
    if item is None:
        return jsonify(error="resource_not_found", message="Cidadão não encontrado."), 404
    return jsonify(_citizen_data(item, include_history=True))


@directory_bp.patch("/cidadaos/<uuid:citizen_id>")
@jwt_required()
def update_citizen(citizen_id: uuid.UUID):
    tenant_id, user_id = _context()
    item = db.session.execute(
        select(Citizen).where(Citizen.id == citizen_id, Citizen.tenant_id == tenant_id)
    ).scalar_one_or_none()
    if item is None:
        return jsonify(error="resource_not_found", message="Cidadão não encontrado."), 404
    payload = request.get_json(silent=True) or {}
    before = _citizen_data(item)
    mappings = {
        "nome": "name",
        "nomeSocial": "social_name",
        "canalPreferencial": "preferred_channel",
        "baseLegal": "legal_basis",
        "observacoes": "notes",
    }
    for api_name, attribute in mappings.items():
        if api_name in payload:
            setattr(item, attribute, str(payload[api_name]).strip() or None)
    try:
        if "contatos" in payload:
            item.contacts = _validate_collection(payload["contatos"], "Contatos")
        if "enderecos" in payload:
            item.addresses = _validate_collection(payload["enderecos"], "Endereços")
        if "flagsPrivacidade" in payload and not isinstance(payload["flagsPrivacidade"], list):
            raise ValueError("Flags de privacidade deve ser uma lista.")
    except ValueError as error:
        return jsonify(error="validation_error", message=str(error)), 422
    if "consentimentoContato" in payload:
        if item.contact_consent != bool(payload["consentimentoContato"]):
            record_consent(
                tenant_id=tenant_id,
                citizen_id=item.id,
                user_id=user_id,
                purpose="CONTATO",
                granted=bool(payload["consentimentoContato"]),
                legal_basis=item.legal_basis,
                source="CORRECAO",
            )
        item.contact_consent = bool(payload["consentimentoContato"])
    if "consentimentoDivulgacao" in payload:
        if item.publication_consent != bool(payload["consentimentoDivulgacao"]):
            record_consent(
                tenant_id=tenant_id,
                citizen_id=item.id,
                user_id=user_id,
                purpose="DIVULGACAO",
                granted=bool(payload["consentimentoDivulgacao"]),
                legal_basis=item.legal_basis,
                source="CORRECAO",
            )
        item.publication_consent = bool(payload["consentimentoDivulgacao"])
    if "flagsPrivacidade" in payload:
        item.privacy_flags = payload["flagsPrivacidade"]
    after = _citizen_data(item)
    add_audit(tenant_id, user_id, "citizen.corrected", "citizen", item.id, before, after)
    db.session.commit()
    return jsonify(after)


@directory_bp.get("/organizacoes")
@jwt_required()
def list_organizations():
    tenant_id, _ = _context()
    items = db.session.execute(
        select(Organization).where(Organization.tenant_id == tenant_id).order_by(Organization.name)
    ).scalars()
    return jsonify(content=[_organization_data(item) for item in items])


@directory_bp.post("/organizacoes")
@jwt_required()
def create_organization():
    tenant_id, user_id = _context()
    payload = request.get_json(silent=True) or {}
    name = str(payload.get("nome", "")).strip()
    organization_type = str(payload.get("tipo", "")).strip()
    if len(name) < 2 or not organization_type:
        return jsonify(error="validation_error", message="Informe nome e tipo."), 422
    try:
        contacts = _validate_collection(payload.get("contatos"), "Contatos")
        addresses = _validate_collection(payload.get("enderecos"), "Endereços")
    except ValueError as error:
        return jsonify(error="validation_error", message=str(error)), 422
    item = Organization(
        tenant_id=tenant_id,
        name=name,
        organization_type=organization_type,
        contacts=contacts,
        addresses=addresses,
        territory=str(payload.get("territorio", "")).strip() or None,
        notes=str(payload.get("observacoes", "")).strip() or None,
    )
    db.session.add(item)
    db.session.flush()
    add_audit(
        tenant_id,
        user_id,
        "organization.created",
        "organization",
        item.id,
        after={"nome": item.name, "tipo": item.organization_type},
    )
    db.session.commit()
    return jsonify(_organization_data(item)), 201


@directory_bp.get("/organizacoes/<uuid:organization_id>")
@jwt_required()
def get_organization(organization_id: uuid.UUID):
    tenant_id, _ = _context()
    item = db.session.execute(
        select(Organization).where(
            Organization.id == organization_id,
            Organization.tenant_id == tenant_id,
        )
    ).scalar_one_or_none()
    if item is None:
        return jsonify(error="resource_not_found", message="Organização não encontrada."), 404
    return jsonify(_organization_data(item))


@directory_bp.patch("/organizacoes/<uuid:organization_id>")
@jwt_required()
def update_organization(organization_id: uuid.UUID):
    tenant_id, user_id = _context()
    item = db.session.execute(
        select(Organization).where(
            Organization.id == organization_id,
            Organization.tenant_id == tenant_id,
        )
    ).scalar_one_or_none()
    if item is None:
        return jsonify(error="resource_not_found", message="Organização não encontrada."), 404
    payload = request.get_json(silent=True) or {}
    before = _organization_data(item)
    mappings = {
        "nome": "name",
        "tipo": "organization_type",
        "territorio": "territory",
        "observacoes": "notes",
    }
    for api_name, attribute in mappings.items():
        if api_name in payload:
            setattr(item, attribute, str(payload[api_name]).strip() or None)
    try:
        if "contatos" in payload:
            item.contacts = _validate_collection(payload["contatos"], "Contatos")
        if "enderecos" in payload:
            item.addresses = _validate_collection(payload["enderecos"], "Endereços")
    except ValueError as error:
        return jsonify(error="validation_error", message=str(error)), 422
    after = _organization_data(item)
    add_audit(
        tenant_id,
        user_id,
        "organization.updated",
        "organization",
        item.id,
        before,
        after,
    )
    db.session.commit()
    return jsonify(after)


@directory_bp.post("/cidadaos/<uuid:citizen_id>/anonimizar")
@roles_required("admin", "manager")
def anonymize_citizen(citizen_id: uuid.UUID):
    tenant_id, user_id = _context()
    item = db.session.execute(
        select(Citizen).where(Citizen.id == citizen_id, Citizen.tenant_id == tenant_id)
    ).scalar_one_or_none()
    if item is None:
        return jsonify(error="resource_not_found", message="Cidadão não encontrado."), 404
    before = {"nome": item.name, "contatos": item.contacts, "enderecos": item.addresses}
    item.name = f"Cidadão anonimizado {str(item.id)[:8]}"
    item.social_name = None
    item.contacts = []
    item.addresses = []
    item.preferred_channel = None
    item.notes = None
    item.privacy_flags = ["ANONIMIZADO"]
    item.anonymized_at = datetime.now(UTC)
    add_audit(
        tenant_id,
        user_id,
        "citizen.anonymized",
        "citizen",
        item.id,
        before,
        {"anonimizadoEm": item.anonymized_at.isoformat()},
    )
    db.session.commit()
    return jsonify(_citizen_data(item))
