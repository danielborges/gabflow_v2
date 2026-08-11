import uuid
from datetime import UTC, datetime

from sqlalchemy import select

from app.extensions import db
from app.models import (
    AgendaEvent,
    AgendaEventStatus,
    AgendaEventType,
    Notification,
    NotificationType,
    OversightAction,
    OversightActionStatus,
)
from app.notifications.service import notify_user

NOTIFICATION_ENTITY = "agenda_oversight_report"


def pending_oversight_events(tenant_id: uuid.UUID, user_id: uuid.UUID) -> list[dict]:
    now = datetime.now(UTC)
    events = list(
        db.session.execute(
            select(AgendaEvent)
            .where(
                AgendaEvent.tenant_id == tenant_id,
                AgendaEvent.event_type == AgendaEventType.FISCALIZACAO,
                AgendaEvent.status != AgendaEventStatus.CANCELADO,
                AgendaEvent.starts_at <= now,
            )
            .order_by(AgendaEvent.starts_at)
        ).scalars()
    )
    events = [
        event
        for event in events
        if _aware(event.ends_at or event.starts_at) <= now and _is_participant(event, user_id)
    ]
    if not events:
        return []
    actions = {
        action.agenda_event_id: action
        for action in db.session.execute(
            select(OversightAction).where(
                OversightAction.tenant_id == tenant_id,
                OversightAction.agenda_event_id.in_([event.id for event in events]),
            )
        ).scalars()
    }
    pending = []
    for event in events:
        action = actions.get(event.id)
        if action and action.status == OversightActionStatus.CONCLUIDA and action.report:
            continue
        pending.append(
            {
                "agendaEventoId": str(event.id),
                "fiscalizacaoId": str(action.id) if action else None,
                "titulo": event.title,
                "descricao": event.description,
                "local": event.location,
                "inicio": event.starts_at.isoformat(),
                "fim": event.ends_at.isoformat() if event.ends_at else None,
                "solicitacaoId": str(event.request_id) if event.request_id else None,
                "participantes": event.participants,
                "statusRelatorio": "RASCUNHO" if action else "NAO_INICIADO",
            }
        )
    return pending


def generate_oversight_report_reminders(tenant_id: uuid.UUID, user_id: uuid.UUID) -> int:
    created = 0
    for item in pending_oversight_events(tenant_id, user_id):
        exists = db.session.execute(
            select(Notification.id).where(
                Notification.tenant_id == tenant_id,
                Notification.user_id == user_id,
                Notification.entity_type == NOTIFICATION_ENTITY,
                Notification.entity_id == item["agendaEventoId"],
            )
        ).scalar_one_or_none()
        if exists:
            continue
        notify_user(
            tenant_id,
            user_id,
            NotificationType.TAREFA,
            "Relatório de fiscalização pendente",
            (
                f"A fiscalização “{item['titulo']}” já foi realizada. "
                "Registre o relatório e as evidências."
            ),
            NOTIFICATION_ENTITY,
            item["agendaEventoId"],
        )
        created += 1
    return created


def resolve_oversight_reminders(tenant_id: uuid.UUID, agenda_event_id: uuid.UUID) -> None:
    now = datetime.now(UTC)
    notifications = db.session.execute(
        select(Notification).where(
            Notification.tenant_id == tenant_id,
            Notification.entity_type == NOTIFICATION_ENTITY,
            Notification.entity_id == str(agenda_event_id),
            Notification.read_at.is_(None),
        )
    ).scalars()
    for notification in notifications:
        notification.read_at = now


def user_is_event_participant(event: AgendaEvent, user_id: uuid.UUID) -> bool:
    return _is_participant(event, user_id)


def _is_participant(event: AgendaEvent, user_id: uuid.UUID) -> bool:
    expected = str(user_id)
    return any(
        isinstance(participant, dict) and str(participant.get("id")) == expected
        for participant in (event.participants or [])
    )


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)
