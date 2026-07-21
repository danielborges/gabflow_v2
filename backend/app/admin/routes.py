import gzip
import json
import urllib.error
import urllib.request
import uuid

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt, get_jwt_identity
from sqlalchemy import func, select

from app.audit import add_audit
from app.auth.permissions import roles_required
from app.auth.security import hash_password
from app.extensions import db
from app.models import (
    AuditLog,
    ExternalAgency,
    IntegrationSetting,
    IntegrationStatus,
    IntegrationType,
    RequestCategory,
    Role,
    Tenant,
    Territory,
    User,
    UserStatus,
)

admin_bp = Blueprint("admin", __name__)

CHAMBER_TYPES = {"CAMARA_MUNICIPAL", "ASSEMBLEIA_LEGISLATIVA"}
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
    return {
        "vereador": item.representative_info or {},
        "mandato": item.mandate_info or {},
        "identidadeVisual": item.visual_identity or {},
        "chefeGabineteId": str(item.chief_of_staff_id) if item.chief_of_staff_id else None,
    }


def _user_data(item: User) -> dict:
    return {
        "id": str(item.id),
        "nome": item.name,
        "email": item.email,
        "perfil": item.role.value,
        "status": item.status.value,
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


@admin_bp.get("/perfil-gabinete")
@roles_required("admin")
def get_office_profile():
    tenant_id, _ = _context()
    tenant = db.session.get(Tenant, tenant_id)
    return jsonify(_office_profile_data(tenant))


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
        tenant.visual_identity = _clean_dict(
            payload.get("identidadeVisual"), tenant.visual_identity
        )
    except ValueError as error:
        return jsonify(error="validation_error", message=str(error)), 422
    chief_id = payload.get("chefeGabineteId", tenant.chief_of_staff_id)
    if chief_id in ("", None):
        tenant.chief_of_staff_id = None
    else:
        chief = _tenant_user(tenant_id, chief_id)
        if chief is None:
            return jsonify(error="validation_error", message="Chefe de gabinete invalido."), 422
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
    password = str(payload.get("senha", "")).strip()
    try:
        role = Role(str(payload.get("perfil", "staff")).lower())
    except ValueError:
        return jsonify(error="validation_error", message="Perfil invalido."), 422
    if role == Role.PLATFORM_ADMIN:
        return jsonify(error="validation_error", message="Perfil invalido para gabinete."), 422
    if len(name) < 2 or not email or len(password) < 8:
        return (
            jsonify(error="validation_error", message="Informe nome, e-mail e senha segura."),
            422,
        )
    active_users = db.session.scalar(
        select(func.count(User.id)).where(
            User.tenant_id == tenant_id,
            User.status == UserStatus.ACTIVE,
        )
    )
    if active_users >= tenant.user_limit:
        return jsonify(error="user_limit_reached", message="Limite de usuarios atingido."), 422
    exists = db.session.execute(
        select(User.id).where(User.tenant_id == tenant_id, User.email == email)
    ).scalar_one_or_none()
    if exists:
        return jsonify(error="conflict", message="E-mail ja cadastrado no gabinete."), 409
    item = User(
        tenant_id=tenant_id,
        name=name,
        email=email,
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
    if "perfil" in payload:
        try:
            role = Role(str(payload["perfil"]).lower())
        except ValueError:
            return jsonify(error="validation_error", message="Perfil invalido."), 422
        if role == Role.PLATFORM_ADMIN:
            return jsonify(error="validation_error", message="Perfil invalido para gabinete."), 422
        item.role = role
    if "status" in payload:
        try:
            item.status = UserStatus(str(payload["status"]).lower())
        except ValueError:
            return jsonify(error="validation_error", message="Status invalido."), 422
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
    items = db.session.execute(
        select(AuditLog)
        .where(AuditLog.tenant_id == tenant_id)
        .order_by(AuditLog.created_at.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
    ).scalars()
    total_pages = max(1, (total + per_page - 1) // per_page)
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
        ],
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
    tenant_id, user_id = _context()
    tenant = db.session.get(Tenant, tenant_id)
    payload = request.get_json(silent=True) or {}
    before = _jurisdiction_data(tenant)

    chamber_type = str(payload.get("tipoCasa", tenant.chamber_type or "")).strip().upper()
    if chamber_type and chamber_type not in CHAMBER_TYPES:
        return jsonify(error="validation_error", message="Tipo de casa legislativa inválido."), 422

    state = str(payload.get("uf", tenant.jurisdiction_state or "")).strip().upper() or None
    if state and (len(state) != 2 or not state.isalpha()):
        return jsonify(error="validation_error", message="UF deve conter 2 letras."), 422

    city = str(payload.get("municipio", tenant.jurisdiction_city or "")).strip() or None
    name = str(payload.get("nome", tenant.jurisdiction_name or "")).strip() or None
    ibge_code = str(payload.get("codigoIbge", tenant.jurisdiction_ibge_code or "")).strip() or None
    center = payload.get("centro") or {}
    bounds = payload.get("limites")
    geojson = payload.get("geojson", tenant.jurisdiction_geojson)
    try:
        latitude = _optional_coordinate(center.get("latitude"), "Latitude", -90, 90)
        longitude = _optional_coordinate(center.get("longitude"), "Longitude", -180, 180)
        bounds = _validate_bounds(bounds)
        geojson = _validate_geojson(geojson)
    except ValueError as error:
        return jsonify(error="validation_error", message=str(error)), 422

    tenant.chamber_type = chamber_type or None
    tenant.jurisdiction_state = state
    tenant.jurisdiction_city = city
    tenant.jurisdiction_name = name or _default_jurisdiction_name(chamber_type, city, state)
    tenant.jurisdiction_ibge_code = ibge_code
    tenant.jurisdiction_center_latitude = latitude
    tenant.jurisdiction_center_longitude = longitude
    tenant.jurisdiction_bounds = bounds
    tenant.jurisdiction_geojson = geojson

    after = _jurisdiction_data(tenant)
    add_audit(
        tenant_id,
        user_id,
        "tenant.jurisdiction.updated",
        "tenant",
        tenant.id,
        before,
        after,
    )
    db.session.commit()
    return jsonify(after)


@admin_bp.post("/jurisdicao/ibge")
@roles_required("admin")
def import_ibge_jurisdiction():
    tenant_id, user_id = _context()
    tenant = db.session.get(Tenant, tenant_id)
    payload = request.get_json(silent=True) or {}
    before = _jurisdiction_data(tenant)
    chamber_type = str(payload.get("tipoCasa", tenant.chamber_type or "")).strip().upper()
    if chamber_type and chamber_type not in CHAMBER_TYPES:
        return jsonify(error="validation_error", message="Tipo de casa legislativa invÃ¡lido."), 422
    ibge_code = str(payload.get("codigoIbge", tenant.jurisdiction_ibge_code or "")).strip()
    if not ibge_code.isdigit():
        return jsonify(error="validation_error", message="Informe um cÃ³digo IBGE numÃ©rico."), 422

    scope = "estados" if chamber_type == "ASSEMBLEIA_LEGISLATIVA" else "municipios"
    try:
        geojson = _fetch_ibge_geojson(scope, ibge_code)
        bounds, center = _geojson_bounds_and_center(geojson)
    except ValueError as error:
        return jsonify(error="validation_error", message=str(error)), 422

    tenant.chamber_type = chamber_type or tenant.chamber_type
    tenant.jurisdiction_ibge_code = ibge_code
    tenant.jurisdiction_geojson = geojson
    tenant.jurisdiction_bounds = bounds
    tenant.jurisdiction_center_latitude = center["latitude"]
    tenant.jurisdiction_center_longitude = center["longitude"]
    if payload.get("nome"):
        tenant.jurisdiction_name = str(payload["nome"]).strip()
    elif tenant.jurisdiction_name is None:
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


def _tenant_user(tenant_id: uuid.UUID, value) -> User | None:
    try:
        user_id = uuid.UUID(str(value))
    except (TypeError, ValueError):
        return None
    return db.session.execute(
        select(User).where(User.id == user_id, User.tenant_id == tenant_id)
    ).scalar_one_or_none()


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


@admin_bp.post("/territorios")
@roles_required("admin")
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
@roles_required("admin", "manager", "staff", "representative")
def list_agencies():
    tenant_id, _ = _context()
    items = db.session.execute(
        select(ExternalAgency)
        .where(ExternalAgency.tenant_id == tenant_id)
        .order_by(ExternalAgency.name)
    ).scalars()
    return jsonify(content=[_simple_data(item) for item in items])


@admin_bp.post("/orgaos")
@roles_required("admin")
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
