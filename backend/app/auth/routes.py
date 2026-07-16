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
from app.models import AuditLog, Tenant, TenantStatus, User, UserStatus

auth_bp = Blueprint("auth", __name__)


def _serialize_user(user: User) -> dict:
    return {
        "id": str(user.id),
        "name": user.name,
        "email": user.email,
        "role": user.role.value,
        "tenant": {
            "id": str(user.tenant.id),
            "name": user.tenant.name,
            "slug": user.tenant.slug,
        },
    }


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


@auth_bp.post("/login")
@limiter.limit("5 per minute")
def login():
    payload = request.get_json(silent=True) or {}
    email = str(payload.get("email", "")).strip().lower()
    password = str(payload.get("password", ""))
    tenant_slug = str(payload.get("tenant", "")).strip().lower()

    if not email or not password or not tenant_slug:
        return jsonify(error="validation_error", message="Preencha tenant, e-mail e senha."), 400

    statement = select(User).join(Tenant).where(User.email == email, Tenant.slug == tenant_slug)
    user = db.session.execute(statement).scalar_one_or_none()

    if (
        user is None
        or user.status != UserStatus.ACTIVE
        or user.tenant.status != TenantStatus.ACTIVE
        or not verify_password(user.password_hash, password)
    ):
        return jsonify(error="invalid_credentials", message="Credenciais inválidas."), 401

    user.last_login_at = datetime.now(UTC)
    _audit(user, "auth.login")
    db.session.commit()

    token = create_access_token(
        identity=str(user.id),
        additional_claims={"tenant_id": str(user.tenant_id), "role": user.role.value},
    )
    response = jsonify(user=_serialize_user(user))
    set_access_cookies(response, token)
    return response


@auth_bp.post("/logout")
@jwt_required()
def logout():
    user_id = uuid.UUID(get_jwt_identity())
    tenant_id = uuid.UUID(get_jwt()["tenant_id"])
    db.session.add(
        AuditLog(
            tenant_id=tenant_id,
            user_id=user_id,
            action="auth.logout",
            entity_type="user",
            entity_id=str(user_id),
            ip_address=request.remote_addr,
            user_agent=request.user_agent.string[:512],
        )
    )
    db.session.commit()
    response = jsonify(message="Sessão encerrada.")
    unset_jwt_cookies(response)
    return response


@auth_bp.get("/me")
@jwt_required()
def me():
    user_id = uuid.UUID(get_jwt_identity())
    tenant_id = uuid.UUID(get_jwt()["tenant_id"])
    user = db.session.execute(
        select(User).where(User.id == user_id, User.tenant_id == tenant_id)
    ).scalar_one_or_none()
    if user is None or user.status != UserStatus.ACTIVE:
        return jsonify(error="unauthorized", message="Sessão inválida."), 401
    return jsonify(user=_serialize_user(user))
