import uuid

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity
from sqlalchemy import func, select

from app.audit import add_audit
from app.auth.permissions import platform_admin_required
from app.extensions import db
from app.models import (
    AgendaEvent,
    Attachment,
    AuditLog,
    ChannelMessage,
    ContractStatus,
    IntegrationSetting,
    IntegrationStatus,
    LegislativeDraft,
    OversightAction,
    PlatformContractEvent,
    PlatformSetting,
    PlatformSettingType,
    PlatformSupportAccess,
    RagDocument,
    Role,
    ServiceRequest,
    Tenant,
    TenantStatus,
    User,
    UserStatus,
)
from app.modules import AVAILABLE_MODULES, DEFAULT_MODULES, normalize_modules, validate_modules

platform_bp = Blueprint("platform", __name__)

PLANS = {"starter", "professional", "premium", "enterprise"}


def _actor_id() -> uuid.UUID:
    return uuid.UUID(get_jwt_identity())


def _tenant_data(item: Tenant) -> dict:
    return {
        "id": str(item.id),
        "nome": item.name,
        "slug": item.slug,
        "status": item.status.value,
        "plano": item.plan,
        "contrato": item.contract_status.value,
        "limiteUsuarios": item.user_limit,
        "limiteArmazenamentoMb": item.storage_limit_mb,
        "modulosHabilitados": normalize_modules(item.enabled_modules),
        "observacoesContrato": item.contract_notes,
        "usuarios": len(item.users),
        "criadoEm": item.created_at.isoformat(),
    }


def _setting_data(item: PlatformSetting) -> dict:
    return {
        "id": str(item.id),
        "tipo": item.setting_type.value,
        "chave": item.key,
        "nome": item.name,
        "valor": item.value,
        "ativo": item.active,
        "atualizadoEm": item.updated_at.isoformat(),
    }


def _support_data(item: PlatformSupportAccess) -> dict:
    return {
        "id": str(item.id),
        "tenantId": str(item.tenant_id),
        "gabinete": item.tenant.name if getattr(item, "tenant", None) else None,
        "solicitadoPor": item.requested_by,
        "autorizadoPor": item.authorized_by,
        "motivo": item.reason,
        "escopo": item.scope,
        "status": item.status,
        "criadoEm": item.created_at.isoformat(),
    }


def _contract_event_data(item: PlatformContractEvent) -> dict:
    return {
        "id": str(item.id),
        "tenantId": str(item.tenant_id),
        "statusAnterior": item.previous_status.value if item.previous_status else None,
        "novoStatus": item.new_status.value,
        "motivo": item.reason,
        "efetivoEm": item.effective_at.isoformat() if item.effective_at else None,
        "criadoEm": item.created_at.isoformat(),
        "usuarioId": str(item.created_by_id) if item.created_by_id else None,
    }


@platform_bp.get("/overview")
@platform_admin_required
def overview():
    tenant_statuses = dict(
        db.session.execute(
            select(Tenant.status, func.count(Tenant.id)).group_by(Tenant.status)
        ).all()
    )
    tenant_users = select(func.count(User.id)).where(User.tenant_id.is_not(None))
    totals = {
        "gabinetes": db.session.scalar(select(func.count(Tenant.id))) or 0,
        "usuarios": db.session.scalar(tenant_users) or 0,
        "solicitacoes": db.session.scalar(select(func.count(ServiceRequest.id))) or 0,
        "documentosRag": db.session.scalar(select(func.count(RagDocument.id))) or 0,
        "anexos": db.session.scalar(select(func.count(Attachment.id))) or 0,
        "mensagensCanal": db.session.scalar(select(func.count(ChannelMessage.id))) or 0,
    }
    statuses = {status.value: tenant_statuses.get(status, 0) for status in TenantStatus}
    return jsonify(
        totais=totals,
        gabinetesPorStatus=statuses,
        planos=_count_by(Tenant.plan),
        modulosDisponiveis=sorted(AVAILABLE_MODULES),
        provedores=_platform_settings_summary(PlatformSettingType.INTEGRATION_PROVIDER),
        alertas=_platform_alerts(),
    )


@platform_bp.get("/gabinetes")
@platform_admin_required
def list_tenants():
    query = str(request.args.get("q", "")).strip().lower()
    statement = select(Tenant).order_by(Tenant.created_at.desc())
    if query:
        statement = statement.where(
            Tenant.name.ilike(f"%{query}%") | Tenant.slug.ilike(f"%{query}%")
        )
    items = db.session.execute(statement).scalars().all()
    return jsonify(content=[_tenant_data(item) for item in items])


@platform_bp.post("/gabinetes")
@platform_admin_required
def create_tenant():
    payload = request.get_json(silent=True) or {}
    name = str(payload.get("nome", "")).strip()
    slug = str(payload.get("slug", "")).strip().lower()
    if not name or not slug:
        return jsonify(error="validation_error", message="Informe nome e slug do gabinete."), 422
    if db.session.execute(select(Tenant.id).where(Tenant.slug == slug)).scalar_one_or_none():
        return jsonify(error="conflict", message="Slug de gabinete ja cadastrado."), 409
    try:
        tenant = Tenant(
            name=name,
            slug=slug,
            status=TenantStatus.ACTIVE,
            contract_status=ContractStatus.TRIAL,
            plan=_plan(payload.get("plano", "starter")),
            user_limit=_positive_int(payload.get("limiteUsuarios", 5), "Limite de usuarios"),
            storage_limit_mb=_positive_int(
                payload.get("limiteArmazenamentoMb", 1024), "Limite de armazenamento"
            ),
            enabled_modules=_modules(payload.get("modulosHabilitados", DEFAULT_MODULES)),
            contract_notes=str(payload.get("observacoesContrato", "")).strip() or None,
        )
    except ValueError as error:
        return jsonify(error="validation_error", message=str(error)), 422
    db.session.add(tenant)
    db.session.flush()
    add_audit(
        None,
        _actor_id(),
        "platform.tenant.created",
        "tenant",
        tenant.id,
        None,
        _tenant_data(tenant),
    )
    db.session.commit()
    return jsonify(_tenant_data(tenant)), 201


@platform_bp.patch("/gabinetes/<uuid:tenant_id>")
@platform_admin_required
def update_tenant(tenant_id: uuid.UUID):
    tenant = db.session.get(Tenant, tenant_id)
    if tenant is None:
        return jsonify(error="resource_not_found", message="Gabinete nao encontrado."), 404
    payload = request.get_json(silent=True) or {}
    before = _tenant_data(tenant)
    contract_transition = None
    try:
        if "nome" in payload:
            tenant.name = str(payload["nome"]).strip() or tenant.name
        if "status" in payload:
            tenant.status = TenantStatus(str(payload["status"]).lower())
        if "contrato" in payload:
            contract_transition = ContractStatus(str(payload["contrato"]).lower())
        if "plano" in payload:
            tenant.plan = _plan(payload["plano"])
        if "limiteUsuarios" in payload:
            tenant.user_limit = _positive_int(payload["limiteUsuarios"], "Limite de usuarios")
        if "limiteArmazenamentoMb" in payload:
            tenant.storage_limit_mb = _positive_int(
                payload["limiteArmazenamentoMb"], "Limite de armazenamento"
            )
        if "modulosHabilitados" in payload:
            tenant.enabled_modules = _modules(payload["modulosHabilitados"])
    except ValueError as error:
        return jsonify(error="validation_error", message=str(error)), 422
    if "observacoesContrato" in payload:
        tenant.contract_notes = str(payload["observacoesContrato"]).strip() or None
    if contract_transition is not None:
        reason = str(payload.get("motivoContrato", "")).strip()
        if not reason:
            return (
                jsonify(
                    error="validation_error",
                    message="Informe o motivo da transicao contratual.",
                ),
                422,
            )
        _apply_contract_transition(tenant, contract_transition, reason)
    db.session.flush()
    after = _tenant_data(tenant)
    add_audit(None, _actor_id(), "platform.tenant.updated", "tenant", tenant.id, before, after)
    db.session.commit()
    return jsonify(after)


@platform_bp.get("/gabinetes/<uuid:tenant_id>/contrato")
@platform_admin_required
def contract_history(tenant_id: uuid.UUID):
    if db.session.get(Tenant, tenant_id) is None:
        return jsonify(error="resource_not_found", message="Gabinete nao encontrado."), 404
    items = db.session.execute(
        select(PlatformContractEvent)
        .where(PlatformContractEvent.tenant_id == tenant_id)
        .order_by(PlatformContractEvent.created_at.desc())
    ).scalars()
    return jsonify(content=[_contract_event_data(item) for item in items])


@platform_bp.post("/gabinetes/<uuid:tenant_id>/contrato")
@platform_admin_required
def transition_contract(tenant_id: uuid.UUID):
    tenant = db.session.get(Tenant, tenant_id)
    if tenant is None:
        return jsonify(error="resource_not_found", message="Gabinete nao encontrado."), 404
    payload = request.get_json(silent=True) or {}
    reason = str(payload.get("motivo", "")).strip()
    if not reason:
        return jsonify(error="validation_error", message="Informe o motivo da transicao."), 422
    try:
        new_status = ContractStatus(str(payload.get("contrato", "")).lower())
    except ValueError:
        return jsonify(error="validation_error", message="Status contratual invalido."), 422
    before = _tenant_data(tenant)
    event = _apply_contract_transition(tenant, new_status, reason)
    if "observacoesContrato" in payload:
        tenant.contract_notes = str(payload["observacoesContrato"]).strip() or None
    db.session.flush()
    after = _tenant_data(tenant)
    add_audit(
        None,
        _actor_id(),
        "platform.contract.transitioned",
        "tenant",
        tenant.id,
        before,
        {"tenant": after, "evento": _contract_event_data(event)},
    )
    db.session.commit()
    return jsonify(tenant=after, evento=_contract_event_data(event))


@platform_bp.get("/gabinetes/<uuid:tenant_id>/consumo")
@platform_admin_required
def tenant_usage(tenant_id: uuid.UUID):
    tenant = db.session.get(Tenant, tenant_id)
    if tenant is None:
        return jsonify(error="resource_not_found", message="Gabinete nao encontrado."), 404
    return jsonify(
        tenant=_tenant_data(tenant),
        consumo={
            "usuarios": _tenant_count(User, tenant_id),
            "solicitacoes": _tenant_count(ServiceRequest, tenant_id),
            "documentosRag": _tenant_count(RagDocument, tenant_id),
            "minutasLegislativas": _tenant_count(LegislativeDraft, tenant_id),
            "agenda": _tenant_count(AgendaEvent, tenant_id),
            "fiscalizacoes": _tenant_count(OversightAction, tenant_id),
            "mensagensCanal": _tenant_count(ChannelMessage, tenant_id),
            "integracoes": _tenant_count(IntegrationSetting, tenant_id),
        },
    )


@platform_bp.post("/gabinetes/<uuid:tenant_id>/reset-admin")
@platform_admin_required
def reset_tenant_admin(tenant_id: uuid.UUID):
    tenant = db.session.get(Tenant, tenant_id)
    if tenant is None:
        return jsonify(error="resource_not_found", message="Gabinete nao encontrado."), 404
    payload = request.get_json(silent=True) or {}
    email = str(payload.get("email", "")).strip().lower()
    if not email:
        return jsonify(error="validation_error", message="Informe o e-mail do administrador."), 422
    user = db.session.execute(
        select(User).where(User.tenant_id == tenant_id, User.email == email)
    ).scalar_one_or_none()
    if user is None:
        return (
            jsonify(error="resource_not_found", message="Usuario nao encontrado no gabinete."),
            404,
        )
    before = {"role": user.role.value, "status": user.status.value}
    user.role = Role.ADMIN
    user.status = UserStatus.ACTIVE
    after = {"role": user.role.value, "status": user.status.value}
    add_audit(None, _actor_id(), "platform.tenant_admin.reset", "user", user.id, before, after)
    db.session.commit()
    return jsonify(message="Administrador do gabinete redefinido.", usuarioId=str(user.id))


@platform_bp.get("/configuracoes")
@platform_admin_required
def list_settings():
    setting_type = request.args.get("tipo")
    statement = select(PlatformSetting).order_by(PlatformSetting.setting_type, PlatformSetting.key)
    if setting_type:
        statement = statement.where(
            PlatformSetting.setting_type == PlatformSettingType(setting_type)
        )
    items = db.session.execute(statement).scalars().all()
    return jsonify(content=[_setting_data(item) for item in items])


@platform_bp.post("/configuracoes")
@platform_admin_required
def upsert_setting():
    payload = request.get_json(silent=True) or {}
    try:
        setting_type = PlatformSettingType(str(payload.get("tipo", "PARAMETER")).upper())
    except ValueError:
        return jsonify(error="validation_error", message="Tipo de configuracao invalido."), 422
    key = str(payload.get("chave", "")).strip()
    name = str(payload.get("nome", "")).strip() or key
    value = payload.get("valor") or {}
    if not key or not isinstance(value, dict):
        return jsonify(error="validation_error", message="Informe chave e valor estruturado."), 422
    item = db.session.execute(
        select(PlatformSetting).where(
            PlatformSetting.setting_type == setting_type,
            PlatformSetting.key == key,
        )
    ).scalar_one_or_none()
    before = _setting_data(item) if item else None
    if item is None:
        item = PlatformSetting(setting_type=setting_type, key=key, name=name)
        db.session.add(item)
    item.name = name
    item.value = _sanitize_setting_value(value)
    item.active = bool(payload.get("ativo", True))
    item.updated_by_id = _actor_id()
    db.session.flush()
    after = _setting_data(item)
    add_audit(
        None,
        _actor_id(),
        "platform.setting.upserted",
        "platform_setting",
        item.id,
        before,
        after,
    )
    db.session.commit()
    return jsonify(after), 201 if before is None else 200


@platform_bp.get("/suporte")
@platform_admin_required
def list_support_accesses():
    items = db.session.execute(
        select(PlatformSupportAccess).order_by(PlatformSupportAccess.created_at.desc()).limit(100)
    ).scalars()
    return jsonify(content=[_support_data(item) for item in items])


@platform_bp.post("/suporte")
@platform_admin_required
def register_support_access():
    payload = request.get_json(silent=True) or {}
    try:
        tenant_id = uuid.UUID(str(payload.get("tenantId", "")))
    except ValueError:
        return jsonify(error="validation_error", message="Informe um gabinete valido."), 422
    if db.session.get(Tenant, tenant_id) is None:
        return jsonify(error="resource_not_found", message="Gabinete nao encontrado."), 404
    reason = str(payload.get("motivo", "")).strip()
    requested_by = str(payload.get("solicitadoPor", "")).strip()
    scope = str(payload.get("escopo", "")).strip()
    if not reason or not requested_by or not scope:
        return (
            jsonify(error="validation_error", message="Informe solicitante, motivo e escopo."),
            422,
        )
    item = PlatformSupportAccess(
        tenant_id=tenant_id,
        requested_by=requested_by,
        authorized_by=str(payload.get("autorizadoPor", "")).strip() or None,
        reason=reason,
        scope=scope,
        created_by_id=_actor_id(),
    )
    db.session.add(item)
    db.session.flush()
    add_audit(
        None,
        _actor_id(),
        "platform.support_access.registered",
        "platform_support_access",
        item.id,
        None,
        _support_data(item),
    )
    db.session.commit()
    return jsonify(_support_data(item)), 201


@platform_bp.get("/auditoria")
@platform_admin_required
def platform_audit():
    items = db.session.execute(
        select(AuditLog)
        .where(AuditLog.tenant_id.is_(None))
        .order_by(AuditLog.created_at.desc())
        .limit(100)
    ).scalars()
    return jsonify(
        content=[
            {
                "id": str(item.id),
                "acao": item.action,
                "entidade": item.entity_type,
                "entidadeId": item.entity_id,
                "usuarioId": str(item.user_id) if item.user_id else None,
                "criadoEm": item.created_at.isoformat(),
            }
            for item in items
        ]
    )


def _tenant_count(model, tenant_id: uuid.UUID) -> int:
    return db.session.scalar(select(func.count(model.id)).where(model.tenant_id == tenant_id)) or 0


def _count_by(column) -> dict:
    rows = db.session.execute(select(column, func.count()).group_by(column))
    return {str(key): value for key, value in rows}


def _platform_settings_summary(setting_type: PlatformSettingType) -> list[dict]:
    items = db.session.execute(
        select(PlatformSetting).where(PlatformSetting.setting_type == setting_type)
    ).scalars()
    return [{"chave": item.key, "nome": item.name, "ativo": item.active} for item in items]


def _platform_alerts() -> list[dict]:
    suspended = db.session.scalar(
        select(func.count(Tenant.id)).where(Tenant.contract_status == ContractStatus.SUSPENDED)
    )
    failed_integrations = db.session.scalar(
        select(func.count(IntegrationSetting.id)).where(
            IntegrationSetting.status == IntegrationStatus.INATIVA
        )
    )
    alerts = []
    if suspended:
        alerts.append({"tipo": "contratos", "mensagem": f"{suspended} contrato(s) suspenso(s)."})
    if failed_integrations:
        alerts.append(
            {
                "tipo": "integracoes",
                "mensagem": f"{failed_integrations} integracao(oes) inativa(s).",
            }
        )
    return alerts


def _plan(value) -> str:
    plan = str(value or "starter").strip().lower()
    if plan not in PLANS:
        raise ValueError("Plano contratado invalido.")
    return plan


def _positive_int(value, label: str) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{label} invalido.") from error
    if parsed < 1:
        raise ValueError(f"{label} deve ser positivo.")
    return parsed


def _modules(value) -> list[str]:
    return validate_modules(value)


def _apply_contract_transition(
    tenant: Tenant, new_status: ContractStatus, reason: str
) -> PlatformContractEvent:
    previous = tenant.contract_status
    tenant.contract_status = new_status
    if new_status in {ContractStatus.TRIAL, ContractStatus.ACTIVE}:
        tenant.status = TenantStatus.ACTIVE
    elif new_status == ContractStatus.SUSPENDED:
        tenant.status = TenantStatus.SUSPENDED
    elif new_status == ContractStatus.CANCELLED:
        tenant.status = TenantStatus.CANCELLED
    event = PlatformContractEvent(
        tenant_id=tenant.id,
        previous_status=previous,
        new_status=new_status,
        reason=reason,
        created_by_id=_actor_id(),
    )
    db.session.add(event)
    return event


def _sanitize_setting_value(value: dict) -> dict:
    secret_keys = {"token", "secret", "senha", "password", "apiKey", "api_key", "clientSecret"}
    return {str(key): item for key, item in value.items() if key not in secret_keys}
