import uuid
from datetime import UTC, datetime, timedelta
from unicodedata import combining, normalize

from flask import Blueprint, Response, current_app, jsonify, request
from flask_jwt_extended import get_jwt, get_jwt_identity, jwt_required
from sqlalchemy import and_, or_, select
from sqlalchemy.exc import IntegrityError

from app.audit import add_audit
from app.auth.permissions import roles_required
from app.directory.addresses import CitizenAddressError, resolve_address
from app.directory.history import add_citizen_history, changed_field_names
from app.directory.identity import (
    cpf_fingerprint,
    decrypt_document,
    encrypt_document,
    normalize_cpf,
    normalize_electoral_title,
    parse_birth_date,
    valid_cpf,
)
from app.directory.pagination import (
    CursorError,
    cursor_datetime,
    decode_cursor,
    encode_cursor,
    page_limit,
)
from app.directory.photos import (
    CitizenPhotoError,
    delete_citizen_photo,
    read_citizen_photo,
    store_citizen_photo,
)
from app.extensions import db
from app.models import (
    AuditLog,
    ChannelIdentityReview,
    ChannelIdentityReviewStatus,
    Citizen,
    CitizenHistory,
    CitizenOrganizationLink,
    ContactAttempt,
    Organization,
    RequestInteraction,
    ServiceRequest,
    User,
    UserStatus,
)
from app.privacy.service import record_consent

directory_bp = Blueprint("directory", __name__)


def _context() -> tuple[uuid.UUID, uuid.UUID]:
    return uuid.UUID(get_jwt()["tenant_id"]), uuid.UUID(get_jwt_identity())


def _etag_response(payload: dict, item: Citizen, status: int = 200):
    response = jsonify(payload)
    response.set_etag(str(item.version))
    return response, status


def _require_current_version(item: Citizen):
    if not request.headers.get("If-Match"):
        return (
            jsonify(
                error="precondition_required",
                code="VERSAO_OBRIGATORIA",
                message="Recarregue o cadastro antes de salvar.",
                versaoAtual=item.version,
            ),
            428,
        )
    if not request.if_match.contains(str(item.version)):
        return (
            jsonify(
                error="precondition_failed",
                code="CADASTRO_DESATUALIZADO",
                message="Este cadastro foi alterado por outro usuário. Recarregue para continuar.",
                versaoAtual=item.version,
            ),
            412,
        )
    return None


def _validate_collection(value, field: str) -> list:
    if value is None:
        return []
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise ValueError(f"{field} deve ser uma lista de objetos.")
    return value


def _resolved_addresses(tenant_id: uuid.UUID, payload: dict, current: list | None = None) -> list:
    if "endereco" not in payload:
        return _validate_collection(payload.get("enderecos"), "Endereços")
    address = payload.get("endereco")
    if address in (None, ""):
        return list(current or [])[1:]
    resolved = resolve_address(tenant_id, address)
    existing = list(current or [])
    return [resolved, *existing[1:]]


def _citizen_data(
    item: Citizen, include_history: bool = False, include_sensitive: bool = False
) -> dict:
    data = {
        "id": str(item.id),
        "nome": item.name,
        "nomeSocial": item.social_name,
        "profissao": item.profession,
        "dataNascimento": item.birth_date.isoformat() if item.birth_date else None,
        "cpfFinal": item.cpf_final,
        "vip": item.vip,
        "contatos": item.contacts,
        "enderecos": item.addresses,
        "fotoUrl": f"/api/v1/cidadaos/{item.id}/foto" if item.photo_storage_key else None,
        "canalPreferencial": item.preferred_channel,
        "consentimentoContato": item.contact_consent,
        "consentimentoDivulgacao": item.publication_consent,
        "baseLegal": item.legal_basis,
        "flagsPrivacidade": item.privacy_flags,
        "observacoes": item.notes,
        "anonimizadoEm": item.anonymized_at.isoformat() if item.anonymized_at else None,
        "criadoEm": item.created_at.isoformat(),
        "atualizadoEm": item.updated_at.isoformat(),
        "cadastradoPor": item.created_by.name if item.created_by else None,
        "versao": item.version,
        "organizacoes": [
            {
                "id": str(link.organization.id),
                "nome": link.organization.name,
                "tipo": link.organization.organization_type,
                "papel": link.role,
            }
            for link in item.organization_links
        ],
    }
    if include_sensitive:
        data["cpf"] = decrypt_document(item.tenant_id, "cpf", item.cpf_ciphertext)
        data["tituloEleitor"] = decrypt_document(
            item.tenant_id, "electoral-title", item.electoral_title_ciphertext
        )
    if include_history:
        request_rows = (
            db.session.execute(
                select(ServiceRequest)
                .where(
                    ServiceRequest.tenant_id == item.tenant_id,
                    ServiceRequest.citizen_id == item.id,
                )
                .order_by(ServiceRequest.created_at.desc(), ServiceRequest.id.desc())
                .limit(21)
            )
            .scalars()
            .all()
        )
        requests = request_rows[:20]
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
        data["solicitacoesProximoCursor"] = (
            encode_cursor(
                "citizen-requests",
                created_at=requests[-1].created_at.isoformat(),
                id=str(requests[-1].id),
            )
            if len(request_rows) > 20
            else None
        )
        last_contact_at, attended_by = _citizen_service_metadata(item)
        data["ultimoContatoEm"] = last_contact_at.isoformat() if last_contact_at else None
        data["atendidoPor"] = attended_by
    return data


def _citizen_service_metadata(item: Citizen) -> tuple[datetime | None, str | None]:
    attempt = db.session.execute(
        select(ContactAttempt.attempted_at, User.name)
        .join(User, User.id == ContactAttempt.created_by_id)
        .where(
            ContactAttempt.tenant_id == item.tenant_id,
            ContactAttempt.citizen_id == item.id,
        )
        .order_by(ContactAttempt.attempted_at.desc())
        .limit(1)
    ).first()
    interaction = db.session.execute(
        select(RequestInteraction.created_at, User.name)
        .join(ServiceRequest, ServiceRequest.id == RequestInteraction.request_id)
        .join(User, User.id == RequestInteraction.author_id)
        .where(
            RequestInteraction.tenant_id == item.tenant_id,
            ServiceRequest.citizen_id == item.id,
        )
        .order_by(RequestInteraction.created_at.desc())
        .limit(1)
    ).first()
    contacts = [contact for contact in (attempt, interaction) if contact]
    if contacts:
        latest = max(contacts, key=lambda contact: contact[0])
        return latest[0], latest[1]
    responsible = db.session.execute(
        select(User.name)
        .join(ServiceRequest, ServiceRequest.responsible_id == User.id)
        .where(
            ServiceRequest.tenant_id == item.tenant_id,
            ServiceRequest.citizen_id == item.id,
        )
        .order_by(ServiceRequest.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()
    return None, responsible


def _audit_snapshot(item: Citizen) -> dict:
    return {
        "nome": item.name,
        "nomeSocial": item.social_name,
        "profissao": item.profession,
        "dataNascimento": item.birth_date.isoformat() if item.birth_date else None,
        "canalPreferencial": item.preferred_channel,
        "baseLegal": item.legal_basis,
        "consentimentoContato": item.contact_consent,
        "consentimentoDivulgacao": item.publication_consent,
        "vip": item.vip,
        "possuiCpf": bool(item.cpf_fingerprint),
        "possuiTituloEleitor": bool(item.electoral_title_ciphertext),
        "organizacaoIds": sorted(str(link.organization_id) for link in item.organization_links),
    }


def _normalized_name(value: object) -> str:
    text = " ".join(str(value or "").strip().lower().split())
    return "".join(character for character in normalize("NFKD", text) if not combining(character))


def _available_citizen_letters(tenant_id: uuid.UUID) -> list[str]:
    names = db.session.execute(
        select(Citizen.name, Citizen.social_name).where(
            Citizen.tenant_id == tenant_id,
            Citizen.anonymized_at.is_(None),
        )
    )
    return sorted(
        {
            normalized[:1].upper()
            for name, social_name in names
            if (normalized := _normalized_name(social_name or name))[:1].isalpha()
            and normalized[:1].isascii()
        }
    )


def _letter_prefixes(letter: str) -> tuple[str, ...]:
    return {
        "A": ("A", "Á", "À", "Â", "Ã", "Ä"),
        "C": ("C", "Ç"),
        "E": ("E", "É", "È", "Ê", "Ë"),
        "I": ("I", "Í", "Ì", "Î", "Ï"),
        "O": ("O", "Ó", "Ò", "Ô", "Õ", "Ö"),
        "U": ("U", "Ú", "Ù", "Û", "Ü"),
    }.get(letter, (letter,))


def _existing_citizen_for_cpf(
    tenant_id: uuid.UUID, cpf: str, *, ignore_id: uuid.UUID | None = None
) -> Citizen | None:
    filters = [
        Citizen.tenant_id == tenant_id,
        Citizen.cpf_fingerprint == cpf_fingerprint(tenant_id, cpf),
        Citizen.anonymized_at.is_(None),
    ]
    if ignore_id:
        filters.append(Citizen.id != ignore_id)
    return db.session.execute(select(Citizen).where(*filters)).scalar_one_or_none()


def _cpf_conflict(item: Citizen):
    return (
        jsonify(
            error="conflict",
            code="CPF_DUPLICADO",
            message=f"CPF já cadastrado para {item.social_name or item.name}.",
            cidadao={
                "id": str(item.id),
                "nome": item.name,
                "nomeSocial": item.social_name,
                "cpfFinal": item.cpf_final,
            },
        ),
        409,
    )


def _apply_documents(item: Citizen, tenant_id: uuid.UUID, payload: dict) -> None:
    if "cpf" in payload:
        cpf = normalize_cpf(payload.get("cpf"))
        if cpf and not valid_cpf(cpf):
            raise ValueError("Informe um CPF válido.")
        item.cpf_ciphertext = encrypt_document(tenant_id, "cpf", cpf)
        item.cpf_fingerprint = cpf_fingerprint(tenant_id, cpf) if cpf else None
        item.cpf_final = cpf[-2:] if cpf else None
        item.cpf_key_version = (
            int(current_app.config["CITIZEN_IDENTITY_HMAC_KEY_VERSION"]) if cpf else None
        )
    if "tituloEleitor" in payload:
        title = normalize_electoral_title(payload.get("tituloEleitor"))
        item.electoral_title_ciphertext = encrypt_document(tenant_id, "electoral-title", title)


def _organization_ids(payload: dict) -> list[uuid.UUID] | None:
    if "organizacaoIds" not in payload:
        return None
    values = payload.get("organizacaoIds")
    if not isinstance(values, list):
        raise ValueError("Organizações deve ser uma lista de identificadores.")
    try:
        return list(dict.fromkeys(uuid.UUID(str(value)) for value in values))
    except (TypeError, ValueError, AttributeError) as error:
        raise ValueError("Informe organizações válidas.") from error


def _sync_organizations(
    item: Citizen, tenant_id: uuid.UUID, user_id: uuid.UUID, organization_ids: list[uuid.UUID]
) -> None:
    organizations = list(
        db.session.execute(
            select(Organization).where(
                Organization.tenant_id == tenant_id,
                Organization.id.in_(organization_ids),
            )
        ).scalars()
    )
    if len(organizations) != len(organization_ids):
        raise ValueError("Uma ou mais organizações não foram encontradas.")
    existing = {link.organization_id: link for link in item.organization_links}
    requested = set(organization_ids)
    for organization_id, link in existing.items():
        if organization_id not in requested:
            item.organization_links.remove(link)
    for organization in organizations:
        if organization.id not in existing:
            item.organization_links.append(
                CitizenOrganizationLink(
                    tenant_id=tenant_id,
                    organization_id=organization.id,
                    role="RESPONSAVEL",
                    created_by_id=user_id,
                )
            )


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
    letter = str(request.args.get("letra", "")).strip().upper()
    vip = str(request.args.get("vip", "")).strip().lower()
    if letter and (len(letter) != 1 or letter not in "ABCDEFGHIJKLMNOPQRSTUVWXYZ#"):
        return jsonify(error="validation_error", message="Letra da agenda inválida."), 422
    try:
        limit = page_limit(request.args.get("limite"), default=30)
        cursor = decode_cursor(request.args.get("cursor"), "citizen-agenda")
        if cursor and (
            cursor.get("query") != query.casefold()
            or cursor.get("letter", "") != letter
            or cursor.get("vip", "") != vip
        ):
            raise CursorError("Cursor não pertence a esta pesquisa.")
    except CursorError as error:
        return jsonify(error="validation_error", message=str(error)), 422
    filters = [Citizen.tenant_id == tenant_id, Citizen.anonymized_at.is_(None)]
    if query:
        pattern = f"%{query}%"
        filters.append(or_(Citizen.name.ilike(pattern), Citizen.social_name.ilike(pattern)))
    if letter and letter != "#":
        prefixes = _letter_prefixes(letter)
        social_name_filter = or_(
            *(Citizen.social_name.ilike(f"{prefix}%") for prefix in prefixes)
        )
        civil_name_filter = or_(*(Citizen.name.ilike(f"{prefix}%") for prefix in prefixes))
        filters.append(
            or_(
                and_(
                    Citizen.social_name.is_not(None),
                    Citizen.social_name != "",
                    social_name_filter,
                ),
                and_(
                    or_(Citizen.social_name.is_(None), Citizen.social_name == ""),
                    civil_name_filter,
                ),
            )
        )
    if vip in {"true", "1"}:
        filters.append(Citizen.vip.is_(True))
    elif vip in {"false", "0"}:
        filters.append(Citizen.vip.is_(False))
    if cursor:
        try:
            cursor_id = uuid.UUID(str(cursor["id"]))
            cursor_name = str(cursor["name"])
        except (KeyError, ValueError):
            return jsonify(error="validation_error", message="Cursor de paginação inválido."), 422
        filters.append(
            or_(
                Citizen.name > cursor_name,
                and_(Citizen.name == cursor_name, Citizen.id > cursor_id),
            )
        )
    rows = (
        db.session.execute(
            select(Citizen).where(*filters).order_by(Citizen.name, Citizen.id).limit(limit + 1)
        )
        .scalars()
        .all()
    )
    has_more = len(rows) > limit
    items = rows[:limit]
    next_cursor = (
        encode_cursor(
            "citizen-agenda",
            name=items[-1].name,
            id=str(items[-1].id),
            query=query.casefold(),
            letter=letter,
            vip=vip,
        )
        if has_more and items
        else None
    )
    return jsonify(
        content=[_citizen_data(item) for item in items],
        proximoCursor=next_cursor,
        letrasDisponiveis=_available_citizen_letters(tenant_id),
        limite=limit,
    )


@directory_bp.post("/cidadaos/busca-segura")
@jwt_required()
def secure_search_citizens():
    tenant_id, _ = _context()
    payload = request.get_json(silent=True) or {}
    filters = [Citizen.tenant_id == tenant_id, Citizen.anonymized_at.is_(None)]
    cpf = normalize_cpf(payload.get("cpf"))
    if cpf:
        if not valid_cpf(cpf):
            return jsonify(error="validation_error", message="Informe um CPF válido."), 422
        filters.append(Citizen.cpf_fingerprint == cpf_fingerprint(tenant_id, cpf))
    else:
        value = (
            str(payload.get("contato") or payload.get("telefone") or payload.get("email") or "")
            .strip()
            .lower()
        )
        if len(value) < 3:
            return (
                jsonify(
                    error="validation_error",
                    message="Informe CPF ou ao menos três caracteres do contato.",
                ),
                422,
            )
        candidates = db.session.execute(select(Citizen).where(*filters)).scalars()
        matches = [
            item
            for item in candidates
            if any(value in str(contact.get("valor", "")).lower() for contact in item.contacts)
        ][:20]
        return jsonify(content=[_citizen_data(item) for item in matches])
    items = db.session.execute(select(Citizen).where(*filters).limit(20)).scalars()
    return jsonify(content=[_citizen_data(item) for item in items])


@directory_bp.post("/cidadaos/verificar-duplicidade")
@jwt_required()
def check_citizen_duplicate():
    tenant_id, _ = _context()
    payload = request.get_json(silent=True) or {}
    name = str(payload.get("nome", "")).strip()
    if len(name) < 2:
        return jsonify(error="validation_error", message="Informe o nome do cidadão."), 422
    ignore_id = None
    if payload.get("ignorarCidadaoId"):
        try:
            ignore_id = uuid.UUID(str(payload["ignorarCidadaoId"]))
        except ValueError:
            return jsonify(error="validation_error", message="Cidadão inválido."), 422
    cpf = normalize_cpf(payload.get("cpf"))
    if cpf and not valid_cpf(cpf):
        return jsonify(error="validation_error", message="Informe um CPF válido."), 422
    cpf_duplicate = _existing_citizen_for_cpf(tenant_id, cpf, ignore_id=ignore_id) if cpf else None
    candidates = db.session.execute(
        select(Citizen).where(
            Citizen.tenant_id == tenant_id,
            Citizen.anonymized_at.is_(None),
            Citizen.id != ignore_id if ignore_id else Citizen.id.is_not(None),
        )
    ).scalars()
    names = {_normalized_name(name), _normalized_name(payload.get("nomeSocial"))} - {""}
    homonyms = [
        item
        for item in candidates
        if names & {_normalized_name(item.name), _normalized_name(item.social_name)}
    ][:10]
    return jsonify(
        cpfDuplicado=_citizen_data(cpf_duplicate) if cpf_duplicate else None,
        homonimos=[_citizen_data(item) for item in homonyms],
    )


@directory_bp.post("/cidadaos")
@jwt_required()
def create_citizen():
    tenant_id, user_id = _context()
    payload = request.get_json(silent=True) or {}
    assisted_review = None
    if payload.get("revisaoCanalId"):
        try:
            review_id = uuid.UUID(str(payload["revisaoCanalId"]))
        except (TypeError, ValueError):
            return jsonify(error="validation_error", message="Revisão de canal inválida."), 422
        assisted_review = db.session.execute(
            select(ChannelIdentityReview)
            .where(
                ChannelIdentityReview.id == review_id,
                ChannelIdentityReview.tenant_id == tenant_id,
            )
            .with_for_update()
        ).scalar_one_or_none()
        if assisted_review is None:
            return jsonify(error="resource_not_found", message="Revisão não encontrada."), 404
        if (
            assisted_review.status != ChannelIdentityReviewStatus.PENDENTE
            or assisted_review.decision_type != "CADASTRO_EM_PREPARACAO"
        ):
            return jsonify(error="validation_error", message="Revisão não está preparada."), 422
        confirmations = payload.get("confirmacoesCadastroAssistido")
        if not isinstance(confirmations, list) or not {
            "nome",
            "contato",
            "baseLegal",
        }.issubset(set(confirmations)):
            return (
                jsonify(
                    error="validation_error",
                    message="Confirme nome, contato e base legal antes de cadastrar.",
                ),
                422,
            )
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
        if assisted_review and not contacts:
            raise ValueError("Confirme ao menos um contato para o cadastro assistido.")
        addresses = _resolved_addresses(tenant_id, payload)
        privacy_flags = payload.get("flagsPrivacidade") or []
        if not isinstance(privacy_flags, list):
            raise ValueError("Flags de privacidade deve ser uma lista.")
        birth_date = parse_birth_date(payload.get("dataNascimento"))
        organization_ids = _organization_ids(payload) or []
        cpf = normalize_cpf(payload.get("cpf"))
        if cpf and not valid_cpf(cpf):
            raise ValueError("Informe um CPF válido.")
    except ValueError as error:
        return jsonify(error="validation_error", message=str(error)), 422

    if cpf:
        existing = _existing_citizen_for_cpf(tenant_id, cpf)
        if existing:
            return _cpf_conflict(existing)

    item = Citizen(
        tenant_id=tenant_id,
        name=name,
        social_name=str(payload.get("nomeSocial", "")).strip() or None,
        profession=str(payload.get("profissao", "")).strip() or None,
        birth_date=birth_date,
        vip=bool(payload.get("vip", False)),
        contacts=contacts,
        addresses=addresses,
        preferred_channel=str(payload.get("canalPreferencial", "")).strip() or None,
        contact_consent=bool(payload.get("consentimentoContato", False)),
        publication_consent=bool(payload.get("consentimentoDivulgacao", False)),
        legal_basis=legal_basis,
        privacy_flags=privacy_flags,
        notes=str(payload.get("observacoes", "")).strip() or None,
        created_by_id=user_id,
    )
    try:
        _apply_documents(item, tenant_id, payload)
    except ValueError as error:
        return jsonify(error="validation_error", message=str(error)), 422
    db.session.add(item)
    try:
        db.session.flush()
        _sync_organizations(item, tenant_id, user_id, organization_ids)
        db.session.flush()
    except IntegrityError:
        db.session.rollback()
        if cpf:
            existing = _existing_citizen_for_cpf(tenant_id, cpf)
            if existing:
                return _cpf_conflict(existing)
        raise
    except ValueError as error:
        db.session.rollback()
        return jsonify(error="validation_error", message=str(error)), 422
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
        after=_audit_snapshot(item),
    )
    add_citizen_history(
        tenant_id,
        item.id,
        user_id,
        "CADASTRO_CRIADO",
        changed_fields=list(_audit_snapshot(item)),
        metadata={
            "versao": item.version,
            **(
                {"revisaoCanalId": str(assisted_review.id), "origem": "CADASTRO_ASSISTIDO"}
                if assisted_review
                else {}
            ),
        },
    )
    if assisted_review:
        assisted_review.status = ChannelIdentityReviewStatus.VINCULADA
        assisted_review.selected_citizen_id = item.id
        assisted_review.reviewed_by_id = user_id
        assisted_review.reviewed_at = datetime.now(UTC)
        assisted_review.decision_type = "CADASTRO_MANUAL"
        add_audit(
            tenant_id,
            user_id,
            "channel.identity_review.registration_completed",
            "channel_identity_review",
            assisted_review.id,
            after={"cidadaoId": str(item.id), "mensagemId": str(assisted_review.message_id)},
        )
    db.session.commit()
    return _etag_response(_citizen_data(item, include_sensitive=True), item, 201)


@directory_bp.get("/cidadaos/<uuid:citizen_id>")
@jwt_required()
def get_citizen(citizen_id: uuid.UUID):
    tenant_id, _ = _context()
    item = db.session.execute(
        select(Citizen).where(Citizen.id == citizen_id, Citizen.tenant_id == tenant_id)
    ).scalar_one_or_none()
    if item is None:
        return jsonify(error="resource_not_found", message="Cidadão não encontrado."), 404
    return _etag_response(_citizen_data(item, include_history=True, include_sensitive=True), item)


@directory_bp.patch("/cidadaos/<uuid:citizen_id>")
@jwt_required()
def update_citizen(citizen_id: uuid.UUID):
    tenant_id, user_id = _context()
    item = db.session.execute(
        select(Citizen).where(Citizen.id == citizen_id, Citizen.tenant_id == tenant_id)
    ).scalar_one_or_none()
    if item is None:
        return jsonify(error="resource_not_found", message="Cidadão não encontrado."), 404
    precondition = _require_current_version(item)
    if precondition:
        return precondition
    payload = request.get_json(silent=True) or {}
    before = _audit_snapshot(item)
    if "nome" in payload and len(str(payload.get("nome", "")).strip()) < 2:
        return jsonify(error="validation_error", message="Informe o nome do cidadão."), 422
    cpf = normalize_cpf(payload.get("cpf")) if "cpf" in payload else None
    if "cpf" in payload:
        if cpf and not valid_cpf(cpf):
            return jsonify(error="validation_error", message="Informe um CPF válido."), 422
        existing = _existing_citizen_for_cpf(tenant_id, cpf, ignore_id=item.id) if cpf else None
        if existing:
            return _cpf_conflict(existing)
    mappings = {
        "nome": "name",
        "nomeSocial": "social_name",
        "profissao": "profession",
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
        if "enderecos" in payload or "endereco" in payload:
            item.addresses = _resolved_addresses(tenant_id, payload, item.addresses)
        if "flagsPrivacidade" in payload and not isinstance(payload["flagsPrivacidade"], list):
            raise ValueError("Flags de privacidade deve ser uma lista.")
        if "dataNascimento" in payload:
            item.birth_date = parse_birth_date(payload.get("dataNascimento"))
        organization_ids = _organization_ids(payload)
        _apply_documents(item, tenant_id, payload)
        if organization_ids is not None:
            _sync_organizations(item, tenant_id, user_id, organization_ids)
    except ValueError as error:
        return jsonify(error="validation_error", message=str(error)), 422
    if "vip" in payload:
        item.vip = bool(payload["vip"])
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
    item.version += 1
    after = _audit_snapshot(item)
    add_audit(tenant_id, user_id, "citizen.corrected", "citizen", item.id, before, after)
    fields = changed_field_names(before, after)
    add_citizen_history(
        tenant_id,
        item.id,
        user_id,
        "CADASTRO_ATUALIZADO",
        changed_fields=fields,
        metadata={"versao": item.version},
    )
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        if cpf:
            existing = _existing_citizen_for_cpf(tenant_id, cpf, ignore_id=item.id)
            if existing:
                return _cpf_conflict(existing)
        raise
    return _etag_response(_citizen_data(item, include_sensitive=True), item)


@directory_bp.get("/cidadaos/<uuid:citizen_id>/solicitacoes")
@jwt_required()
def list_citizen_requests(citizen_id: uuid.UUID):
    tenant_id, _ = _context()
    citizen = db.session.execute(
        select(Citizen.id).where(Citizen.id == citizen_id, Citizen.tenant_id == tenant_id)
    ).scalar_one_or_none()
    if citizen is None:
        return jsonify(error="resource_not_found", message="Cidadão não encontrado."), 404
    try:
        limit = page_limit(request.args.get("limite"), default=20)
        cursor = decode_cursor(request.args.get("cursor"), "citizen-requests")
    except CursorError as error:
        return jsonify(error="validation_error", message=str(error)), 422
    filters = [
        ServiceRequest.tenant_id == tenant_id,
        ServiceRequest.citizen_id == citizen_id,
    ]
    if cursor:
        try:
            created_at = cursor_datetime(cursor["created_at"])
            cursor_id = uuid.UUID(str(cursor["id"]))
        except (KeyError, ValueError, CursorError):
            return jsonify(error="validation_error", message="Cursor de paginação inválido."), 422
        filters.append(
            or_(
                ServiceRequest.created_at < created_at,
                and_(ServiceRequest.created_at == created_at, ServiceRequest.id < cursor_id),
            )
        )
    rows = (
        db.session.execute(
            select(ServiceRequest)
            .where(*filters)
            .order_by(ServiceRequest.created_at.desc(), ServiceRequest.id.desc())
            .limit(limit + 1)
        )
        .scalars()
        .all()
    )
    has_more = len(rows) > limit
    items = rows[:limit]
    next_cursor = (
        encode_cursor(
            "citizen-requests",
            created_at=items[-1].created_at.isoformat(),
            id=str(items[-1].id),
        )
        if has_more and items
        else None
    )
    return jsonify(
        content=[
            {
                "id": str(item.id),
                "protocolo": item.protocol,
                "titulo": item.title,
                "status": item.status.value,
                "criadaEm": item.created_at.isoformat(),
            }
            for item in items
        ],
        proximoCursor=next_cursor,
        limite=limit,
    )


@directory_bp.get("/cidadaos/<uuid:citizen_id>/historico")
@jwt_required()
def list_citizen_history(citizen_id: uuid.UUID):
    tenant_id, _ = _context()
    citizen = db.session.execute(
        select(Citizen.id).where(Citizen.id == citizen_id, Citizen.tenant_id == tenant_id)
    ).scalar_one_or_none()
    if citizen is None:
        return jsonify(error="resource_not_found", message="Cidadão não encontrado."), 404
    try:
        limit = page_limit(request.args.get("limite"), default=20)
        cursor = decode_cursor(request.args.get("cursor"), "citizen-history")
    except CursorError as error:
        return jsonify(error="validation_error", message=str(error)), 422
    filters = [
        CitizenHistory.tenant_id == tenant_id,
        CitizenHistory.citizen_id == citizen_id,
    ]
    if cursor:
        try:
            created_at = cursor_datetime(cursor["created_at"])
            cursor_id = uuid.UUID(str(cursor["id"]))
        except (KeyError, ValueError, CursorError):
            return jsonify(error="validation_error", message="Cursor de paginação inválido."), 422
        filters.append(
            or_(
                CitizenHistory.created_at < created_at,
                and_(CitizenHistory.created_at == created_at, CitizenHistory.id < cursor_id),
            )
        )
    rows = db.session.execute(
        select(CitizenHistory, User.name)
        .join(User, and_(User.id == CitizenHistory.user_id, User.tenant_id == tenant_id))
        .where(*filters)
        .order_by(CitizenHistory.created_at.desc(), CitizenHistory.id.desc())
        .limit(limit + 1)
    ).all()
    has_more = len(rows) > limit
    items = rows[:limit]
    next_cursor = (
        encode_cursor(
            "citizen-history",
            created_at=items[-1][0].created_at.isoformat(),
            id=str(items[-1][0].id),
        )
        if has_more and items
        else None
    )
    return jsonify(
        content=[
            {
                "id": str(item.id),
                "acao": item.action,
                "camposAlterados": item.changed_fields,
                "metadados": item.metadata_summary,
                "usuario": user_name,
                "alteradoEm": item.created_at.isoformat(),
            }
            for item, user_name in items
        ],
        proximoCursor=next_cursor,
        limite=limit,
    )


@directory_bp.post("/cidadaos/metricas-fluxo")
@jwt_required()
def record_citizen_flow_metric():
    tenant_id, user_id = _context()
    payload = request.get_json(silent=True) or {}
    metric = str(payload.get("evento", "")).upper()
    allowed = {
        "CADASTRO_CONCLUIDO",
        "PESQUISA_SEM_RESULTADO",
        "DUPLICIDADE_DETECTADA",
        "SOLICITACAO_INICIADA",
    }
    if metric not in allowed:
        return jsonify(error="validation_error", message="Evento de fluxo inválido."), 422
    duration = payload.get("duracaoMs")
    if duration is not None:
        try:
            duration = int(duration)
        except (TypeError, ValueError):
            return jsonify(error="validation_error", message="Duração inválida."), 422
        if not 0 <= duration <= 3_600_000:
            return jsonify(error="validation_error", message="Duração inválida."), 422
    add_audit(
        tenant_id,
        user_id,
        f"citizen.flow.{metric.lower()}",
        "citizen_flow",
        None,
        after={"duracaoMs": duration} if duration is not None else {},
    )
    db.session.commit()
    return "", 204


@directory_bp.get("/cidadaos/metricas-fluxo")
@roles_required("admin", "manager")
def citizen_flow_metrics():
    tenant_id, _ = _context()
    since = datetime.now(UTC) - timedelta(days=30)
    rows = db.session.execute(
        select(AuditLog).where(
            AuditLog.tenant_id == tenant_id,
            AuditLog.entity_type == "citizen_flow",
            AuditLog.created_at >= since,
        )
    ).scalars()
    counts: dict[str, int] = {}
    registration_durations = []
    for item in rows:
        event = item.action.removeprefix("citizen.flow.").upper()
        counts[event] = counts.get(event, 0) + 1
        duration = (item.after or {}).get("duracaoMs")
        if event == "CADASTRO_CONCLUIDO" and isinstance(duration, int):
            registration_durations.append(duration)
    return jsonify(
        periodoDias=30,
        eventos=counts,
        tempoMedioCadastroMs=(
            round(sum(registration_durations) / len(registration_durations))
            if registration_durations
            else None
        ),
    )


@directory_bp.post("/enderecos/resolver")
@jwt_required()
def resolve_citizen_address():
    tenant_id, _ = _context()
    try:
        resolved = resolve_address(tenant_id, request.get_json(silent=True) or {})
    except CitizenAddressError as error:
        return jsonify(error="validation_error", message=str(error)), 422
    return jsonify(resolved)


@directory_bp.get("/cidadaos/<uuid:citizen_id>/foto")
@jwt_required()
def get_citizen_photo(citizen_id: uuid.UUID):
    tenant_id, _ = _context()
    item = db.session.execute(
        select(Citizen).where(Citizen.id == citizen_id, Citizen.tenant_id == tenant_id)
    ).scalar_one_or_none()
    if item is None or not item.photo_storage_key:
        return jsonify(error="resource_not_found", message="Foto não encontrada."), 404
    try:
        content = read_citizen_photo(tenant_id, item.photo_storage_key)
    except CitizenPhotoError:
        return jsonify(error="resource_not_found", message="Foto não encontrada."), 404
    return Response(
        content,
        mimetype="image/webp",
        headers={"Cache-Control": "private, max-age=300", "X-Content-Type-Options": "nosniff"},
    )


@directory_bp.put("/cidadaos/<uuid:citizen_id>/foto")
@jwt_required()
def put_citizen_photo(citizen_id: uuid.UUID):
    tenant_id, user_id = _context()
    item = db.session.execute(
        select(Citizen).where(Citizen.id == citizen_id, Citizen.tenant_id == tenant_id)
    ).scalar_one_or_none()
    if item is None:
        return jsonify(error="resource_not_found", message="Cidadão não encontrado."), 404
    uploaded_file = request.files.get("foto")
    if uploaded_file is None:
        return jsonify(error="validation_error", message="Selecione uma foto."), 422
    try:
        stored = store_citizen_photo(tenant_id, citizen_id, uploaded_file)
    except CitizenPhotoError as error:
        return jsonify(error="validation_error", message=str(error)), 422
    previous_key = item.photo_storage_key
    item.photo_storage_key = stored["storage_key"]
    item.version += 1
    add_citizen_history(
        tenant_id,
        item.id,
        user_id,
        "FOTO_ATUALIZADA",
        changed_fields=["foto"],
        metadata={"versao": item.version},
    )
    add_audit(
        tenant_id,
        user_id,
        "citizen.photo.updated",
        "citizen",
        item.id,
        after={
            "mimeType": stored["mime_type"],
            "tamanhoBytes": stored["size_bytes"],
            "sha256": stored["sha256"],
            "scanner": stored["scan_provider"],
        },
    )
    db.session.commit()
    if previous_key:
        _cleanup_photo(previous_key, item.id)
    return jsonify(fotoUrl=f"/api/v1/cidadaos/{item.id}/foto", versao=item.version)


@directory_bp.delete("/cidadaos/<uuid:citizen_id>/foto")
@jwt_required()
def remove_citizen_photo(citizen_id: uuid.UUID):
    tenant_id, user_id = _context()
    item = db.session.execute(
        select(Citizen).where(Citizen.id == citizen_id, Citizen.tenant_id == tenant_id)
    ).scalar_one_or_none()
    if item is None:
        return jsonify(error="resource_not_found", message="Cidadão não encontrado."), 404
    previous_key = item.photo_storage_key
    item.photo_storage_key = None
    item.version += 1
    add_citizen_history(
        tenant_id,
        item.id,
        user_id,
        "FOTO_REMOVIDA",
        changed_fields=["foto"],
        metadata={"versao": item.version},
    )
    add_audit(tenant_id, user_id, "citizen.photo.removed", "citizen", item.id)
    db.session.commit()
    if previous_key:
        _cleanup_photo(previous_key, item.id)
    return "", 204


def _cleanup_photo(storage_key: str, citizen_id: uuid.UUID) -> None:
    try:
        delete_citizen_photo(storage_key)
    except CitizenPhotoError:
        current_app.logger.warning(
            "citizen_photo_cleanup_failed", extra={"citizen_id": str(citizen_id)}
        )


@directory_bp.get("/organizacoes")
@jwt_required()
def list_organizations():
    tenant_id, _ = _context()
    query = str(request.args.get("q", "")).strip()
    filters = [Organization.tenant_id == tenant_id]
    if query:
        filters.append(Organization.name.ilike(f"%{query}%"))
    items = db.session.execute(
        select(Organization).where(*filters).order_by(Organization.name).limit(50)
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
    item.profession = None
    item.birth_date = None
    item.cpf_ciphertext = None
    item.cpf_fingerprint = None
    item.cpf_final = None
    item.cpf_key_version = None
    item.electoral_title_ciphertext = None
    item.photo_storage_key = None
    item.vip = False
    item.contacts = []
    item.addresses = []
    item.preferred_channel = None
    item.notes = None
    item.privacy_flags = ["ANONIMIZADO"]
    item.organization_links.clear()
    item.version += 1
    item.anonymized_at = datetime.now(UTC)
    add_citizen_history(
        tenant_id,
        item.id,
        user_id,
        "CADASTRO_ANONIMIZADO",
        changed_fields=["dadosPessoais", "documentos", "contatos", "enderecos"],
        metadata={"versao": item.version},
    )
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
