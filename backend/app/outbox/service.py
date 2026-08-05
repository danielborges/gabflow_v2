import socket
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from flask import current_app
from sqlalchemy import or_, select

from app.extensions import db
from app.models import OutboxEvent
from app.outbox.handlers import NonRetryableEventError, handle_event, handle_exhausted_event
from app.outbox.lease import renewable_event_lease
from app.tenant_context import clear_tenant_context, tenant_context

RAG_QUEUE_EVENT_TYPES = {
    "IngestaoDocumentoRag",
    "IngestaoDocumentoRagGlobal",
    "SincronizacaoMemoriaOperacional",
    "CompilacaoSinaisRag",
    "AvaliacaoPerfilQualidadeRag",
    "AvaliacaoRolloutPerfilQualidadeRag",
    "RevarreduraSegurancaRag",
    "AuditoriaAutomatizadaRls",
}
WORKER_QUEUES = {"all", "default", "rag"}


@dataclass(frozen=True)
class ProcessingResult:
    claimed: int = 0
    succeeded: int = 0
    retried: int = 0
    failed: int = 0


def worker_identity() -> str:
    return f"{socket.gethostname()}-{uuid.uuid4().hex[:8]}"


def process_batch(worker_id: str) -> ProcessingResult:
    event_ids = claim_events(worker_id)
    succeeded = retried = failed = 0
    for event_id in event_ids:
        outcome = process_event(event_id, worker_id)
        succeeded += outcome == "succeeded"
        retried += outcome == "retried"
        failed += outcome == "failed"
    return ProcessingResult(len(event_ids), succeeded, retried, failed)


def claim_events(worker_id: str) -> list[uuid.UUID]:
    now = datetime.now(UTC)
    lock_expired_at = now - timedelta(seconds=current_app.config["WORKER_LOCK_TIMEOUT_SECONDS"])
    statement = select(OutboxEvent).where(
        OutboxEvent.published_at.is_(None),
        OutboxEvent.failed_at.is_(None),
        OutboxEvent.available_at <= now,
        or_(
            OutboxEvent.locked_at.is_(None),
            OutboxEvent.locked_at < lock_expired_at,
        ),
    )
    queue = str(current_app.config.get("WORKER_QUEUE", "all")).lower()
    if queue not in WORKER_QUEUES:
        raise ValueError(f"Fila de worker inválida: {queue}.")
    if queue == "rag":
        statement = statement.where(OutboxEvent.event_type.in_(RAG_QUEUE_EVENT_TYPES))
    elif queue == "default":
        statement = statement.where(OutboxEvent.event_type.not_in(RAG_QUEUE_EVENT_TYPES))
    statement = (
        statement.order_by(OutboxEvent.occurred_at, OutboxEvent.id)
        .limit(current_app.config["WORKER_BATCH_SIZE"])
        .with_for_update(skip_locked=True)
    )
    events = list(db.session.execute(statement).scalars())
    for event in events:
        event.locked_at = now
        event.locked_by = worker_id
    db.session.commit()
    return [event.id for event in events]


def process_event(event_id: uuid.UUID, worker_id: str) -> str:
    started = time.perf_counter()
    event = db.session.execute(
        select(OutboxEvent).where(
            OutboxEvent.id == event_id,
            OutboxEvent.locked_by == worker_id,
            OutboxEvent.published_at.is_(None),
            OutboxEvent.failed_at.is_(None),
        )
    ).scalar_one_or_none()
    if event is None:
        return "skipped"

    try:
        if event.tenant_id is None:
            with renewable_event_lease(event.id, worker_id):
                handle_event(event)
            event.published_at = datetime.now(UTC)
            event.locked_at = None
            event.locked_by = None
            event.last_error = None
            event.processing_duration_ms = _duration_ms(started)
            current_app.logger.info(
                "Outbox event processed",
                extra={
                    "event_type": event.event_type,
                    "event_id": str(event.id),
                    "worker_id": worker_id,
                    "duration_ms": event.processing_duration_ms,
                },
            )
            db.session.commit()
            return "succeeded"
        with tenant_context(event.tenant_id):
            with renewable_event_lease(event.id, worker_id):
                handle_event(event)
            event.published_at = datetime.now(UTC)
            event.locked_at = None
            event.locked_by = None
            event.last_error = None
            event.processing_duration_ms = _duration_ms(started)
            current_app.logger.info(
                "Outbox event processed",
                extra={
                    "event_type": event.event_type,
                    "event_id": str(event.id),
                    "worker_id": worker_id,
                    "duration_ms": event.processing_duration_ms,
                },
            )
            db.session.commit()
            return "succeeded"
    except Exception as error:
        db.session.rollback()
        clear_tenant_context()
        return _record_failure(event_id, worker_id, error, started)


def _record_failure(event_id: uuid.UUID, worker_id: str, error: Exception, started: float) -> str:
    event = db.session.execute(
        select(OutboxEvent)
        .where(OutboxEvent.id == event_id, OutboxEvent.locked_by == worker_id)
        .with_for_update()
    ).scalar_one_or_none()
    if event is None:
        return "skipped"

    now = datetime.now(UTC)
    event.attempt_count += 1
    event.last_error = str(error)[:2000]
    event.processing_duration_ms = _duration_ms(started)
    event.locked_at = None
    event.locked_by = None
    exhausted = (
        isinstance(error, NonRetryableEventError)
        or event.attempt_count >= current_app.config["WORKER_MAX_ATTEMPTS"]
    )
    if exhausted:
        event.failed_at = now
        try:
            if event.tenant_id is None:
                handle_exhausted_event(event, event.last_error)
                db.session.commit()
            else:
                with tenant_context(event.tenant_id):
                    handle_exhausted_event(event, event.last_error)
                    db.session.commit()
        except Exception:
            db.session.rollback()
            clear_tenant_context()
            current_app.logger.exception(
                "Failed to record exhausted outbox event side effects id=%s",
                event_id,
            )
            event = db.session.get(OutboxEvent, event_id)
            if event is not None:
                if event.tenant_id is None:
                    event.attempt_count = max(
                        event.attempt_count,
                        current_app.config["WORKER_MAX_ATTEMPTS"],
                    )
                    event.last_error = str(error)[:2000]
                    event.failed_at = now
                    event.locked_at = None
                    event.locked_by = None
                    db.session.commit()
                else:
                    with tenant_context(event.tenant_id):
                        event.attempt_count = max(
                            event.attempt_count,
                            current_app.config["WORKER_MAX_ATTEMPTS"],
                        )
                        event.last_error = str(error)[:2000]
                        event.failed_at = now
                        event.locked_at = None
                        event.locked_by = None
                        db.session.commit()
        current_app.logger.error(
            "Outbox event permanently failed type=%s id=%s attempts=%s",
            event.event_type,
            event.id,
            event.attempt_count,
        )
        return "failed"

    delay = min(
        current_app.config["WORKER_RETRY_BASE_SECONDS"] * (2 ** (event.attempt_count - 1)),
        current_app.config["WORKER_RETRY_MAX_SECONDS"],
    )
    event.available_at = now + timedelta(seconds=delay)
    db.session.commit()
    clear_tenant_context()
    current_app.logger.warning(
        "Outbox event scheduled for retry type=%s id=%s attempt=%s delay=%ss",
        event.event_type,
        event.id,
        event.attempt_count,
        delay,
    )
    return "retried"


def _duration_ms(started: float) -> int:
    return max(1, round((time.perf_counter() - started) * 1000))
