import threading
from contextlib import contextmanager
from datetime import UTC, datetime

from flask import current_app
from sqlalchemy import update

from app.extensions import db
from app.models import OutboxEvent


@contextmanager
def renewable_event_lease(event_id, worker_id):
    """Keep a long-running outbox claim from being reclaimed by another worker."""
    configured = max(0, int(current_app.config["WORKER_HEARTBEAT_SECONDS"]))
    lock_timeout = max(
        2, int(current_app.config["WORKER_LOCK_TIMEOUT_SECONDS"])
    )
    interval = min(configured, max(1, lock_timeout // 3))
    if interval == 0 or db.engine.dialect.name == "sqlite":
        yield
        return

    app = current_app._get_current_object()
    engine = db.engine
    stopped = threading.Event()

    def heartbeat():
        while not stopped.wait(interval):
            try:
                with app.app_context(), engine.begin() as connection:
                    connection.execute(
                        update(OutboxEvent)
                        .where(
                            OutboxEvent.id == event_id,
                            OutboxEvent.locked_by == worker_id,
                            OutboxEvent.published_at.is_(None),
                            OutboxEvent.failed_at.is_(None),
                        )
                        .values(locked_at=datetime.now(UTC))
                    )
            except Exception:
                app.logger.exception(
                    "Failed to renew outbox lease event=%s worker=%s",
                    event_id,
                    worker_id,
                )

    thread = threading.Thread(
        target=heartbeat,
        name=f"outbox-lease-{str(event_id)[:8]}",
        daemon=True,
    )
    thread.start()
    try:
        yield
    finally:
        stopped.set()
        thread.join(timeout=min(1.0, float(interval)))
