import json
import uuid
from datetime import UTC, datetime, timedelta

from flask import Blueprint, jsonify, make_response, request
from flask_jwt_extended import get_jwt, get_jwt_identity
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.audit import add_audit
from app.auth.permissions import roles_required
from app.extensions import db
from app.models import (
    AuditLog,
    Citizen,
    PrivacyRequest,
    PrivacyRequestStatus,
    PrivacyRequestType,
    RetentionAction,
    RetentionPolicy,
    User,
    UserStatus,
)
from app.privacy.service import (
    citizen_export,
    consent_data,
    privacy_request_data,
    record_consent,
    retention_policy_data,
)

privacy_bp = Blueprint("privacy", __name__)


def _context() -> tuple[uuid.UUID, uuid.UUID]:
    return uuid.UUID(get_jwt()["tenant_id"]), uuid.UUID(get_jwt_identity())


def _citizen(citizen_id: uuid.UUID, tenant_id: uuid.UUID) -> Citizen | None:
    return db.session.execute(
        select(Citizen).where(Citizen.id == citizen_id, Citizen.tenant_id == tenant_id)
    ).scalar_one_or_none()


@privacy_bp.get("/privacidade/resumo")
@roles_required("admin", "manager")
def privacy_summary():
    tenant_id, _ = _context()
    now = datetime.now(UTC)
    open_requests = db.session.execute(
        select(PrivacyRequest).where(
            PrivacyRequest.tenant_id == tenant_id,
            PrivacyRequest.status.in_(
                [PrivacyRequestStatus.ABERTA, PrivacyRequestStatus.EM_ANALISE]
            ),
        )
    ).scalars()
    items = list(open_requests)
    return jsonify(
        solicitacoesAbertas=len(items),
        solicitacoesVencidas=sum(
            (item.due_at if item.due_at.tzinfo else item.due_at.replace(tzinfo=UTC)) < now
            for item in items
        ),
        cidadaosAtivos=db.session.execute(
            select(func.count(Citizen.id)).where(
                Citizen.tenant_id == tenant_id, Citizen.anonymized_at.is_(None)
            )
        ).scalar_one(),
        politicasAtivas=db.session.execute(
            select(func.count(RetentionPolicy.id)).where(
                RetentionPolicy.tenant_id == tenant_id, RetentionPolicy.active.is_(True)
            )
        ).scalar_one(),
    )


@privacy_bp.get("/privacidade/solicitacoes")
@roles_required("admin", "manager")
def list_privacy_requests():
    tenant_id, _ = _context()
    items = db.session.execute(
        select(PrivacyRequest)
        .where(PrivacyRequest.tenant_id == tenant_id)
        .order_by(PrivacyRequest.created_at.desc())
    ).scalars()
    return jsonify(content=[privacy_request_data(item) for item in items])


@privacy_bp.post("/privacidade/solicitacoes")
@roles_required("admin", "manager")
def create_privacy_request():
    tenant_id, user_id = _context()
    payload = request.get_json(silent=True) or {}
    try:
        citizen_id = uuid.UUID(str(payload.get("cidadaoId", "")))
        request_type = PrivacyRequestType(str(payload.get("tipo", "")).upper())
        due_days = int(payload.get("prazoDias", 15))
    except (TypeError, ValueError):
        return jsonify(error="validation_error", message="Dados da solicitação inválidos."), 422
    citizen = _citizen(citizen_id, tenant_id)
    details = str(payload.get("detalhes", "")).strip()
    if citizen is None:
        return jsonify(error="resource_not_found", message="Cidadão não encontrado."), 404
    if not details or not 1 <= due_days <= 365:
        return jsonify(error="validation_error", message="Informe detalhes e prazo válido."), 422
    item = PrivacyRequest(
        tenant_id=tenant_id,
        citizen_id=citizen.id,
        request_type=request_type,
        identity_validated=payload.get("identidadeValidada") is True,
        details=details,
        due_at=datetime.now(UTC) + timedelta(days=due_days),
        created_by_id=user_id,
        assigned_to_id=user_id,
    )
    db.session.add(item)
    db.session.flush()
    add_audit(
        tenant_id,
        user_id,
        "privacy_request.created",
        "privacy_request",
        item.id,
        after=privacy_request_data(item),
    )
    db.session.commit()
    return jsonify(privacy_request_data(item)), 201


@privacy_bp.patch("/privacidade/solicitacoes/<uuid:item_id>")
@roles_required("admin", "manager")
def update_privacy_request(item_id: uuid.UUID):
    tenant_id, user_id = _context()
    item = db.session.execute(
        select(PrivacyRequest).where(
            PrivacyRequest.id == item_id, PrivacyRequest.tenant_id == tenant_id
        )
    ).scalar_one_or_none()
    if item is None:
        return jsonify(error="resource_not_found", message="Solicitação não encontrada."), 404
    payload = request.get_json(silent=True) or {}
    before = privacy_request_data(item)
    if "identidadeValidada" in payload:
        item.identity_validated = payload["identidadeValidada"] is True
    if "responsavelId" in payload:
        try:
            assignee_id = uuid.UUID(str(payload["responsavelId"]))
        except ValueError:
            return jsonify(error="validation_error", message="Responsável inválido."), 422
        assignee = db.session.execute(
            select(User).where(
                User.id == assignee_id,
                User.tenant_id == tenant_id,
                User.status == UserStatus.ACTIVE,
            )
        ).scalar_one_or_none()
        if assignee is None:
            return jsonify(error="validation_error", message="Responsável inválido."), 422
        item.assigned_to = assignee
    if "status" in payload:
        try:
            status = PrivacyRequestStatus(str(payload["status"]).upper())
        except ValueError:
            return jsonify(error="validation_error", message="Status inválido."), 422
        if status in [PrivacyRequestStatus.CONCLUIDA, PrivacyRequestStatus.REJEITADA]:
            resolution = str(payload.get("resolucao", "")).strip()
            if not resolution:
                return jsonify(error="validation_error", message="Informe a resolução."), 422
            if status == PrivacyRequestStatus.CONCLUIDA and not item.identity_validated:
                return (
                    jsonify(
                        error="validation_error",
                        message="Valide a identidade antes de concluir.",
                    ),
                    422,
                )
            item.resolution = resolution
            item.completed_at = datetime.now(UTC)
        item.status = status
    db.session.flush()
    after = privacy_request_data(item)
    add_audit(
        tenant_id,
        user_id,
        "privacy_request.updated",
        "privacy_request",
        item.id,
        before=before,
        after=after,
    )
    db.session.commit()
    return jsonify(after)


@privacy_bp.post("/privacidade/solicitacoes/<uuid:item_id>/exportar")
@roles_required("admin", "manager")
def export_privacy_request(item_id: uuid.UUID):
    tenant_id, user_id = _context()
    item = db.session.execute(
        select(PrivacyRequest).where(
            PrivacyRequest.id == item_id, PrivacyRequest.tenant_id == tenant_id
        )
    ).scalar_one_or_none()
    if item is None:
        return jsonify(error="resource_not_found", message="Solicitação não encontrada."), 404
    if item.request_type != PrivacyRequestType.ACESSO or not item.identity_validated:
        return (
            jsonify(
                error="validation_error",
                message="A exportação exige solicitação de acesso e identidade validada.",
            ),
            422,
        )
    package = citizen_export(item.citizen)
    add_audit(
        tenant_id,
        user_id,
        "privacy_request.exported",
        "privacy_request",
        item.id,
        after={"cidadaoId": str(item.citizen_id)},
    )
    db.session.commit()
    response = make_response(json.dumps(package, ensure_ascii=False, indent=2))
    response.headers["Content-Type"] = "application/json; charset=utf-8"
    response.headers["Content-Disposition"] = (
        f'attachment; filename="dados-titular-{item.citizen_id}.json"'
    )
    return response


@privacy_bp.get("/cidadaos/<uuid:citizen_id>/consentimentos")
@roles_required("admin", "manager")
def list_consents(citizen_id: uuid.UUID):
    tenant_id, _ = _context()
    citizen = _citizen(citizen_id, tenant_id)
    if citizen is None:
        return jsonify(error="resource_not_found", message="Cidadão não encontrado."), 404
    return jsonify(content=[consent_data(item) for item in citizen.consent_records])


@privacy_bp.post("/cidadaos/<uuid:citizen_id>/consentimentos")
@roles_required("admin", "manager")
def create_consent(citizen_id: uuid.UUID):
    tenant_id, user_id = _context()
    citizen = _citizen(citizen_id, tenant_id)
    if citizen is None:
        return jsonify(error="resource_not_found", message="Cidadão não encontrado."), 404
    payload = request.get_json(silent=True) or {}
    purpose = str(payload.get("finalidade", "")).upper()
    granted = payload.get("concedido")
    if purpose not in {"CONTATO", "DIVULGACAO"} or not isinstance(granted, bool):
        return jsonify(error="validation_error", message="Consentimento inválido."), 422
    item = record_consent(
        tenant_id=tenant_id,
        citizen_id=citizen.id,
        user_id=user_id,
        purpose=purpose,
        granted=granted,
        legal_basis=str(payload.get("baseLegal") or citizen.legal_basis),
        source=str(payload.get("origem", "ATENDIMENTO")).upper(),
        evidence=str(payload.get("evidencia", "")).strip() or None,
    )
    if purpose == "CONTATO":
        citizen.contact_consent = granted
    else:
        citizen.publication_consent = granted
    db.session.flush()
    add_audit(
        tenant_id,
        user_id,
        "citizen.consent.recorded",
        "citizen",
        citizen.id,
        after=consent_data(item),
    )
    db.session.commit()
    return jsonify(consent_data(item)), 201


@privacy_bp.get("/privacidade/retencao")
@roles_required("admin", "manager")
def list_retention_policies():
    tenant_id, _ = _context()
    items = db.session.execute(
        select(RetentionPolicy)
        .where(RetentionPolicy.tenant_id == tenant_id)
        .order_by(RetentionPolicy.data_type)
    ).scalars()
    return jsonify(content=[retention_policy_data(item) for item in items])


@privacy_bp.put("/privacidade/retencao")
@roles_required("admin", "manager")
def save_retention_policy():
    tenant_id, user_id = _context()
    payload = request.get_json(silent=True) or {}
    data_type = str(payload.get("tipoDado", "")).upper()
    try:
        days = int(payload.get("retencaoDias"))
        action = RetentionAction(str(payload.get("acao", "")).upper())
    except (TypeError, ValueError):
        return jsonify(error="validation_error", message="Política inválida."), 422
    if data_type not in {"CIDADAO", "ANEXO", "AUDITORIA"} or not 30 <= days <= 36500:
        return jsonify(error="validation_error", message="Política inválida."), 422
    item = db.session.execute(
        select(RetentionPolicy).where(
            RetentionPolicy.tenant_id == tenant_id,
            RetentionPolicy.data_type == data_type,
        )
    ).scalar_one_or_none()
    before = retention_policy_data(item) if item else None
    if item is None:
        item = RetentionPolicy(
            tenant_id=tenant_id, data_type=data_type, updated_by_id=user_id
        )
        db.session.add(item)
    item.retention_days = days
    item.action = action
    item.active = payload.get("ativa", True) is not False
    item.updated_by_id = user_id
    try:
        db.session.flush()
    except IntegrityError:
        db.session.rollback()
        return jsonify(error="conflict", message="Política já cadastrada."), 409
    after = retention_policy_data(item)
    add_audit(
        tenant_id,
        user_id,
        "retention_policy.saved",
        "retention_policy",
        item.id,
        before=before,
        after=after,
    )
    db.session.commit()
    return jsonify(after)


@privacy_bp.get("/auditoria")
@roles_required("admin", "manager")
def list_audit():
    tenant_id, _ = _context()
    page = max(request.args.get("page", 0, type=int), 0)
    size = min(max(request.args.get("size", 50, type=int), 1), 100)
    filters = [AuditLog.tenant_id == tenant_id]
    action = str(request.args.get("acao", "")).strip()
    entity_type = str(request.args.get("entidade", "")).strip()
    if action:
        filters.append(AuditLog.action.ilike(f"%{action}%"))
    if entity_type:
        filters.append(AuditLog.entity_type == entity_type)
    total = db.session.execute(select(func.count(AuditLog.id)).where(*filters)).scalar_one()
    items = db.session.execute(
        select(AuditLog)
        .where(*filters)
        .order_by(AuditLog.created_at.desc())
        .offset(page * size)
        .limit(size)
    ).scalars()
    users = {
        user.id: user.name
        for user in db.session.execute(select(User).where(User.tenant_id == tenant_id)).scalars()
    }
    return jsonify(
        content=[
            {
                "id": str(item.id),
                "usuario": users.get(item.user_id, "Sistema"),
                "acao": item.action,
                "entidade": item.entity_type,
                "entidadeId": item.entity_id,
                "antes": item.before,
                "depois": item.after,
                "ip": item.ip_address,
                "criadaEm": item.created_at.isoformat(),
            }
            for item in items
        ],
        totalElements=total,
        page=page,
        size=size,
    )
