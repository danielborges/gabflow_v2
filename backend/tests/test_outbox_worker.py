from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.communications.email import EmailDeliveryError
from app.extensions import db
from app.models import OutboxEvent, Tenant
from app.outbox.service import ProcessingResult, process_batch
from app.outbox.worker import run_worker


def _event(tenant_id):
    return OutboxEvent(
        tenant_id=tenant_id,
        event_type="TesteIntegracao",
        aggregate_type="Teste",
        aggregate_id="aggregate-1",
        payload={"value": 1},
    )


def test_transient_failure_uses_exponential_backoff(app, monkeypatch):
    with app.app_context():
        tenant_id = db.session.execute(select(Tenant.id).limit(1)).scalar_one()
        event = _event(tenant_id)
        db.session.add(event)
        db.session.commit()
        event_id = event.id

        def fail(_event):
            raise EmailDeliveryError("Falha transitória.")

        monkeypatch.setattr("app.outbox.service.handle_event", fail)
        before = datetime.now(UTC)
        result = process_batch("worker-a")

        assert result.retried == 1
        stored = db.session.get(OutboxEvent, event_id)
        assert stored.attempt_count == 1
        available_at = stored.available_at.replace(tzinfo=UTC)
        assert available_at >= before + timedelta(
            seconds=app.config["WORKER_RETRY_BASE_SECONDS"]
        )
        assert stored.locked_at is None
        assert stored.published_at is None


def test_retry_succeeds_without_reprocessing_published_event(app, monkeypatch):
    with app.app_context():
        tenant_id = db.session.execute(select(Tenant.id).limit(1)).scalar_one()
        event = _event(tenant_id)
        db.session.add(event)
        db.session.commit()
        event_id = event.id
        calls = []

        monkeypatch.setattr("app.outbox.service.handle_event", lambda item: calls.append(item.id))
        first = process_batch("worker-a")
        second = process_batch("worker-a")

        assert first.succeeded == 1
        assert second.claimed == 0
        assert calls == [event_id]
        assert db.session.get(OutboxEvent, event_id).published_at is not None


def test_stale_lock_can_be_reclaimed(app, monkeypatch):
    with app.app_context():
        tenant_id = db.session.execute(select(Tenant.id).limit(1)).scalar_one()
        event = _event(tenant_id)
        event.locked_by = "dead-worker"
        event.locked_at = datetime.now(UTC) - timedelta(
            seconds=app.config["WORKER_LOCK_TIMEOUT_SECONDS"] + 1
        )
        db.session.add(event)
        db.session.commit()

        monkeypatch.setattr("app.outbox.service.handle_event", lambda _event: None)
        result = process_batch("worker-b")

        assert result.succeeded == 1


def test_worker_once_runs_outbox_and_scheduler(app, monkeypatch):
    calls = []
    monkeypatch.setattr(
        "app.outbox.worker.process_batch",
        lambda worker_id: calls.append(("outbox", worker_id)) or ProcessingResult(),
    )
    monkeypatch.setattr(
        "app.outbox.worker.generate_due_return_reminders",
        lambda: calls.append(("scheduler", None)) or 0,
    )

    result = run_worker(app, once=True)

    assert result == ProcessingResult()
    assert calls[0][0] == "outbox"
    assert calls[1] == ("scheduler", None)
