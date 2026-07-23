import gzip
import json
import re
import urllib.error
import urllib.parse
import urllib.request
import uuid

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt, get_jwt_identity
from sqlalchemy import String, cast, func, select

from app.audit import add_audit
from app.agency_suggestions import reload_suggested_agencies
from app.auth.permissions import roles_required
from app.auth.security import hash_password
from app.default_categories import ensure_default_request_categories
from app.extensions import db
from app.models import (
    AuditLog,
    ExternalAgency,
    IntegrationSetting,
    IntegrationStatus,
    IntegrationType,
    PoliticalParty,
    RequestCategory,
    Role,
    Tenant,
    Territory,
    User,
    UserStatus,
)
from app.plans import USER_LIMIT_REACHED_MESSAGE, user_limit_for_plan
from app.territory_suggestions import reload_suggested_territories

admin_bp = Blueprint("admin", __name__)

CHAMBER_TYPES = {"CAMARA_MUNICIPAL", "ASSEMBLEIA_LEGISLATIVA"}
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]{2,}$")
BR_PHONE_RE = re.compile(r"^\D*([1-9]{2})\D*(?:(9\d{4})\D*(\d{4})|([2-5]\d{3})\D*(\d{4}))\D*$")
IBGE_MALHAS_URL = (
    "https://servicodados.ibge.gov.br/api/v3/malhas/"
    "{scope}/{code}?formato=application/vnd.geo+json&qualidade=minima"
)


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
        data["responsavel"] = item.responsible
        data["telefone"] = _format_phone(item.phone)
        data["origem"] = item.source
    return data


def _jurisdiction_data(item: Tenant) -> dict:
    return {
        "tipoCasa": item.chamber_type,
        "nome": item.jurisdiction_name,
        "municipio": item.jurisdiction_city,
        "uf": item.jurisdiction_state,
        "codigoIbge": item.jurisdiction_ibge_code,
        "centro": {
            "latitude": item.jurisdiction_center_latitude,
            "longitude": item.jurisdiction_center_longitude,
        }
        if item.jurisdiction_center_latitude is not None
        and item.jurisdiction_center_longitude is not None
        else None,
        "limites": item.jurisdiction_bounds,
        "geojson": item.jurisdiction_geojson,
    }


def _office_profile_data(item: Tenant) -> dict:
    visual_identity = item.visual_identity or {}
    user_limit = user_limit_for_plan(item.plan)
    return {
        "vereador": item.representative_info or {},
        "mandato": item.mandate_info or {},
        "dadosInstitucionais": visual_identity.get("dadosInstitucionais") or {},
        "redesSociais": visual_identity.get("redesSociais") or {},
        "identidadeVisual": visual_identity,
        "chefeGabineteId": str(item.chief_of_staff_id) if item.chief_of_staff_id else None,
        "contrato": {
            "plano": item.plan,
            "limiteUsuarios": user_limit,
            "usuariosAtivos": _active_user_count(item.id),
        },
    }


def _parliamentarian_data(item: Tenant) -> dict:
    data = item.representative_info or {}
    return {
        "nomeCompleto": data.get("nomeCompleto") or data.get("nomeCivil") or "",
        "nomeParlamentar": data.get("nomeParlamentar") or "",
        "cpf": _format_cpf(data.get("cpf")),
        "fotografiaUrl": data.get("fotografiaUrl") or "",
        "partidoId": data.get("partidoId") or "",
        "partido": data.get("partido") or "",
        "partidoNome": data.get("partidoNome") or "",
        "partidoNumero": data.get("partidoNumero") or "",
        "partidoLogoUrl": data.get("partidoLogoUrl") or "",
        "partidoFonteUrl": data.get("partidoFonteUrl") or "",
        "coligacaoFederacao": data.get("coligacaoFederacao") or "",
        "email": data.get("email") or "",
        "telefoneInstitucional": data.get("telefoneInstitucional") or "",
        "biografia": data.get("biografia") or "",
        "dadosOficiais": data.get("dadosOficiais") or "",
        "areasPrioritarias": data.get("areasPrioritarias") or [],
        "redesSociais": data.get("redesSociais") or {},
        "statusMandato": data.get("statusMandato") or "ATIVO",
        "mandatos": data.get("mandatos") or [],
        "insightsOficiais": data.get("insightsOficiais") or {},
        "arquivosCampanha": data.get("arquivosCampanha") or [],
    }


def _user_data(item: User) -> dict:
    chief_of_staff = bool(item.tenant and item.tenant.chief_of_staff_id == item.id)
    return {
        "id": str(item.id),
        "nome": item.name,
        "email": item.email,
        "cpf": _format_cpf(item.cpf),
        "telefone": _format_phone(item.phone),
        "perfil": item.role.value,
        "status": item.status.value,
        "chefeGabinete": chief_of_staff,
        "funcoes": ["chefe_gabinete"] if chief_of_staff else [],
        "mfaHabilitado": item.mfa_enabled,
        "ultimoLoginEm": item.last_login_at.isoformat() if item.last_login_at else None,
        "criadoEm": item.created_at.isoformat(),
    }


def _integration_data(item: IntegrationSetting) -> dict:
    return {
        "id": str(item.id),
        "tipo": item.integration_type.value,
        "status": item.status.value,
        "nome": item.name,
        "configuracao": item.config,
        "segredosConfigurados": item.secrets_configured,
        "atualizadaEm": item.updated_at.isoformat(),
    }


def _party_data(item: PoliticalParty) -> dict:
    return {
        "id": str(item.id),
        "sigla": item.acronym,
        "nome": item.name,
        "numero": item.ballot_number,
        "deferimento": item.registration_date,
        "presidenteNacional": item.national_president,
        "logoUrl": item.logo_url,
        "fonteUrl": item.source_url,
    }


AUDIT_ACTION_LABELS = {
    "auth.login": "Acessou o sistema",
    "tenant.user.created": "Usuário criado",
    "tenant.user.updated": "Usuário atualizado",
    "tenant.profile.updated": "Dados do gabinete atualizados",
    "tenant.representative.updated": "Dados do parlamentar atualizados",
    "category.created": "Categoria criada",
    "category.updated": "Categoria atualizada",
    "category.deleted": "Categoria desativada",
    "territory.created": "Território criado",
    "territory.updated": "Território atualizado",
    "territory.deleted": "Território desativado",
    "territory.suggestions.reloaded": "Sugestões de territórios recarregadas",
    "agency.created": "Órgão criado",
    "agency.updated": "Órgão atualizado",
    "agency.deleted": "Órgão desativado",
    "agency.suggestions.reloaded": "Sugestões de órgãos recarregadas",
    "integration.created": "Integração criada",
    "integration.updated": "Integração atualizada",
    "response_template.created": "Template de resposta criado",
    "response_template.updated": "Template de resposta editado",
    "response_template.deactivated": "Template de resposta desativado",
}

AUDIT_ENTITY_LABELS = {
    "agenda_event": "Agenda",
    "citizen": "Cidadão",
    "external_agency": "Órgão",
    "integration_setting": "Integração",
    "rag_document": "Documento de conhecimento",
    "rag_document_version": "Versão de documento",
    "request": "Solicitação",
    "request_category": "Categoria",
    "request_task": "Tarefa",
    "response_template": "Template de resposta",
    "service_request": "Solicitação",
    "tenant": "Gabinete",
    "territory": "Território",
    "user": "Usuário",
}


def _audit_record_label(item: AuditLog) -> str:
    source = item.after or item.before or {}
    for key in ("nome", "name", "titulo", "title", "assunto", "email"):
        value = source.get(key)
        if value:
            return str(value)
    if item.entity_type == "user":
        user = db.session.get(User, item.entity_id) if item.entity_id else None
        if user:
            return user.name
    return "Registro interno"


def _audit_action_label(action: str) -> str:
    if action in AUDIT_ACTION_LABELS:
        return AUDIT_ACTION_LABELS[action]
    words = action.replace(".", " ").replace("_", " ").split()
    return " ".join(word.capitalize() for word in words) if words else "Evento registrado"


def _audit_data(item: AuditLog, users_by_id: dict[uuid.UUID, User]) -> dict:
    user = users_by_id.get(item.user_id) if item.user_id else None
    actor = user.name if user else "Sistema"
    actor_detail = user.email if user else "Ação automática ou usuário removido"
    entity = AUDIT_ENTITY_LABELS.get(item.entity_type, item.entity_type.replace("_", " ").title())
    record = _audit_record_label(item)
    action = _audit_action_label(item.action)
    return {
        "id": str(item.id),
        "acao": item.action,
        "acaoAmigavel": action,
        "resumo": f"{action} em {entity.lower()}",
        "entidade": item.entity_type,
        "entidadeAmigavel": entity,
        "entidadeId": item.entity_id,
        "registro": record,
        "usuarioId": str(item.user_id) if item.user_id else None,
        "usuarioNome": actor,
        "usuarioEmail": actor_detail,
        "criadoEm": item.created_at.isoformat(),
    }


@admin_bp.get("/perfil-gabinete")
@roles_required("admin")
def get_office_profile():
    tenant_id, _ = _context()
    tenant = db.session.get(Tenant, tenant_id)
    return jsonify(_office_profile_data(tenant))


@admin_bp.get("/partidos")
@roles_required("admin")
def admin_list_parties():
    query = str(request.args.get("q", "")).strip()
    statement = (
        select(PoliticalParty)
        .where(PoliticalParty.active.is_(True))
        .order_by(PoliticalParty.acronym)
    )
    if query:
        like = f"%{query.lower()}%"
        statement = statement.where(
            (func.lower(PoliticalParty.acronym).like(like))
            | (func.lower(PoliticalParty.name).like(like))
            | (cast(PoliticalParty.ballot_number, String).like(like))
        )
    items = db.session.execute(statement).scalars().all()
    return jsonify(content=[_party_data(item) for item in items])


@admin_bp.get("/parlamentar")
@roles_required("admin")
def get_parliamentarian_profile():
    tenant_id, _ = _context()
    tenant = db.session.get(Tenant, tenant_id)
    return jsonify(_parliamentarian_data(tenant))


@admin_bp.patch("/parlamentar")
@roles_required("admin")
def update_parliamentarian_profile():
    tenant_id, user_id = _context()
    tenant = db.session.get(Tenant, tenant_id)
    payload = request.get_json(silent=True) or {}
    before = _parliamentarian_data(tenant)
    try:
        tenant.representative_info = _clean_parliamentarian(payload, before)
    except ValueError as error:
        return jsonify(error="validation_error", message=str(error)), 422
    after = _parliamentarian_data(tenant)
    add_audit(
        tenant_id,
        user_id,
        "tenant.parliamentarian.updated",
        "tenant",
        tenant.id,
        before,
        after,
    )
    db.session.commit()
    return jsonify(after)


@admin_bp.post("/parlamentar/insights-oficiais")
@roles_required("admin")
def parliamentarian_official_insights():
    tenant_id, user_id = _context()
    tenant = db.session.get(Tenant, tenant_id)
    data = _parliamentarian_data(tenant)
    payload = request.get_json(silent=True) or {}
    name = str(
        payload.get("nome") or data["nomeParlamentar"] or data["nomeCompleto"]
    ).strip()
    party = str(data.get("partido") or "").strip()
    query = " ".join(item for item in [name, party] if item).strip() or "parlamentar"
    encoded = urllib.parse.quote_plus(query)
    insights = {
        "consulta": query,
        "fontes": [
            {
                "nome": "TSE - Divulgacao de Candidaturas e Contas",
                "url": (
                    "https://divulgacandcontas.tse.jus.br/divulga/#/consulta/"
                    f"candidatos?query={encoded}"
                ),
                "uso": (
                    "Conferir dados de candidatura, partido, bens declarados "
                    "e resultado eleitoral quando disponivel."
                ),
            },
            {
                "nome": "TSE - Partidos registrados",
                "url": "https://www.tse.jus.br/partidos/partidos-registrados-no-tse",
                "uso": "Validar sigla, numero de legenda e dados oficiais do partido.",
            },
            {
                "nome": "TRE do estado",
                "url": f"https://www.google.com/search?q=site%3Atre.jus.br+{encoded}",
                "uso": (
                    "Buscar registros regionais, diplomacao, julgamento de contas "
                    "e comunicados oficiais."
                ),
            },
        ],
        "insightsSugeridos": [
            "Validar nome de urna, partido, votacao recebida e situacao da candidatura.",
            (
                "Comparar areas prioritarias informadas com propostas, plano de governo "
                "e historico legislativo."
            ),
            (
                "Registrar fontes oficiais consultadas antes de usar os dados "
                "em comunicacoes publicas."
            ),
        ],
    }
    add_audit(
        tenant_id,
        user_id,
        "tenant.parliamentarian.official_insights.requested",
        "tenant",
        tenant.id,
        None,
        insights,
    )
    db.session.commit()
    return jsonify(insights)


@admin_bp.patch("/perfil-gabinete")
@roles_required("admin")
def update_office_profile():
    tenant_id, user_id = _context()
    tenant = db.session.get(Tenant, tenant_id)
    payload = request.get_json(silent=True) or {}
    before = _office_profile_data(tenant)
    try:
        tenant.representative_info = _clean_dict(
            payload.get("vereador"), tenant.representative_info
        )
        tenant.mandate_info = _clean_dict(payload.get("mandato"), tenant.mandate_info)
        visual_identity = _clean_dict(
            payload.get("identidadeVisual"), tenant.visual_identity
        )
        if "dadosInstitucionais" in payload:
            visual_identity["dadosInstitucionais"] = _clean_dict(
                payload.get("dadosInstitucionais"),
                visual_identity.get("dadosInstitucionais"),
            )
        if "redesSociais" in payload:
            visual_identity["redesSociais"] = _clean_dict(
                payload.get("redesSociais"),
                visual_identity.get("redesSociais"),
            )
        _validate_office_contacts(visual_identity)
        tenant.visual_identity = visual_identity
        office_name = str(
            (visual_identity.get("dadosInstitucionais") or {}).get("nomeGabinete") or ""
        ).strip()
        if office_name:
            tenant.name = office_name[:160]
    except ValueError as error:
        return jsonify(error="validation_error", message=str(error)), 422
    chief_id = payload.get("chefeGabineteId", tenant.chief_of_staff_id)
    if chief_id in ("", None):
        tenant.chief_of_staff_id = None
    else:
        chief = _tenant_user(tenant_id, chief_id)
        if chief is None:
            return jsonify(error="validation_error", message="Chefe de gabinete invalido."), 422
        if chief.status != UserStatus.ACTIVE:
            return jsonify(
                error="validation_error",
                message="Chefe de gabinete deve ser um usuario ativo.",
            ), 422
        if chief.role in {Role.PLATFORM_ADMIN, Role.REPRESENTATIVE}:
            return jsonify(
                error="validation_error",
                message="Chefe de gabinete deve ser assessor ou administrador interno.",
            ), 422
        tenant.chief_of_staff_id = chief.id
    after = _office_profile_data(tenant)
    add_audit(
        tenant_id, user_id, "tenant.office_profile.updated", "tenant", tenant.id, before, after
    )
    db.session.commit()
    return jsonify(after)


@admin_bp.get("/usuarios")
@roles_required("admin")
def admin_list_users():
    tenant_id, _ = _context()
    users = db.session.execute(
        select(User).where(User.tenant_id == tenant_id).order_by(User.name)
    ).scalars()
    return jsonify(content=[_user_data(item) for item in users])


@admin_bp.post("/usuarios")
@roles_required("admin")
def admin_create_user():
    tenant_id, user_id = _context()
    tenant = db.session.get(Tenant, tenant_id)
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
    if role not in {Role.ADMIN, Role.REPRESENTATIVE, Role.STAFF}:
        return jsonify(error="validation_error", message="Perfil invalido para gabinete."), 422
    if not EMAIL_RE.match(email):
        return jsonify(error="validation_error", message="Informe um e-mail valido."), 422
    if not _valid_cpf(cpf):
        return jsonify(error="validation_error", message="Informe um CPF valido."), 422
    if phone and not BR_PHONE_RE.match(phone):
        return jsonify(error="validation_error", message="Informe um telefone valido com DDD."), 422
    if len(name) < 2 or not email or len(password) < 8:
        return (
            jsonify(error="validation_error", message="Informe nome, e-mail e senha segura."),
            422,
        )
    if role in {Role.ADMIN, Role.REPRESENTATIVE} and _tenant_role_exists(tenant_id, role):
        return jsonify(error="role_limit_reached", message=_single_role_message(role)), 422
    if _active_user_count(tenant_id) >= user_limit_for_plan(tenant.plan):
        return jsonify(error="user_limit_reached", message=USER_LIMIT_REACHED_MESSAGE), 422
    exists = db.session.execute(select(User.id).where(User.email == email)).scalar_one_or_none()
    if exists:
        return jsonify(error="conflict", message="E-mail ja cadastrado na plataforma."), 409
    exists = db.session.execute(select(User.id).where(User.cpf == cpf)).scalar_one_or_none()
    if exists:
        return jsonify(error="conflict", message="CPF ja cadastrado na plataforma."), 409
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
    after = _user_data(item)
    add_audit(tenant_id, user_id, "tenant.user.created", "user", item.id, None, after)
    db.session.commit()
    return jsonify(after), 201


@admin_bp.patch("/usuarios/<uuid:item_id>")
@roles_required("admin")
def admin_update_user(item_id: uuid.UUID):
    tenant_id, user_id = _context()
    item = _tenant_user(tenant_id, item_id)
    if item is None:
        return jsonify(error="resource_not_found", message="Usuario nao encontrado."), 404
    payload = request.get_json(silent=True) or {}
    before = _user_data(item)
    if "nome" in payload:
        item.name = str(payload["nome"]).strip() or item.name
    if "email" in payload:
        email = str(payload["email"]).strip().lower()
        if not email or not EMAIL_RE.match(email):
            return jsonify(error="validation_error", message="Informe um e-mail valido."), 422
        exists = db.session.execute(
            select(User.id).where(User.email == email, User.id != item.id)
        ).scalar_one_or_none()
        if exists:
            return jsonify(error="conflict", message="E-mail ja cadastrado na plataforma."), 409
        item.email = email
    if "cpf" in payload:
        cpf = _cpf_digits(payload["cpf"])
        if not _valid_cpf(cpf):
            return jsonify(error="validation_error", message="Informe um CPF valido."), 422
        exists = db.session.execute(
            select(User.id).where(User.cpf == cpf, User.id != item.id)
        ).scalar_one_or_none()
        if exists:
            return jsonify(error="conflict", message="CPF ja cadastrado na plataforma."), 409
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
        if role not in {Role.ADMIN, Role.REPRESENTATIVE, Role.STAFF}:
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
            tenant = db.session.get(Tenant, tenant_id)
            if _active_user_count(tenant_id) >= user_limit_for_plan(tenant.plan):
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
    after = _user_data(item)
    add_audit(tenant_id, user_id, "tenant.user.updated", "user", item.id, before, after)
    db.session.commit()
    return jsonify(after)


@admin_bp.get("/auditoria")
@roles_required("admin")
def admin_audit():
    tenant_id, _ = _context()
    page = _positive_int(request.args.get("page"), 1)
    per_page = _positive_int(request.args.get("perPage"), 10)
    if per_page not in {10, 25, 50}:
        per_page = 10
    total = db.session.scalar(
        select(func.count(AuditLog.id)).where(AuditLog.tenant_id == tenant_id)
    )
    items = list(
        db.session.execute(
        select(AuditLog)
        .where(AuditLog.tenant_id == tenant_id)
        .order_by(AuditLog.created_at.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
        ).scalars()
    )
    user_ids = {item.user_id for item in items if item.user_id}
    users_by_id = {}
    if user_ids:
        users = db.session.execute(select(User).where(User.id.in_(user_ids))).scalars()
        users_by_id = {user.id: user for user in users}
    total_pages = max(1, (total + per_page - 1) // per_page)
    return jsonify(
        content=[_audit_data(item, users_by_id) for item in items],
        page=page,
        perPage=per_page,
        total=total,
        totalPages=total_pages,
    )


@admin_bp.get("/jurisdicao")
@roles_required("admin", "manager", "staff", "representative")
def get_jurisdiction():
    tenant_id, _ = _context()
    tenant = db.session.get(Tenant, tenant_id)
    return jsonify(_jurisdiction_data(tenant))


@admin_bp.patch("/jurisdicao")
@roles_required("admin")
def update_jurisdiction():
    return (
        jsonify(
            error="jurisdiction_locked",
            message="A jurisdição e o tipo do gabinete são definidos na contratação e não podem ser alterados.",
        ),
        403,
    )


@admin_bp.post("/jurisdicao/ibge")
@roles_required("admin")
def import_ibge_jurisdiction():
    tenant_id, user_id = _context()
    tenant = db.session.get(Tenant, tenant_id)
    payload = request.get_json(silent=True) or {}
    before = _jurisdiction_data(tenant)
    chamber_type = str(tenant.chamber_type or "").strip().upper()
    requested_chamber_type = str(payload.get("tipoCasa", chamber_type)).strip().upper()
    if requested_chamber_type and requested_chamber_type != chamber_type:
        return (
            jsonify(error="jurisdiction_locked", message="O tipo do gabinete não pode ser alterado."),
            403,
        )
    if chamber_type and chamber_type not in CHAMBER_TYPES:
        return jsonify(error="validation_error", message="Tipo de casa legislativa invÃ¡lido."), 422
    requested_ibge_code = str(payload.get("codigoIbge", tenant.jurisdiction_ibge_code or "")).strip()
    current_ibge_code = str(tenant.jurisdiction_ibge_code or "").strip()
    if current_ibge_code and requested_ibge_code and requested_ibge_code != current_ibge_code:
        return (
            jsonify(error="jurisdiction_locked", message="A jurisdição do gabinete não pode ser alterada."),
            403,
        )
    ibge_code = current_ibge_code or requested_ibge_code
    if not ibge_code.isdigit():
        return jsonify(error="validation_error", message="Informe um cÃ³digo IBGE numÃ©rico."), 422

    scope = "estados" if chamber_type == "ASSEMBLEIA_LEGISLATIVA" else "municipios"
    try:
        geojson = _fetch_ibge_geojson(scope, ibge_code)
        bounds, center = _geojson_bounds_and_center(geojson)
    except ValueError as error:
        return jsonify(error="validation_error", message=str(error)), 422

    tenant.jurisdiction_ibge_code = tenant.jurisdiction_ibge_code or ibge_code
    tenant.jurisdiction_geojson = geojson
    tenant.jurisdiction_bounds = bounds
    tenant.jurisdiction_center_latitude = center["latitude"]
    tenant.jurisdiction_center_longitude = center["longitude"]
    if tenant.jurisdiction_name is None:
        tenant.jurisdiction_name = _default_jurisdiction_name(
            tenant.chamber_type or "", tenant.jurisdiction_city, tenant.jurisdiction_state
        )

    after = _jurisdiction_data(tenant)
    add_audit(
        tenant_id,
        user_id,
        "tenant.jurisdiction.ibge_imported",
        "tenant",
        tenant.id,
        before,
        after,
    )
    db.session.commit()
    return jsonify(after)


@admin_bp.get("/integracoes")
@roles_required("admin")
def list_integrations():
    tenant_id, _ = _context()
    items = db.session.execute(
        select(IntegrationSetting)
        .where(IntegrationSetting.tenant_id == tenant_id)
        .order_by(IntegrationSetting.integration_type)
    ).scalars()
    return jsonify(content=[_integration_data(item) for item in items])


@admin_bp.post("/integracoes")
@roles_required("admin")
def upsert_integration():
    tenant_id, user_id = _context()
    payload = request.get_json(silent=True) or {}
    try:
        integration_type = IntegrationType(str(payload.get("tipo", "")).upper())
        status = IntegrationStatus(str(payload.get("status", "RASCUNHO")).upper())
    except ValueError:
        return (
            jsonify(error="validation_error", message="Tipo ou status de integração inválido."),
            422,
        )
    name = str(payload.get("nome", "")).strip() or integration_type.value
    config = payload.get("configuracao") or {}
    if not isinstance(config, dict):
        return jsonify(error="validation_error", message="Configuração deve ser um objeto."), 422
    public_config, has_secret = _sanitize_integration_config(config)
    item = db.session.execute(
        select(IntegrationSetting).where(
            IntegrationSetting.tenant_id == tenant_id,
            IntegrationSetting.integration_type == integration_type,
        )
    ).scalar_one_or_none()
    if item is None:
        item = IntegrationSetting(
            tenant_id=tenant_id,
            integration_type=integration_type,
            updated_by_id=user_id,
            name=name,
            status=status,
            config=public_config,
            secrets_configured=has_secret,
        )
        db.session.add(item)
        action = "integration.created"
        before = None
    else:
        before = _integration_data(item)
        item.name = name
        item.status = status
        item.config = public_config
        item.secrets_configured = item.secrets_configured or has_secret
        item.updated_by_id = user_id
        action = "integration.updated"
    db.session.flush()
    after = _integration_data(item)
    add_audit(tenant_id, user_id, action, "integration_setting", item.id, before, after)
    db.session.commit()
    return jsonify(after), 201 if before is None else 200


def _sanitize_integration_config(config: dict) -> tuple[dict, bool]:
    secret_names = {
        "token",
        "secret",
        "senha",
        "password",
        "apiKey",
        "api_key",
        "accessToken",
        "access_token",
        "pageAccessToken",
        "page_access_token",
        "clientSecret",
    }
    public_config = {}
    has_secret = False
    for key, value in config.items():
        if key in secret_names:
            has_secret = has_secret or bool(value)
            continue
        public_config[str(key)] = value
    return public_config, has_secret


def _clean_dict(value, fallback) -> dict:
    if value is None:
        return fallback or {}
    if not isinstance(value, dict):
        raise ValueError("Valor estruturado invalido.")
    return {str(key): item for key, item in value.items() if item not in (None, "")}


def _validate_office_contacts(visual_identity: dict) -> None:
    institutional = visual_identity.get("dadosInstitucionais") or {}
    if not isinstance(institutional, dict):
        raise ValueError("Dados institucionais invalidos.")
    email = str(institutional.get("emailOficial") or "").strip()
    phone = str(institutional.get("telefone") or "").strip()
    site = str(institutional.get("site") or "").strip()
    logo = str(visual_identity.get("logoUrl") or "").strip()
    if email and not EMAIL_RE.match(email):
        raise ValueError("Informe um e-mail oficial valido.")
    if phone and not BR_PHONE_RE.match(phone):
        raise ValueError("Informe um telefone institucional valido com DDD.")
    if site and not _valid_http_url(site):
        raise ValueError("Informe um site institucional valido.")
    if logo and not (_valid_http_url(logo) or logo.startswith("data:image/")):
        raise ValueError("Informe uma imagem valida para o logotipo.")


def _clean_parliamentarian(value, fallback) -> dict:
    if not isinstance(value, dict):
        raise ValueError("Valor estruturado invalido.")
    data = _clean_dict(value, fallback)
    mandates = data.get("mandatos") or []
    if not isinstance(mandates, list):
        raise ValueError("Historico de mandatos invalido.")
    cleaned_mandates = []
    active_count = 0
    for mandate in mandates:
        if not isinstance(mandate, dict):
            raise ValueError("Mandato invalido.")
        cleaned = {
            str(key): item
            for key, item in mandate.items()
            if item not in (None, "")
        }
        status = str(cleaned.get("status", "")).upper()
        if status in {"ATUAL", "ATIVO"}:
            active_count += 1
            cleaned["status"] = "ATUAL"
        elif status:
            cleaned["status"] = status
        if cleaned:
            cleaned_mandates.append(cleaned)
    if active_count > 1:
        raise ValueError("Deve existir apenas um mandato atual ativo por gabinete.")
    areas = data.get("areasPrioritarias") or []
    if isinstance(areas, str):
        areas = [item.strip() for item in areas.split(",") if item.strip()]
    if not isinstance(areas, list):
        raise ValueError("Areas prioritarias invalidas.")
    redes = data.get("redesSociais") or {}
    if not isinstance(redes, dict):
        raise ValueError("Redes sociais invalidas.")
    data["areasPrioritarias"] = [str(item).strip() for item in areas if str(item).strip()]
    data["redesSociais"] = {
        str(key): str(item).strip()
        for key, item in redes.items()
        if item not in (None, "")
    }
    email = str(data.get("email") or "").strip()
    phone = str(data.get("telefoneInstitucional") or "").strip()
    photo = str(data.get("fotografiaUrl") or "").strip()
    cpf = _cpf_digits(data.get("cpf"))
    site = str(data["redesSociais"].get("site") or "").strip()
    if email and not EMAIL_RE.match(email):
        raise ValueError("Informe um e-mail valido para o parlamentar.")
    if phone and not BR_PHONE_RE.match(phone):
        raise ValueError("Informe um telefone institucional valido com DDD.")
    if cpf and not _valid_cpf(cpf):
        raise ValueError("Informe um CPF valido para o parlamentar.")
    if photo and not (_valid_http_url(photo) or photo.startswith("data:image/")):
        raise ValueError("Informe uma imagem valida para a fotografia.")
    if site and not _valid_http_url(site):
        raise ValueError("Informe um site valido para o parlamentar.")
    if cpf:
        data["cpf"] = cpf
    data["mandatos"] = cleaned_mandates
    data["statusMandato"] = str(data.get("statusMandato") or "ATIVO").upper()
    return data


def _valid_http_url(value: str) -> bool:
    candidate = value if value.lower().startswith(("http://", "https://")) else f"https://{value}"
    parsed = urllib.parse.urlsplit(candidate)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc and "." in parsed.netloc)


def _tenant_user(tenant_id: uuid.UUID, value) -> User | None:
    try:
        user_id = uuid.UUID(str(value))
    except (TypeError, ValueError):
        return None
    return db.session.execute(
        select(User).where(User.id == user_id, User.tenant_id == tenant_id)
    ).scalar_one_or_none()


def _active_user_count(tenant_id: uuid.UUID) -> int:
    return (
        db.session.scalar(
            select(func.count(User.id)).where(
                User.tenant_id == tenant_id,
                User.status == UserStatus.ACTIVE,
            )
        )
        or 0
    )


def _tenant_role_exists(
    tenant_id: uuid.UUID, role: Role, exclude_user_id: uuid.UUID | None = None
) -> bool:
    statement = select(User.id).where(User.tenant_id == tenant_id, User.role == role)
    if exclude_user_id is not None:
        statement = statement.where(User.id != exclude_user_id)
    return db.session.execute(statement).scalar_one_or_none() is not None


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


def _positive_int(value, fallback: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return fallback
    return parsed if parsed > 0 else fallback


def _optional_coordinate(value, label: str, minimum: float, maximum: float) -> float | None:
    if value in (None, ""):
        return None
    try:
        coordinate = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{label} inválida.") from error
    if not minimum <= coordinate <= maximum:
        raise ValueError(f"{label} fora do intervalo permitido.")
    return coordinate


def _validate_bounds(value) -> dict | None:
    if value in (None, ""):
        return None
    if not isinstance(value, dict):
        raise ValueError("Limites territoriais inválidos.")
    required = {
        "minLatitude": (-90, 90),
        "maxLatitude": (-90, 90),
        "minLongitude": (-180, 180),
        "maxLongitude": (-180, 180),
    }
    parsed = {
        key: _optional_coordinate(value.get(key), key, minimum, maximum)
        for key, (minimum, maximum) in required.items()
    }
    if any(item is None for item in parsed.values()):
        raise ValueError("Informe todos os limites territoriais.")
    if parsed["minLatitude"] >= parsed["maxLatitude"]:
        raise ValueError("Latitude mínima deve ser menor que a máxima.")
    if parsed["minLongitude"] >= parsed["maxLongitude"]:
        raise ValueError("Longitude mínima deve ser menor que a máxima.")
    return parsed


def _fetch_ibge_geojson(scope: str, code: str) -> dict:
    url = IBGE_MALHAS_URL.format(scope=scope, code=code)
    try:
        with urllib.request.urlopen(url, timeout=20) as response:  # noqa: S310
            raw = response.read()
            if response.headers.get("Content-Encoding") == "gzip" or raw.startswith(b"\x1f\x8b"):
                raw = gzip.decompress(raw)
    except urllib.error.HTTPError as error:
        if error.code == 404:
            raise ValueError("CÃ³digo IBGE nÃ£o encontrado na malha territorial.") from error
        raise ValueError("NÃ£o foi possÃ­vel consultar a malha territorial no IBGE.") from error
    except urllib.error.URLError as error:
        raise ValueError("IBGE indisponÃ­vel no momento. Tente novamente mais tarde.") from error
    try:
        return _validate_geojson(json.loads(raw.decode("utf-8")))
    except json.JSONDecodeError as error:
        raise ValueError("IBGE retornou uma malha territorial invÃ¡lida.") from error


def _validate_geojson(value) -> dict | None:
    if value in (None, ""):
        return None
    if not isinstance(value, dict):
        raise ValueError("GeoJSON da jurisdiÃ§Ã£o invÃ¡lido.")
    if value.get("type") == "FeatureCollection":
        features = value.get("features")
        if not isinstance(features, list) or not features:
            raise ValueError("GeoJSON da jurisdiÃ§Ã£o nÃ£o possui feiÃ§Ãµes.")
        for feature in features:
            _validate_geojson_feature(feature)
        return value
    if value.get("type") == "Feature":
        _validate_geojson_feature(value)
        return {"type": "FeatureCollection", "features": [value]}
    raise ValueError("GeoJSON deve ser Feature ou FeatureCollection.")


def _validate_geojson_feature(feature: dict) -> None:
    if not isinstance(feature, dict) or feature.get("type") != "Feature":
        raise ValueError("FeiÃ§Ã£o GeoJSON invÃ¡lida.")
    geometry = feature.get("geometry") or {}
    if geometry.get("type") not in {"Polygon", "MultiPolygon"}:
        raise ValueError("A jurisdiÃ§Ã£o deve ser Polygon ou MultiPolygon.")
    coordinates = list(_iter_geojson_coordinates(geometry))
    if len(coordinates) < 3:
        raise ValueError("PolÃ­gono da jurisdiÃ§Ã£o nÃ£o possui coordenadas suficientes.")


def _geojson_bounds_and_center(geojson: dict) -> tuple[dict, dict]:
    coordinates = [
        coordinate
        for feature in geojson.get("features", [])
        for coordinate in _iter_geojson_coordinates(feature.get("geometry") or {})
    ]
    if not coordinates:
        raise ValueError("GeoJSON da jurisdiÃ§Ã£o nÃ£o possui coordenadas.")
    longitudes = [item[0] for item in coordinates]
    latitudes = [item[1] for item in coordinates]
    bounds = {
        "minLatitude": min(latitudes),
        "maxLatitude": max(latitudes),
        "minLongitude": min(longitudes),
        "maxLongitude": max(longitudes),
    }
    center = {
        "latitude": (bounds["minLatitude"] + bounds["maxLatitude"]) / 2,
        "longitude": (bounds["minLongitude"] + bounds["maxLongitude"]) / 2,
    }
    return bounds, center


def _iter_geojson_coordinates(geometry: dict):
    geometry_type = geometry.get("type")
    coordinates = geometry.get("coordinates")
    if geometry_type == "Polygon":
        polygons = [coordinates]
    elif geometry_type == "MultiPolygon":
        polygons = coordinates
    else:
        return
    if not isinstance(polygons, list):
        return
    for polygon in polygons:
        if not isinstance(polygon, list):
            continue
        for ring in polygon:
            if not isinstance(ring, list):
                continue
            for coordinate in ring:
                if (
                    isinstance(coordinate, list | tuple)
                    and len(coordinate) >= 2
                    and isinstance(coordinate[0], int | float)
                    and isinstance(coordinate[1], int | float)
                ):
                    yield (float(coordinate[0]), float(coordinate[1]))


def _default_jurisdiction_name(
    chamber_type: str, city: str | None, state: str | None
) -> str | None:
    if chamber_type == "CAMARA_MUNICIPAL" and city and state:
        return f"{city}/{state}"
    if chamber_type == "ASSEMBLEIA_LEGISLATIVA" and state:
        return state
    return None


@admin_bp.get("/categorias")
@roles_required("admin", "manager", "staff", "representative")
def list_categories():
    tenant_id, _ = _context()
    if ensure_default_request_categories(tenant_id):
        db.session.commit()
    items = db.session.execute(
        select(RequestCategory)
        .where(RequestCategory.tenant_id == tenant_id)
        .order_by(RequestCategory.name)
    ).scalars()
    return jsonify(content=[_serialize(item) for item in items])


@admin_bp.post("/categorias")
@roles_required("admin")
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
@roles_required("admin")
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
@roles_required("admin", "manager", "staff", "representative")
def list_territories():
    tenant_id, _ = _context()
    items = db.session.execute(
        select(Territory).where(Territory.tenant_id == tenant_id).order_by(Territory.name)
    ).scalars()
    return jsonify(content=[_simple_data(item) for item in items])


@admin_bp.post("/territorios/recarregar-sugestoes")
@roles_required("admin")
def reload_territory_suggestions():
    tenant_id, user_id = _context()
    tenant = db.session.get(Tenant, tenant_id)
    before = [
        _simple_data(item)
        for item in db.session.execute(
            select(Territory).where(Territory.tenant_id == tenant_id).order_by(Territory.name)
        ).scalars()
    ]
    items, suggestions = reload_suggested_territories(tenant)
    after = [_simple_data(item) for item in items]
    add_audit(
        tenant_id,
        user_id,
        "territory.suggestions.reloaded",
        "territory",
        tenant_id,
        before,
        {"territorios": after, "sugestoes": suggestions},
    )
    db.session.commit()
    return jsonify(content=after, sugestoes=suggestions)


@admin_bp.post("/territorios")
@roles_required("admin")
def create_territory():
    tenant_id, user_id = _context()
    name = str((request.get_json(silent=True) or {}).get("nome", "")).strip()
    if len(name) < 2:
        return jsonify(error="validation_error", message="Informe o nome do território."), 422
    exists = db.session.execute(
        select(Territory.id).where(Territory.tenant_id == tenant_id, Territory.name == name)
    ).scalar_one_or_none()
    if exists:
        return jsonify(error="conflict", message="Território ja cadastrado no gabinete."), 409
    item = Territory(tenant_id=tenant_id, name=name)
    db.session.add(item)
    db.session.flush()
    add_audit(
        tenant_id, user_id, "territory.created", "territory", item.id, after=_simple_data(item)
    )
    db.session.commit()
    return jsonify(_simple_data(item)), 201


@admin_bp.patch("/territorios/<uuid:territory_id>")
@roles_required("admin")
def update_territory(territory_id: uuid.UUID):
    tenant_id, user_id = _context()
    item = db.session.execute(
        select(Territory).where(Territory.id == territory_id, Territory.tenant_id == tenant_id)
    ).scalar_one_or_none()
    if item is None:
        return jsonify(error="resource_not_found", message="Território não encontrado."), 404
    payload = request.get_json(silent=True) or {}
    before = _simple_data(item)
    if "nome" in payload:
        name = str(payload["nome"]).strip()
        if len(name) < 2:
            return jsonify(error="validation_error", message="Informe o nome do território."), 422
        exists = db.session.execute(
            select(Territory.id).where(
                Territory.tenant_id == tenant_id,
                Territory.name == name,
                Territory.id != item.id,
            )
        ).scalar_one_or_none()
        if exists:
            return jsonify(error="conflict", message="Território ja cadastrado no gabinete."), 409
        item.name = name
    if "ativa" in payload:
        item.active = bool(payload["ativa"])
    after = _simple_data(item)
    add_audit(tenant_id, user_id, "territory.updated", "territory", item.id, before, after)
    db.session.commit()
    return jsonify(after)


@admin_bp.delete("/territorios/<uuid:territory_id>")
@roles_required("admin")
def delete_territory(territory_id: uuid.UUID):
    tenant_id, user_id = _context()
    item = db.session.execute(
        select(Territory).where(Territory.id == territory_id, Territory.tenant_id == tenant_id)
    ).scalar_one_or_none()
    if item is None:
        return jsonify(error="resource_not_found", message="Território não encontrado."), 404
    before = _simple_data(item)
    item.active = False
    after = _simple_data(item)
    add_audit(tenant_id, user_id, "territory.deleted", "territory", item.id, before, after)
    db.session.commit()
    return jsonify(after)


@admin_bp.get("/orgaos")
@roles_required("admin", "manager", "staff", "representative")
def list_agencies():
    tenant_id, _ = _context()
    items = db.session.execute(
        select(ExternalAgency)
        .where(ExternalAgency.tenant_id == tenant_id)
        .order_by(ExternalAgency.name)
    ).scalars()
    return jsonify(content=[_simple_data(item) for item in items])


@admin_bp.post("/orgaos/recarregar-sugestoes")
@roles_required("admin")
def reload_agency_suggestions():
    tenant_id, user_id = _context()
    tenant = db.session.get(Tenant, tenant_id)
    before = [
        _simple_data(item)
        for item in db.session.execute(
            select(ExternalAgency)
            .where(ExternalAgency.tenant_id == tenant_id)
            .order_by(ExternalAgency.name)
        ).scalars()
    ]
    items, suggestions = reload_suggested_agencies(tenant)
    after = [_simple_data(item) for item in items]
    add_audit(
        tenant_id,
        user_id,
        "agency.suggestions.reloaded",
        "external_agency",
        tenant_id,
        before,
        {"orgaos": after, "sugestoes": suggestions},
    )
    db.session.commit()
    return jsonify(content=after, sugestoes=suggestions)


@admin_bp.post("/orgaos")
@roles_required("admin")
def create_agency():
    tenant_id, user_id = _context()
    payload = request.get_json(silent=True) or {}
    name = str(payload.get("nome", "")).strip()
    email = str(payload.get("emailContato", "")).strip() or None
    responsible = str(payload.get("responsavel", "")).strip() or None
    phone = str(payload.get("telefone", "")).strip() or None
    if len(name) < 2:
        return jsonify(error="validation_error", message="Informe o nome do órgão."), 422
    if email and not EMAIL_RE.match(email):
        return (
            jsonify(error="validation_error", message="Informe um e-mail de contato valido."),
            422,
        )
    if phone and not BR_PHONE_RE.match(phone):
        return jsonify(error="validation_error", message="Informe um telefone valido com DDD."), 422
    exists = db.session.execute(
        select(ExternalAgency.id).where(
            ExternalAgency.tenant_id == tenant_id, ExternalAgency.name == name
        )
    ).scalar_one_or_none()
    if exists:
        return jsonify(error="conflict", message="Órgão ja cadastrado no gabinete."), 409
    item = ExternalAgency(
        tenant_id=tenant_id,
        name=name,
        contact_email=email,
        responsible=responsible,
        phone=_phone_digits(phone) or None,
        source="Manual",
    )
    db.session.add(item)
    db.session.flush()
    add_audit(
        tenant_id, user_id, "agency.created", "external_agency", item.id, after=_simple_data(item)
    )
    db.session.commit()
    return jsonify(_simple_data(item)), 201


@admin_bp.patch("/orgaos/<uuid:agency_id>")
@roles_required("admin")
def update_agency(agency_id: uuid.UUID):
    tenant_id, user_id = _context()
    item = db.session.execute(
        select(ExternalAgency).where(
            ExternalAgency.id == agency_id, ExternalAgency.tenant_id == tenant_id
        )
    ).scalar_one_or_none()
    if item is None:
        return jsonify(error="resource_not_found", message="Órgão não encontrado."), 404
    payload = request.get_json(silent=True) or {}
    before = _simple_data(item)
    if "nome" in payload:
        name = str(payload["nome"]).strip()
        if len(name) < 2:
            return jsonify(error="validation_error", message="Informe o nome do órgão."), 422
        exists = db.session.execute(
            select(ExternalAgency.id).where(
                ExternalAgency.tenant_id == tenant_id,
                ExternalAgency.name == name,
                ExternalAgency.id != item.id,
            )
        ).scalar_one_or_none()
        if exists:
            return jsonify(error="conflict", message="Órgão ja cadastrado no gabinete."), 409
        item.name = name
    if "emailContato" in payload:
        email = str(payload["emailContato"]).strip() or None
        if email and not EMAIL_RE.match(email):
            return (
                jsonify(error="validation_error", message="Informe um e-mail de contato valido."),
                422,
            )
        item.contact_email = email
    if "responsavel" in payload:
        item.responsible = str(payload["responsavel"]).strip() or None
    if "telefone" in payload:
        phone = str(payload["telefone"]).strip()
        if phone and not BR_PHONE_RE.match(phone):
            return jsonify(error="validation_error", message="Informe um telefone valido com DDD."), 422
        item.phone = _phone_digits(phone) or None
    if "ativa" in payload:
        item.active = bool(payload["ativa"])
    after = _simple_data(item)
    add_audit(tenant_id, user_id, "agency.updated", "external_agency", item.id, before, after)
    db.session.commit()
    return jsonify(after)


@admin_bp.delete("/orgaos/<uuid:agency_id>")
@roles_required("admin")
def delete_agency(agency_id: uuid.UUID):
    tenant_id, user_id = _context()
    item = db.session.execute(
        select(ExternalAgency).where(
            ExternalAgency.id == agency_id, ExternalAgency.tenant_id == tenant_id
        )
    ).scalar_one_or_none()
    if item is None:
        return jsonify(error="resource_not_found", message="Órgão não encontrado."), 404
    before = _simple_data(item)
    item.active = False
    after = _simple_data(item)
    add_audit(tenant_id, user_id, "agency.deleted", "external_agency", item.id, before, after)
    db.session.commit()
    return jsonify(after)
