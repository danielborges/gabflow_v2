import uuid
from functools import wraps

from flask import jsonify
from flask_jwt_extended import get_jwt, get_jwt_identity, verify_jwt_in_request


def roles_required(*allowed_roles: str):
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            verify_jwt_in_request()
            role = get_jwt().get("role")
            if role not in allowed_roles:
                return jsonify(error="forbidden", message="Permissão insuficiente."), 403
            return fn(*args, **kwargs)

        return wrapper

    return decorator


def roles_or_chief_required(*allowed_roles: str):
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            verify_jwt_in_request()
            role = get_jwt().get("role")
            if role not in allowed_roles and not is_chief_of_staff():
                return jsonify(error="forbidden", message="PermissÃ£o insuficiente."), 403
            return fn(*args, **kwargs)

        return wrapper

    return decorator


def platform_admin_required(fn):
    return roles_required("platform_admin")(fn)


def is_chief_of_staff() -> bool:
    claims = get_jwt()
    if claims.get("is_chief_of_staff") is True:
        return True
    tenant_id = claims.get("tenant_id")
    user_id = get_jwt_identity()
    if not tenant_id or not user_id:
        return False
    try:
        tenant_uuid = uuid.UUID(str(tenant_id))
    except (TypeError, ValueError):
        return False
    from app.extensions import db
    from app.models import Tenant

    tenant = db.session.get(Tenant, tenant_uuid)
    return bool(tenant and tenant.chief_of_staff_id and str(tenant.chief_of_staff_id) == user_id)
