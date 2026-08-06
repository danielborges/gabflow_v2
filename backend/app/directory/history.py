import uuid

from app.extensions import db
from app.models import CitizenHistory


def changed_field_names(before: dict, after: dict) -> list[str]:
    return sorted(key for key in before.keys() | after.keys() if before.get(key) != after.get(key))


def add_citizen_history(
    tenant_id: uuid.UUID,
    citizen_id: uuid.UUID,
    user_id: uuid.UUID,
    action: str,
    *,
    changed_fields: list[str] | None = None,
    metadata: dict | None = None,
) -> CitizenHistory:
    item = CitizenHistory(
        tenant_id=tenant_id,
        citizen_id=citizen_id,
        user_id=user_id,
        action=action,
        changed_fields=sorted(set(changed_fields or [])),
        metadata_summary=metadata or {},
    )
    db.session.add(item)
    return item
