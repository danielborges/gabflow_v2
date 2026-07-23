import re
import uuid
from datetime import date, datetime, time

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity
from sqlalchemy import func, select

from app.agency_suggestions import reload_suggested_agencies
from app.audit import add_audit
from app.auth.permissions import platform_admin_required
from app.auth.security import hash_password
from app.default_categories import ensure_default_request_categories
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
    PublicLead,
    RagDocument,
    Role,
    ServiceRequest,
    Tenant,
    TenantStatus,
    User,
    UserStatus,
)
from app.modules import AVAILABLE_MODULES, DEFAULT_MODULES, normalize_modules, validate_modules
from app.plans import USER_LIMIT_REACHED_MESSAGE, normalize_plan, user_limit_for_plan
from app.territory_suggestions import reload_suggested_territories

platform_bp = Blueprint("platform", __name__)

LEAD_STATUSES = {
    "new",
    "contacting",
    "proposal_sent",
    "contract_negotiation",
    "payment_pending",
    "onboarding_scheduled",
    "converted",
    "lost",
}
LEAD_PAYMENT_STATUSES = {"pending", "invoice_sent", "paid", "overdue", "cancelled"}
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]{2,}$")
BR_PHONE_RE = re.compile(
    r"^\D*([1-9]{2})\D*(?:(9\d{4})\D*(\d{4})|([2-5]\d{3})\D*(\d{4}))\D*$"
)
TENANT_ROLES = {Role.ADMIN, Role.REPRESENTATIVE, Role.STAFF}


def _actor_id() -> uuid.UUID:
    return uuid.UUID(get_jwt_identity())


def _tenant_data(item: Tenant) -> dict:
    representative = item.representative_info or {}
    return {
        "id": str(item.id),
        "nome": item.name,
        "slug": item.slug,
        "status": item.status.value,
        "plano": item.plan,
        "contrato": item.contract_status.value,
        "limiteUsuarios": user_limit_for_plan(item.plan),
        "modulosHabilitados": normalize_modules(item.enabled_modules),
        "observacoesContrato": item.contract_notes,
        "jurisdicao": {
            "nome": item.jurisdiction_name,
            "municipio": item.jurisdiction_city,
            "uf": item.jurisdiction_state,
            "codigoIbge": item.jurisdiction_ibge_code,
            "tipoCasa": item.chamber_type,
        },
        "parlamentar": {
            "nome": (
                representative.get("nomeParlamentar")
                or representative.get("nomeCompleto")
                or representative.get("nomeCivil")
                or ""
            ),
            "partido": representative.get("partido") or "",
            "statusMandato": representative.get("statusMandato") or "",
        },
        "usuarios": len(item.users),
        "usuariosAtivos": _active_tenant_users(item.id),
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


def _tenant_user_data(item: User) -> dict:
    chief_of_staff = bool(item.tenant and item.tenant.chief_of_staff_id == item.id)
    return {
        "id": str(item.id),
        "tenantId": str(item.tenant_id) if item.tenant_id else None,
        "gabinete": item.tenant.name if item.tenant else None,
        "nome": item.name,
        "email": item.email,
        "cpf": _format_cpf(item.cpf),
        "telefone": _format_phone(item.phone),
        "perfil": item.role.value,
        "status": item.status.value,
        "chefeGabinete": chief_of_staff,
        "mfaHabilitado": item.mfa_enabled,
        "ultimoLoginEm": item.last_login_at.isoformat() if item.last_login_at else None,
        "criadoEm": item.created_at.isoformat(),
    }


def _lead_data(item: PublicLead) -> dict:
    return {
        "id": str(item.id),
        "plano": item.plan,
        "tipoInstituicao": item.audience,
        "estado": item.state,
        "municipio": item.city,
        "municipioIbgeId": item.municipality_ibge_id,
        "nomeGabinete": item.organization,
        "administradorGabinete": item.admin_name or item.name,
        "telefone": item.phone,
        "whatsapp": item.whatsapp,
        "email": item.email,
        "formaContato": item.preferred_contact,
        "comoEncontrou": item.discovery_source,
        "observacoes": item.message,
        "status": item.status,
        "pagamento": item.payment_status,
        "dataOnboarding": item.onboarding_date.isoformat() if item.onboarding_date else None,
        "onboarding": item.onboarding_details or {},
        "tentativasContato": item.contact_attempts or [],
        "documentosContrato": item.contract_documents or [],
        "pagamentos": item.payments or [],
        "historicoAcoes": item.action_history or [],
        "tenantConvertidoId": str(item.converted_tenant_id) if item.converted_tenant_id else None,
        "observacoesContrato": item.contract_notes,
        "criadoEm": item.created_at.isoformat() if item.created_at else None,
        "atualizadoEm": item.updated_at.isoformat() if item.updated_at else None,
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
        "interessesContratacao": db.session.scalar(select(func.count(PublicLead.id))) or 0,
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
    plan = str(request.args.get("plano", "")).strip().lower()
    jurisdiction = str(request.args.get("jurisdicao", "")).strip().lower()
    representative = str(request.args.get("parlamentar", "")).strip().lower()
    created_from = _optional_datetime_start(request.args.get("criadoDe"))
    created_to = _optional_datetime_end(request.args.get("criadoAte"))
    statement = select(Tenant).order_by(Tenant.created_at.desc())
    if query:
        statement = statement.where(
            Tenant.name.ilike(f"%{query}%") | Tenant.slug.ilike(f"%{query}%")
        )
    if plan:
        statement = statement.where(Tenant.plan == plan)
    if created_from:
        statement = statement.where(Tenant.created_at >= created_from)
    if created_to:
        statement = statement.where(Tenant.created_at <= created_to)
    items = [
        item
        for item in db.session.execute(statement).scalars().all()
        if _tenant_matches_optional_filters(item, jurisdiction, representative)
    ]
    return jsonify(content=[_tenant_data(item) for item in items])


@platform_bp.get("/interesses-contratacao")
@platform_admin_required
def list_contracting_interests():
    status = str(request.args.get("status", "")).strip().lower()
    statement = select(PublicLead).order_by(PublicLead.created_at.desc())
    if status:
        statement = statement.where(PublicLead.status == status)
    items = db.session.execute(statement.limit(200)).scalars().all()
    return jsonify(content=[_lead_data(item) for item in items])


@platform_bp.patch("/interesses-contratacao/<uuid:lead_id>")
@platform_admin_required
def update_contracting_interest(lead_id: uuid.UUID):
    item = db.session.get(PublicLead, lead_id)
    if item is None:
        return (
            jsonify(
                error="resource_not_found",
                message="Interesse em contratacao nao encontrado.",
            ),
            404,
        )
    payload = request.get_json(silent=True) or {}
    before = _lead_data(item)
    if "status" in payload:
        status = str(payload["status"]).strip().lower()
        if status not in LEAD_STATUSES:
            return jsonify(error="validation_error", message="Status de contratacao invalido."), 422
        item.status = status
    if "pagamento" in payload:
        payment = str(payload["pagamento"]).strip().lower()
        if payment not in LEAD_PAYMENT_STATUSES:
            return jsonify(error="validation_error", message="Status de pagamento invalido."), 422
        item.payment_status = payment
    try:
        if "dataOnboarding" in payload:
            item.onboarding_date = _optional_date(payload["dataOnboarding"])
        if "tentativaContato" in payload:
            attempt = _contact_attempt(payload["tentativaContato"])
            item.contact_attempts = [attempt, *(item.contact_attempts or [])][:50]
            _append_lead_action(item, "contact_attempt", attempt)
        if "documentoContrato" in payload:
            document = _contract_document(payload["documentoContrato"])
            item.contract_documents = [document, *(item.contract_documents or [])][:50]
            _append_lead_action(item, "contract_document.registered", document)
        if "pagamentoItem" in payload:
            payment = _payment_item(payload["pagamentoItem"])
            item.payments = [payment, *(item.payments or [])][:80]
            item.payment_status = payment["status"]
            _append_lead_action(item, "payment.registered", payment)
        if "onboarding" in payload:
            onboarding = _onboarding_details(payload["onboarding"])
            item.onboarding_details = onboarding
            item.onboarding_date = _optional_date(onboarding.get("data"))
            _append_lead_action(item, "onboarding.scheduled", onboarding)
        if payload.get("gerarContrato") is True:
            contract = _generated_contract(item)
            item.contract_documents = [contract, *(item.contract_documents or [])][:50]
            _append_lead_action(item, "contract.generated", contract)
    except ValueError as error:
        return jsonify(error="validation_error", message=str(error)), 422
    if "observacoesContrato" in payload:
        item.contract_notes = str(payload["observacoesContrato"]).strip()[:2000] or None
    db.session.flush()
    after = _lead_data(item)
    add_audit(
        None,
        _actor_id(),
        "platform.contracting_interest.updated",
        "public_lead",
        item.id,
        before,
        after,
    )
    db.session.commit()
    return jsonify(after)


@platform_bp.post("/interesses-contratacao/<uuid:lead_id>/converter")
@platform_admin_required
def convert_contracting_interest(lead_id: uuid.UUID):
    item = db.session.get(PublicLead, lead_id)
    if item is None:
        return (
            jsonify(
                error="resource_not_found",
                message="Interesse em contratacao nao encontrado.",
            ),
            404,
        )
    if item.converted_tenant_id:
        return jsonify(error="conflict", message="Interesse ja convertido em gabinete."), 409
    payload = request.get_json(silent=True) or {}
    slug = str(payload.get("slug", "")).strip().lower() or _slugify(item.organization)
    if db.session.execute(select(Tenant.id).where(Tenant.slug == slug)).scalar_one_or_none():
        return jsonify(error="conflict", message="Slug de gabinete ja cadastrado."), 409
    try:
        tenant = Tenant(
            name=item.organization,
            slug=slug,
            status=TenantStatus.ACTIVE,
            contract_status=ContractStatus.TRIAL,
            plan=normalize_plan(payload.get("plano", item.plan)),
            user_limit=user_limit_for_plan(payload.get("plano", item.plan)),
            storage_limit_mb=0,
            enabled_modules=DEFAULT_MODULES,
            contract_notes=str(
                payload.get("observacoesContrato", item.contract_notes or "")
            ).strip()
            or None,
            chamber_type="CAMARA_MUNICIPAL",
            jurisdiction_name=_jurisdiction_name(item.city, item.state),
            jurisdiction_city=item.city,
            jurisdiction_state=item.state,
            jurisdiction_ibge_code=str(item.municipality_ibge_id)
            if item.municipality_ibge_id
            else None,
        )
    except ValueError as error:
        return jsonify(error="validation_error", message=str(error)), 422
    before = _lead_data(item)
    db.session.add(tenant)
    db.session.flush()
    ensure_default_request_categories(tenant.id)
    reload_suggested_territories(tenant)
    reload_suggested_agencies(tenant)
    item.converted_tenant_id = tenant.id
    item.status = "converted"
    _append_lead_action(
        item,
        "tenant.converted",
        {"tenantId": str(tenant.id), "slug": tenant.slug},
    )
    after = _lead_data(item)
    add_audit(
        None,
        _actor_id(),
        "platform.contracting_interest.converted",
        "public_lead",
        item.id,
        before,
        {"lead": after, "tenant": _tenant_data(tenant)},
    )
    db.session.commit()
    return jsonify(interesse=after, tenant=_tenant_data(tenant)), 201


@platform_bp.post("/gabinetes")
@platform_admin_required
def create_tenant():
    return (
        jsonify(
            error="tenant_creation_locked",
            message="Gabinetes devem ser criados a partir de Interesses em Contratacao.",
        ),
        405,
    )


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
            visual_identity = dict(tenant.visual_identity or {})
            institutional = dict(visual_identity.get("dadosInstitucionais") or {})
            institutional["nomeGabinete"] = tenant.name
            visual_identity["dadosInstitucionais"] = institutional
            tenant.visual_identity = visual_identity
        if "status" in payload:
            tenant.status = TenantStatus(str(payload["status"]).lower())
        if "contrato" in payload:
            contract_transition = ContractStatus(str(payload["contrato"]).lower())
        if "plano" in payload:
            plan = normalize_plan(payload["plano"])
            plan_limit = user_limit_for_plan(plan)
            active_users = _active_tenant_users(tenant.id)
            if active_users > plan_limit:
                return (
                    jsonify(
                        error="plan_user_limit_conflict",
                        message=(
                            "O plano selecionado permite menos usuarios ativos "
                            "do que o gabinete possui hoje."
                        ),
                        usuariosAtivos=active_users,
                        limiteUsuarios=plan_limit,
                    ),
                    422,
                )
            tenant.plan = plan
            tenant.user_limit = plan_limit
        if "modulosHabilitados" in payload:
            tenant.enabled_modules = _modules(payload["modulosHabilitados"])
        if "observacoesContrato" in payload:
            tenant.contract_notes = str(payload["observacoesContrato"]).strip()[:2000] or None
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


@platform_bp.get("/gabinetes/<uuid:tenant_id>/usuarios")
@platform_admin_required
def list_tenant_users(tenant_id: uuid.UUID):
    tenant = db.session.get(Tenant, tenant_id)
    if tenant is None:
        return jsonify(error="resource_not_found", message="Gabinete nao encontrado."), 404
    users = db.session.execute(
        select(User).where(User.tenant_id == tenant_id).order_by(User.name)
    ).scalars()
    return jsonify(
        tenant=_tenant_data(tenant),
        content=[_tenant_user_data(item) for item in users],
    )


@platform_bp.post("/gabinetes/<uuid:tenant_id>/usuarios")
@platform_admin_required
def create_tenant_user(tenant_id: uuid.UUID):
    tenant = db.session.get(Tenant, tenant_id)
    if tenant is None:
        return jsonify(error="resource_not_found", message="Gabinete nao encontrado."), 404
    payload = request.get_json(silent=True) or {}
    name = str(payload.get("nome", "")).strip()
    email = str(payload.get("email", "")).strip().lower()
    cpf = _cpf_digits(payload.get("cpf"))
    phone = str(payload.get("telefone", "")).strip()
    password = str(payload.get("senha", "")).strip()
    try:
        role = Role(str(payload.get("perfil", "staff")).lower())
    except ValueError:
        return jsonify(error="validation_error", message="Perfil invalido."), 422
    if role not in TENANT_ROLES:
        return jsonify(error="validation_error", message="Perfil invalido para gabinete."), 422
    validation = _validate_tenant_user_payload(
        tenant_id=tenant_id,
        name=name,
        email=email,
        cpf=cpf,
        phone=phone,
        role=role,
        password=password,
    )
    if validation:
        return validation
    if _active_tenant_users(tenant_id) >= user_limit_for_plan(tenant.plan):
        return jsonify(error="user_limit_reached", message=USER_LIMIT_REACHED_MESSAGE), 422
    item = User(
        tenant_id=tenant_id,
        name=name,
        email=email,
        cpf=cpf,
        phone=_phone_digits(phone) or None,
        password_hash=hash_password(password),
        role=role,
        status=UserStatus.ACTIVE,
    )
    db.session.add(item)
    db.session.flush()
    after = _tenant_user_data(item)
    add_audit(tenant_id, _actor_id(), "platform.tenant_user.created", "user", item.id, None, after)
    db.session.commit()
    return jsonify(after), 201


@platform_bp.patch("/gabinetes/<uuid:tenant_id>/usuarios/<uuid:user_id>")
@platform_admin_required
def update_tenant_user(tenant_id: uuid.UUID, user_id: uuid.UUID):
    tenant = db.session.get(Tenant, tenant_id)
    if tenant is None:
        return jsonify(error="resource_not_found", message="Gabinete nao encontrado."), 404
    item = _tenant_user(tenant_id, user_id)
    if item is None:
        return jsonify(error="resource_not_found", message="Usuario nao encontrado."), 404
    payload = request.get_json(silent=True) or {}
    before = _tenant_user_data(item)
    if "nome" in payload:
        name = str(payload["nome"]).strip()
        if len(name) < 2:
            return jsonify(error="validation_error", message="Informe o nome do usuario."), 422
        item.name = name
    if "email" in payload:
        email = str(payload["email"]).strip().lower()
        validation = _validate_unique_email(email, exclude_user_id=item.id)
        if validation:
            return validation
        item.email = email
    if "cpf" in payload:
        cpf = _cpf_digits(payload["cpf"])
        validation = _validate_unique_cpf(cpf, exclude_user_id=item.id)
        if validation:
            return validation
        item.cpf = cpf
    if "telefone" in payload:
        phone = str(payload["telefone"]).strip()
        if phone and not BR_PHONE_RE.match(phone):
            return (
                jsonify(error="validation_error", message="Informe um telefone valido com DDD."),
                422,
            )
        item.phone = _phone_digits(phone) or None
    if "perfil" in payload:
        try:
            role = Role(str(payload["perfil"]).lower())
        except ValueError:
            return jsonify(error="validation_error", message="Perfil invalido."), 422
        if role not in TENANT_ROLES:
            return jsonify(error="validation_error", message="Perfil invalido para gabinete."), 422
        if (
            role in {Role.ADMIN, Role.REPRESENTATIVE}
            and item.role != role
            and _tenant_role_exists(tenant_id, role, exclude_user_id=item.id)
        ):
            return jsonify(error="role_limit_reached", message=_single_role_message(role)), 422
        item.role = role
    if "status" in payload:
        try:
            new_status = UserStatus(str(payload["status"]).lower())
        except ValueError:
            return jsonify(error="validation_error", message="Status invalido."), 422
        if item.status != UserStatus.ACTIVE and new_status == UserStatus.ACTIVE:
            if _active_tenant_users(tenant_id) >= user_limit_for_plan(tenant.plan):
                return (
                    jsonify(error="user_limit_reached", message=USER_LIMIT_REACHED_MESSAGE),
                    422,
                )
        item.status = new_status
    if payload.get("senha"):
        password = str(payload["senha"])
        if len(password) < 8:
            return (
                jsonify(error="validation_error", message="Senha deve ter ao menos 8 caracteres."),
                422,
            )
        item.password_hash = hash_password(password)
    db.session.flush()
    after = _tenant_user_data(item)
    add_audit(
        tenant_id, _actor_id(), "platform.tenant_user.updated", "user", item.id, before, after
    )
    db.session.commit()
    return jsonify(after)


@platform_bp.delete("/gabinetes/<uuid:tenant_id>/usuarios/<uuid:user_id>")
@platform_admin_required
def block_tenant_user(tenant_id: uuid.UUID, user_id: uuid.UUID):
    tenant = db.session.get(Tenant, tenant_id)
    if tenant is None:
        return jsonify(error="resource_not_found", message="Gabinete nao encontrado."), 404
    item = _tenant_user(tenant_id, user_id)
    if item is None:
        return jsonify(error="resource_not_found", message="Usuario nao encontrado."), 404
    before = _tenant_user_data(item)
    item.status = UserStatus.BLOCKED
    db.session.flush()
    after = _tenant_user_data(item)
    add_audit(
        tenant_id, _actor_id(), "platform.tenant_user.blocked", "user", item.id, before, after
    )
    db.session.commit()
    return jsonify(after)


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
    if (
        user.status != UserStatus.ACTIVE
        and _active_tenant_users(tenant_id) >= user_limit_for_plan(tenant.plan)
    ):
        return jsonify(error="user_limit_reached", message=USER_LIMIT_REACHED_MESSAGE), 422
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


def _active_tenant_users(tenant_id: uuid.UUID) -> int:
    return (
        db.session.scalar(
            select(func.count(User.id)).where(
                User.tenant_id == tenant_id,
                User.status == UserStatus.ACTIVE,
            )
        )
        or 0
    )


def _tenant_user(tenant_id: uuid.UUID, user_id: uuid.UUID) -> User | None:
    return db.session.execute(
        select(User).where(User.tenant_id == tenant_id, User.id == user_id)
    ).scalar_one_or_none()


def _tenant_role_exists(
    tenant_id: uuid.UUID, role: Role, exclude_user_id: uuid.UUID | None = None
) -> bool:
    statement = select(User.id).where(User.tenant_id == tenant_id, User.role == role)
    if exclude_user_id:
        statement = statement.where(User.id != exclude_user_id)
    return db.session.execute(statement).scalar_one_or_none() is not None


def _validate_tenant_user_payload(
    *,
    tenant_id: uuid.UUID,
    name: str,
    email: str,
    cpf: str,
    phone: str,
    role: Role,
    password: str,
):
    if len(name) < 2 or len(password) < 8:
        return (
            jsonify(error="validation_error", message="Informe nome e senha segura."),
            422,
        )
    validation = _validate_unique_email(email)
    if validation:
        return validation
    validation = _validate_unique_cpf(cpf)
    if validation:
        return validation
    if phone and not BR_PHONE_RE.match(phone):
        return (
            jsonify(error="validation_error", message="Informe um telefone valido com DDD."),
            422,
        )
    if role in {Role.ADMIN, Role.REPRESENTATIVE} and _tenant_role_exists(tenant_id, role):
        return jsonify(error="role_limit_reached", message=_single_role_message(role)), 422
    return None


def _validate_unique_email(email: str, exclude_user_id: uuid.UUID | None = None):
    if not email or not EMAIL_RE.match(email):
        return jsonify(error="validation_error", message="Informe um e-mail valido."), 422
    statement = select(User.id).where(User.email == email)
    if exclude_user_id:
        statement = statement.where(User.id != exclude_user_id)
    if db.session.execute(statement).scalar_one_or_none():
        return jsonify(error="conflict", message="E-mail ja cadastrado na plataforma."), 409
    return None


def _validate_unique_cpf(cpf: str, exclude_user_id: uuid.UUID | None = None):
    if not _valid_cpf(cpf):
        return jsonify(error="validation_error", message="Informe um CPF valido."), 422
    statement = select(User.id).where(User.cpf == cpf)
    if exclude_user_id:
        statement = statement.where(User.id != exclude_user_id)
    if db.session.execute(statement).scalar_one_or_none():
        return jsonify(error="conflict", message="CPF ja cadastrado na plataforma."), 409
    return None


def _single_role_message(role: Role) -> str:
    if role == Role.ADMIN:
        return "Ja existe um usuario administrador neste gabinete."
    if role == Role.REPRESENTATIVE:
        return "Ja existe um usuario parlamentar neste gabinete."
    return "Perfil limitado ja cadastrado neste gabinete."


def _cpf_digits(value) -> str:
    return re.sub(r"\D", "", str(value or ""))[:11]


def _phone_digits(value) -> str:
    return re.sub(r"\D", "", str(value or ""))[:11]


def _valid_cpf(value: str) -> bool:
    if len(value) != 11 or len(set(value)) == 1:
        return False
    digits = [int(item) for item in value]
    for position in (9, 10):
        total = sum(digits[index] * (position + 1 - index) for index in range(position))
        check = (total * 10) % 11
        if check == 10:
            check = 0
        if digits[position] != check:
            return False
    return True


def _format_cpf(value: str | None) -> str | None:
    digits = _cpf_digits(value)
    if len(digits) != 11:
        return None
    return f"{digits[:3]}.{digits[3:6]}.{digits[6:9]}-{digits[9:]}"


def _format_phone(value: str | None) -> str | None:
    digits = _phone_digits(value)
    if len(digits) == 11:
        return f"({digits[:2]}) {digits[2:7]}-{digits[7:]}"
    if len(digits) == 10:
        return f"({digits[:2]}) {digits[2:6]}-{digits[6:]}"
    return value or None


def _count_by(column) -> dict:
    rows = db.session.execute(select(column, func.count()).group_by(column))
    return {str(key): value for key, value in rows}


def _tenant_matches_optional_filters(
    tenant: Tenant, jurisdiction: str, representative: str
) -> bool:
    if jurisdiction:
        jurisdiction_values = [
            tenant.jurisdiction_name,
            tenant.jurisdiction_city,
            tenant.jurisdiction_state,
            tenant.jurisdiction_ibge_code,
            tenant.chamber_type,
        ]
        if not _contains_any(jurisdiction, jurisdiction_values):
            return False
    if representative:
        data = tenant.representative_info or {}
        representative_values = [
            data.get("nomeParlamentar"),
            data.get("nomeCompleto"),
            data.get("nomeCivil"),
            data.get("partido"),
            data.get("partidoNome"),
        ]
        if not _contains_any(representative, representative_values):
            return False
    return True


def _contains_any(query: str, values: list[str | None]) -> bool:
    return any(query in str(value or "").casefold() for value in values)


def _optional_datetime_start(value) -> datetime | None:
    parsed = _optional_date(value)
    return datetime.combine(parsed, time.min) if parsed else None


def _optional_datetime_end(value) -> datetime | None:
    parsed = _optional_date(value)
    return datetime.combine(parsed, time.max) if parsed else None


def _optional_date(value) -> date | None:
    if value in (None, ""):
        return None
    try:
        return date.fromisoformat(str(value))
    except ValueError as error:
        raise ValueError("Data de onboarding invalida.") from error


def _contact_attempt(payload) -> dict:
    if not isinstance(payload, dict):
        raise ValueError("Tentativa de contato invalida.")
    channel = str(payload.get("canal", "")).strip().lower()
    note = str(payload.get("observacao", "")).strip()
    result = str(payload.get("resultado", "")).strip()[:120]
    if channel not in {"email", "telefone", "whatsapp"} or len(note) < 2:
        raise ValueError("Informe canal e observacao da tentativa de contato.")
    return {
        "canal": channel,
        "resultado": result or "registrado",
        "observacao": note[:1000],
        "registradoEm": date.today().isoformat(),
    }


def _contract_document(payload) -> dict:
    if not isinstance(payload, dict):
        raise ValueError("Documento invalido.")
    name = str(payload.get("nome", "")).strip()
    kind = str(payload.get("tipo", "contrato_assinado")).strip().lower()
    url = str(payload.get("url", "")).strip()
    notes = str(payload.get("observacao", "")).strip()
    if len(name) < 2:
        raise ValueError("Informe o nome do documento.")
    return {
        "tipo": kind[:60],
        "nome": name[:180],
        "url": url[:500] or None,
        "observacao": notes[:1000] or None,
        "registradoEm": date.today().isoformat(),
    }


def _payment_item(payload) -> dict:
    if not isinstance(payload, dict):
        raise ValueError("Pagamento invalido.")
    kind = str(payload.get("tipo", "")).strip().lower()
    status = str(payload.get("status", "")).strip().lower()
    if kind not in {"onboarding", "mensalidade"}:
        raise ValueError("Tipo de pagamento invalido.")
    if status not in LEAD_PAYMENT_STATUSES:
        raise ValueError("Status de pagamento invalido.")
    try:
        amount = float(payload.get("valor") or 0)
    except (TypeError, ValueError) as error:
        raise ValueError("Valor de pagamento invalido.") from error
    return {
        "tipo": kind,
        "status": status,
        "valor": round(amount, 2),
        "vencimento": str(payload.get("vencimento", "")).strip()[:10] or None,
        "observacao": str(payload.get("observacao", "")).strip()[:1000] or None,
        "registradoEm": date.today().isoformat(),
    }


def _onboarding_details(payload) -> dict:
    if not isinstance(payload, dict):
        raise ValueError("Dados de onboarding invalidos.")
    location = str(payload.get("local", "")).strip().lower()
    if location not in {"remota", "presencial"}:
        raise ValueError("Local de onboarding invalido.")
    data = str(payload.get("data", "")).strip()
    _optional_date(data)
    return {
        "data": data,
        "local": location,
        "tecnicoResponsavel": str(payload.get("tecnicoResponsavel", "")).strip()[:160],
        "observacao": str(payload.get("observacao", "")).strip()[:1000],
    }


def _generated_contract(item: PublicLead) -> dict:
    return {
        "tipo": "contrato_gerado",
        "nome": f"Contrato GabFlow - {item.organization}",
        "url": None,
        "observacao": "Minuta gerada para conferência comercial.",
        "registradoEm": date.today().isoformat(),
    }


def _append_lead_action(item: PublicLead, action: str, payload: dict) -> None:
    event = {"acao": action, "dados": payload, "registradoEm": date.today().isoformat()}
    item.action_history = [event, *(item.action_history or [])][:100]


def _jurisdiction_name(city: str | None, state: str | None) -> str | None:
    if city and state:
        return f"{city}/{state}"
    if state:
        return state
    return None


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug[:80] or f"gabinete-{uuid.uuid4().hex[:8]}"


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
