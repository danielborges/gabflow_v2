import uuid

from flask_jwt_extended import get_jwt, get_jwt_identity
from sqlalchemy import or_

from app.auth.permissions import is_chief_of_staff
from app.models import ServiceRequest


def can_distribute_requests() -> bool:
    return get_jwt().get("role") in {"admin", "representative"} or is_chief_of_staff()


def request_visibility_filters(
    tenant_id: uuid.UUID, user_id: uuid.UUID | None = None
) -> list:
    user_id = user_id or uuid.UUID(get_jwt_identity())
    filters = [ServiceRequest.tenant_id == tenant_id]
    if not can_distribute_requests():
        filters.append(
            or_(
                ServiceRequest.responsible_id == user_id,
                ServiceRequest.responsible_id.is_(None),
            )
        )
    return filters
