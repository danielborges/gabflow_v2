import uuid

from flask import request

from app.extensions import db
from app.models import AuditLog


def add_audit(
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    action: str,
    entity_type: str,
    entity_id: uuid.UUID | str | None,
    before: dict | None = None,
    after: dict | None = None,
) -> None:
    db.session.add(
        AuditLog(
            tenant_id=tenant_id,
            user_id=user_id,
            action=action,
            entity_type=entity_type,
            entity_id=str(entity_id) if entity_id else None,
            before=before,
            after=after,
            ip_address=request.remote_addr,
            user_agent=request.user_agent.string[:512],
        )
    )
