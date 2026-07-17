import signal
import time
from dataclasses import dataclass

from flask import Flask

from app.communications.service import generate_due_return_reminders
from app.extensions import db
from app.outbox.service import ProcessingResult, process_batch, worker_identity


@dataclass
class WorkerState:
    running: bool = True


def run_worker(app: Flask, *, once: bool = False) -> ProcessingResult:
    worker_id = worker_identity()
    state = WorkerState()
    last_scheduler_run = 0.0
    aggregate = ProcessingResult()

    def stop_worker(_signum, _frame) -> None:
        state.running = False

    if not once:
        signal.signal(signal.SIGTERM, stop_worker)
        signal.signal(signal.SIGINT, stop_worker)

    app.logger.info("Worker started id=%s", worker_id)
    while state.running:
        with app.app_context():
            result = process_batch(worker_id)
            aggregate = ProcessingResult(
                claimed=aggregate.claimed + result.claimed,
                succeeded=aggregate.succeeded + result.succeeded,
                retried=aggregate.retried + result.retried,
                failed=aggregate.failed + result.failed,
            )

            now = time.monotonic()
            if once or now - last_scheduler_run >= app.config["SCHEDULER_INTERVAL_SECONDS"]:
                reminders = generate_due_return_reminders()
                db.session.commit()
                if reminders:
                    app.logger.info("Scheduler generated %s return reminders", reminders)
                last_scheduler_run = now

        if once:
            break
        if result.claimed == 0:
            time.sleep(app.config["WORKER_POLL_SECONDS"])

    app.logger.info(
        "Worker stopped id=%s claimed=%s succeeded=%s retried=%s failed=%s",
        worker_id,
        aggregate.claimed,
        aggregate.succeeded,
        aggregate.retried,
        aggregate.failed,
    )
    return aggregate
