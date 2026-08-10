import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.extensions import db
from app.models import (
    NotificationType,
    TerritorialAction,
    TerritorialActionAlert,
    TerritorialActionStatus,
    TerritorialAlertStatus,
)
from app.notifications.service import notify_user

OPEN_STATUSES = (TerritorialActionStatus.PENDENTE, TerritorialActionStatus.EM_ANDAMENTO)


def generate_deadline_notifications(
    tenant_id: uuid.UUID,
    *,
    now: datetime | None = None,
    due_soon_hours: int = 24,
    limit: int = 200,
) -> int:
    current = now or datetime.now(UTC)
    horizon = current + timedelta(hours=due_soon_hours)
    actions = db.session.scalars(
        select(TerritorialAction)
        .where(
            TerritorialAction.tenant_id == tenant_id,
            TerritorialAction.status.in_(OPEN_STATUSES),
            TerritorialAction.assignee_id.is_not(None),
            TerritorialAction.due_at.is_not(None),
            TerritorialAction.due_at <= horizon,
        )
        .order_by(TerritorialAction.due_at)
        .limit(limit)
        .with_for_update(skip_locked=True)
    )
    generated = 0
    for action in actions:
        due_at = _utc(action.due_at)
        if due_at < current:
            if action.overdue_notified_at is not None:
                _create_alert_if_missing(
                    action, "PRAZO_VENCIDO", "Ação territorial vencida",
                    f'A ação "{action.title}" ultrapassou o prazo definido.', current,
                )
                continue
            _resolve_alert_type(action, "PRAZO_PROXIMO", current, "Prazo vencido")
            _activate_alert(
                action, "PRAZO_VENCIDO", "Ação territorial vencida",
                f'A ação "{action.title}" ultrapassou o prazo definido.', current,
            )
            notify_user(
                tenant_id,
                action.assignee_id,
                NotificationType.SLA,
                "Ação territorial vencida",
                f'A ação "{action.title}" ultrapassou o prazo definido.',
                "territorial_action",
                action.id,
            )
            action.overdue_notified_at = current
        else:
            if action.due_soon_notified_at is not None:
                _create_alert_if_missing(
                    action, "PRAZO_PROXIMO", "Prazo territorial próximo",
                    f'A ação "{action.title}" vence nas próximas 24 horas.', current,
                )
                continue
            _activate_alert(
                action, "PRAZO_PROXIMO", "Prazo territorial próximo",
                f'A ação "{action.title}" vence nas próximas 24 horas.', current,
            )
            notify_user(
                tenant_id,
                action.assignee_id,
                NotificationType.SLA,
                "Prazo territorial próximo",
                f'A ação "{action.title}" vence nas próximas {due_soon_hours} horas.',
                "territorial_action",
                action.id,
            )
            action.due_soon_notified_at = current
        generated += 1
    return generated


def reset_deadline_notifications(action: TerritorialAction) -> None:
    action.due_soon_notified_at = None
    action.overdue_notified_at = None
    resolve_action_alerts(action, note="Prazo redefinido")


def resolve_action_alerts(
    action: TerritorialAction,
    *,
    actor_id: uuid.UUID | None = None,
    note: str = "Ação encerrada",
) -> int:
    now = datetime.now(UTC)
    alerts = db.session.scalars(select(TerritorialActionAlert).where(
        TerritorialActionAlert.tenant_id == action.tenant_id,
        TerritorialActionAlert.action_id == action.id,
        TerritorialActionAlert.status != TerritorialAlertStatus.RESOLVIDO,
    )).all()
    for alert in alerts:
        alert.status = TerritorialAlertStatus.RESOLVIDO
        alert.resolved_at = now
        alert.resolved_by_id = actor_id
        alert.resolution_note = note[:500]
    return len(alerts)


def _activate_alert(
    action: TerritorialAction,
    alert_type: str,
    title: str,
    message: str,
    triggered_at: datetime,
) -> TerritorialActionAlert:
    alert = db.session.execute(select(TerritorialActionAlert).where(
        TerritorialActionAlert.tenant_id == action.tenant_id,
        TerritorialActionAlert.action_id == action.id,
        TerritorialActionAlert.alert_type == alert_type,
    )).scalar_one_or_none()
    if alert is None:
        alert = TerritorialActionAlert(
            tenant_id=action.tenant_id,
            action_id=action.id,
            alert_type=alert_type,
            status=TerritorialAlertStatus.ATIVO,
            title=title,
            message=message,
            triggered_at=triggered_at,
        )
        db.session.add(alert)
    else:
        alert.status = TerritorialAlertStatus.ATIVO
        alert.title = title
        alert.message = message
        alert.triggered_at = triggered_at
        alert.acknowledged_at = None
        alert.acknowledged_by_id = None
        alert.resolved_at = None
        alert.resolved_by_id = None
        alert.resolution_note = None
    return alert


def _create_alert_if_missing(
    action: TerritorialAction,
    alert_type: str,
    title: str,
    message: str,
    triggered_at: datetime,
) -> None:
    exists = db.session.scalar(select(TerritorialActionAlert.id).where(
        TerritorialActionAlert.tenant_id == action.tenant_id,
        TerritorialActionAlert.action_id == action.id,
        TerritorialActionAlert.alert_type == alert_type,
    ))
    if exists is None:
        _activate_alert(action, alert_type, title, message, triggered_at)


def _resolve_alert_type(
    action: TerritorialAction,
    alert_type: str,
    resolved_at: datetime,
    note: str,
) -> None:
    alert = db.session.execute(select(TerritorialActionAlert).where(
        TerritorialActionAlert.tenant_id == action.tenant_id,
        TerritorialActionAlert.action_id == action.id,
        TerritorialActionAlert.alert_type == alert_type,
        TerritorialActionAlert.status != TerritorialAlertStatus.RESOLVIDO,
    )).scalar_one_or_none()
    if alert:
        alert.status = TerritorialAlertStatus.RESOLVIDO
        alert.resolved_at = resolved_at
        alert.resolution_note = note


def _utc(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)
