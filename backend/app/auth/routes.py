import uuid
from datetime import UTC, datetime

from flask import Blueprint, jsonify, request
from flask_jwt_extended import (
    create_access_token,
    get_jwt,
    get_jwt_identity,
    jwt_required,
    set_access_cookies,
    unset_jwt_cookies,
)
from sqlalchemy import select

from app.auth.security import verify_password
from app.extensions import db, limiter
from app.models import AuditLog, Role, TenantStatus, User, UserStatus
from app.modules import BLOCKING_CONTRACT_STATUSES, normalize_modules

auth_bp = Blueprint("auth", __name__)


def _serialize_user(user: User) -> dict:
    chief_of_staff = _is_chief_of_staff(user)
    return {
        "id": str(user.id),
        "name": user.name,
        "email": user.email,
        "role": user.role.value,
        "chefeGabinete": chief_of_staff,
        "funcoes": ["chefe_gabinete"] if chief_of_staff else [],
        "tenant": {
            "id": str(user.tenant.id),
            "name": user.tenant.name,
            "slug": user.tenant.slug,
            "status": user.tenant.status.value,
            "contrato": user.tenant.contract_status.value,
            "plano": user.tenant.plan,
            "modulosHabilitados": normalize_modules(user.tenant.enabled_modules),
        }
        if user.tenant is not None
        else None,
    }


def _is_chief_of_staff(user: User) -> bool:
    return bool(user.tenant and user.tenant.chief_of_staff_id == user.id)


def _audit(user: User, action: str) -> None:
    db.session.add(
        AuditLog(
            tenant_id=user.tenant_id,
            user_id=user.id,
            action=action,
            entity_type="user",
            entity_id=str(user.id),
            ip_address=request.remote_addr,
            user_agent=request.user_agent.string[:512],
        )
    )


def _resolve_login_user(email: str) -> User | None:
    users = db.session.execute(select(User).where(User.email == email)).scalars().all()
    if len(users) != 1:
        return None
    return users[0]


@auth_bp.post("/login")
@limiter.limit("5 per minute")
def login():
    payload = request.get_json(silent=True) or {}
    email = str(payload.get("email", "")).strip().lower()
    password = str(payload.get("password", ""))

    if not email or not password:
        return jsonify(error="validation_error", message="Preencha e-mail e senha."), 400

    user = _resolve_login_user(email)

    if (
        user is None
        or user.status != UserStatus.ACTIVE
        or (user.tenant is not None and user.tenant.status != TenantStatus.ACTIVE)
        or (
            user.tenant is not None
            and user.tenant.contract_status in BLOCKING_CONTRACT_STATUSES
        )
        or not verify_password(user.password_hash, password)
    ):
        return jsonify(error="invalid_credentials", message="Credenciais inválidas."), 401

    session_id = uuid.uuid4().hex
    user.current_session_id = session_id
    user.last_login_at = datetime.now(UTC)
    _audit(user, "auth.login")
    db.session.commit()

    token = create_access_token(
        identity=str(user.id),
        additional_claims={
            "tenant_id": str(user.tenant_id) if user.tenant_id else None,
            "role": user.role.value,
            "is_chief_of_staff": _is_chief_of_staff(user),
            "session_id": session_id,
        },
    )
    response = jsonify(user=_serialize_user(user))
    set_access_cookies(response, token)
    return response


@auth_bp.post("/logout")
@jwt_required()
def logout():
    user_id = uuid.UUID(get_jwt_identity())
    tenant_claim = get_jwt().get("tenant_id")
    db.session.add(
        AuditLog(
            tenant_id=uuid.UUID(tenant_claim) if tenant_claim else None,
            user_id=user_id,
            action="auth.logout",
            entity_type="user",
            entity_id=str(user_id),
            ip_address=request.remote_addr,
            user_agent=request.user_agent.string[:512],
        )
    )
    user = db.session.get(User, user_id)
    if user is not None:
        user.current_session_id = None
    db.session.commit()
    response = jsonify(message="Sessão encerrada.")
    unset_jwt_cookies(response)
    return response


@auth_bp.get("/me")
@jwt_required()
def me():
    user_id = uuid.UUID(get_jwt_identity())
    tenant_claim = get_jwt().get("tenant_id")
    statement = select(User).where(User.id == user_id)
    if tenant_claim:
        statement = statement.where(User.tenant_id == uuid.UUID(tenant_claim))
    else:
        statement = statement.where(User.role == Role.PLATFORM_ADMIN, User.tenant_id.is_(None))
    user = db.session.execute(statement).scalar_one_or_none()
    if user is None or user.status != UserStatus.ACTIVE:
        return jsonify(error="unauthorized", message="Sessão inválida."), 401
    return jsonify(user=_serialize_user(user))
