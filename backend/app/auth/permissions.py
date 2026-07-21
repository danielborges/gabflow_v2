from functools import wraps

from flask import jsonify
from flask_jwt_extended import get_jwt, verify_jwt_in_request


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


def platform_admin_required(fn):
    return roles_required("platform_admin")(fn)
