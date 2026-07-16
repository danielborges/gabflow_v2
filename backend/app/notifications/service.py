import uuid

from sqlalchemy import select

from app.extensions import db
from app.models import Notification, NotificationPreference, NotificationType


def notify_user(
    tenant_id: uuid.UUID,
    user_id: uuid.UUID | None,
    notification_type: NotificationType,
    title: str,
    message: str,
    entity_type: str | None = None,
    entity_id: uuid.UUID | str | None = None,
) -> None:
    if user_id is None:
        return
    preference = db.session.execute(
        select(NotificationPreference).where(
            NotificationPreference.tenant_id == tenant_id,
            NotificationPreference.user_id == user_id,
            NotificationPreference.notification_type == notification_type,
        )
    ).scalar_one_or_none()
    if preference is not None and not preference.enabled:
        return
    db.session.add(
        Notification(
            tenant_id=tenant_id,
            user_id=user_id,
            notification_type=notification_type,
            title=title,
            message=message,
            entity_type=entity_type,
            entity_id=str(entity_id) if entity_id else None,
        )
    )
