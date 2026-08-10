import signal
import time
from dataclasses import dataclass

from flask import Flask, current_app
from sqlalchemy import select, text

from app.communications.service import generate_due_return_reminders
from app.database_security import assert_runtime_database_role
from app.electoral.advanced_features import dispatch_due_report_schedules
from app.electoral.mandate_intelligence import dispatch_alert_deliveries
from app.electoral.reports import cleanup_expired_reports
from app.extensions import db
from app.models import Mandate, Tenant, User
from app.outbox.service import ProcessingResult, process_batch, worker_identity
from app.rag.operational_memory import enqueue_expired_operational_memory
from app.tenant_context import activate_user_context, tenant_context
from app.territorial.service import generate_deadline_notifications


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
            assert_runtime_database_role()
            result = process_batch(worker_id)
            aggregate = ProcessingResult(
                claimed=aggregate.claimed + result.claimed,
                succeeded=aggregate.succeeded + result.succeeded,
                retried=aggregate.retried + result.retried,
                failed=aggregate.failed + result.failed,
            )

            now = time.monotonic()
            if app.config["WORKER_RUN_SCHEDULER"] and (
                once or now - last_scheduler_run >= app.config["SCHEDULER_INTERVAL_SECONDS"]
            ):
                reminders, expirations, report_expirations, territorial_deadlines = (
                    _run_scheduler_once()
                )
                if reminders:
                    app.logger.info("Scheduler generated %s return reminders", reminders)
                if expirations:
                    app.logger.info(
                        "Scheduler enqueued %s operational memory expirations",
                        expirations,
                    )
                if report_expirations:
                    app.logger.info(
                        "Scheduler revoked %s expired electoral reports",
                        report_expirations,
                    )
                if territorial_deadlines:
                    app.logger.info(
                        "Scheduler generated %s territorial deadline notifications",
                        territorial_deadlines,
                    )
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


def _run_scheduler_once() -> tuple[int, int, int, int]:
    if db.engine.dialect.name == "postgresql":
        acquired = db.session.execute(
            text("SELECT pg_try_advisory_xact_lock(hashtext('gabflow.scheduler.return-reminders'))")
        ).scalar_one()
        if not acquired:
            db.session.commit()
            return 0, 0, 0, 0
    reminders = generate_due_return_reminders()
    expirations = 0
    report_expirations = 0
    electoral_alert_deliveries = 0
    recurring_report_jobs = 0
    territorial_deadlines = 0
    tenant_ids = list(db.session.scalars(select(Tenant.id).order_by(Tenant.id)))
    for tenant_id in tenant_ids:
        with tenant_context(tenant_id):
            territorial_deadlines += generate_deadline_notifications(tenant_id)
            expirations += enqueue_expired_operational_memory(tenant_id)
            report_expirations += cleanup_expired_reports(tenant_id)
            recurring_report_jobs += dispatch_due_report_schedules(tenant_id)
            user_ids = list(db.session.scalars(select(User.id).where(User.tenant_id == tenant_id)))
            mandate_ids = list(
                db.session.scalars(select(Mandate.id).where(Mandate.tenant_id == tenant_id))
            )
            for user_id in user_ids:
                activate_user_context(user_id)
                for mandate_id in mandate_ids:
                    electoral_alert_deliveries += dispatch_alert_deliveries(
                        tenant_id, mandate_id, frequencies={"DAILY", "WEEKLY"}
                    )
                db.session.info.pop("user_id", None)
    db.session.commit()
    if electoral_alert_deliveries:
        current_app.logger.info(
            "Scheduler generated %s electoral alert deliveries",
            electoral_alert_deliveries,
        )
    if recurring_report_jobs:
        current_app.logger.info(
            "Scheduler generated %s recurring electoral report jobs",
            recurring_report_jobs,
        )
    return reminders, expirations, report_expirations, territorial_deadlines
