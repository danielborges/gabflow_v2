import uuid
from datetime import UTC, datetime

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt, get_jwt_identity, jwt_required
from sqlalchemy import func, select

from app.audit import add_audit
from app.communications.service import generate_return_reminders
from app.extensions import db
from app.models import Notification, NotificationPreference, NotificationType

notifications_bp = Blueprint("notifications", __name__)


def _context() -> tuple[uuid.UUID, uuid.UUID]:
    return uuid.UUID(get_jwt()["tenant_id"]), uuid.UUID(get_jwt_identity())


def _serialize(item: Notification) -> dict:
    return {
        "id": str(item.id),
        "tipo": item.notification_type.value,
        "titulo": item.title,
        "mensagem": item.message,
        "entidadeTipo": item.entity_type,
        "entidadeId": item.entity_id,
        "lidaEm": item.read_at.isoformat() if item.read_at else None,
        "criadaEm": item.created_at.isoformat(),
    }


def _preference_data(item_type: NotificationType, preference: NotificationPreference | None):
    return {
        "tipo": item_type.value,
        "habilitada": preference.enabled if preference else True,
    }


@notifications_bp.get("/notificacoes")
@jwt_required()
def list_notifications():
    tenant_id, user_id = _context()
    if generate_return_reminders(tenant_id, user_id):
        db.session.commit()
    items = db.session.execute(
        select(Notification)
        .where(Notification.tenant_id == tenant_id, Notification.user_id == user_id)
        .order_by(Notification.created_at.desc())
        .limit(50)
    ).scalars()
    unread = db.session.execute(
        select(func.count(Notification.id)).where(
            Notification.tenant_id == tenant_id,
            Notification.user_id == user_id,
            Notification.read_at.is_(None),
        )
    ).scalar_one()
    return jsonify(content=[_serialize(item) for item in items], naoLidas=unread)


@notifications_bp.patch("/notificacoes/<uuid:notification_id>/lida")
@jwt_required()
def mark_read(notification_id: uuid.UUID):
    tenant_id, user_id = _context()
    item = db.session.execute(
        select(Notification).where(
            Notification.id == notification_id,
            Notification.tenant_id == tenant_id,
            Notification.user_id == user_id,
        )
    ).scalar_one_or_none()
    if item is None:
        return jsonify(error="resource_not_found", message="Notificação não encontrada."), 404
    if item.read_at is None:
        item.read_at = datetime.now(UTC)
        db.session.commit()
    return jsonify(_serialize(item))


@notifications_bp.post("/notificacoes/marcar-todas-lidas")
@jwt_required()
def mark_all_read():
    tenant_id, user_id = _context()
    items = db.session.execute(
        select(Notification).where(
            Notification.tenant_id == tenant_id,
            Notification.user_id == user_id,
            Notification.read_at.is_(None),
        )
    ).scalars()
    now = datetime.now(UTC)
    count = 0
    for item in items:
        item.read_at = now
        count += 1
    db.session.commit()
    return jsonify(atualizadas=count)


@notifications_bp.get("/notificacoes/preferencias")
@jwt_required()
def list_preferences():
    tenant_id, user_id = _context()
    preferences = {
        item.notification_type: item
        for item in db.session.execute(
            select(NotificationPreference).where(
                NotificationPreference.tenant_id == tenant_id,
                NotificationPreference.user_id == user_id,
            )
        ).scalars()
    }
    return jsonify(
        content=[
            _preference_data(item_type, preferences.get(item_type))
            for item_type in NotificationType
        ]
    )


@notifications_bp.put("/notificacoes/preferencias")
@jwt_required()
def update_preferences():
    tenant_id, user_id = _context()
    payload = request.get_json(silent=True) or {}
    values = payload.get("preferencias")
    if not isinstance(values, list):
        return jsonify(error="validation_error", message="Informe as preferências."), 422
    updated = []
    for value in values:
        try:
            item_type = NotificationType(str(value.get("tipo", "")).upper())
        except (AttributeError, ValueError):
            return jsonify(error="validation_error", message="Tipo de notificação inválido."), 422
        enabled = value.get("habilitada")
        if not isinstance(enabled, bool):
            return jsonify(error="validation_error", message="Preferência inválida."), 422
        preference = db.session.execute(
            select(NotificationPreference).where(
                NotificationPreference.tenant_id == tenant_id,
                NotificationPreference.user_id == user_id,
                NotificationPreference.notification_type == item_type,
            )
        ).scalar_one_or_none()
        if preference is None:
            preference = NotificationPreference(
                tenant_id=tenant_id,
                user_id=user_id,
                notification_type=item_type,
            )
            db.session.add(preference)
        preference.enabled = enabled
        updated.append(_preference_data(item_type, preference))
    add_audit(
        tenant_id,
        user_id,
        "notification.preferences.updated",
        "user",
        user_id,
        after={"preferencias": updated},
    )
    db.session.commit()
    return jsonify(content=updated)
