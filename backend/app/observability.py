import json
import logging
from datetime import UTC, datetime, timedelta

from flask import current_app, g, has_request_context
from sqlalchemy import func, select

from app.extensions import db
from app.models import OutboxEvent
from app.outbox.service import RAG_QUEUE_EVENT_TYPES


class JsonLogFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "service": "gabflow",
            "logger": record.name,
            "message": record.getMessage(),
        }
        if has_request_context():
            payload["requestId"] = getattr(g, "request_id", None)
            tenant_id = db.session.info.get("tenant_id")
            payload["tenantId"] = str(tenant_id) if tenant_id else None
        for source, target in (
            ("event_type", "eventType"),
            ("event_id", "eventId"),
            ("worker_id", "workerId"),
            ("duration_ms", "durationMs"),
            ("queue", "queue"),
        ):
            value = getattr(record, source, None)
            if value is not None:
                payload[target] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def configure_logging(app) -> None:
    if app.config.get("LOG_FORMAT") != "json":
        return
    formatter = JsonLogFormatter()
    for handler in app.logger.handlers or logging.getLogger().handlers:
        handler.setFormatter(formatter)


def rag_pipeline_snapshot() -> dict:
    now = datetime.now(UTC)
    since = now - timedelta(hours=current_app.config["RAG_METRICS_WINDOW_HOURS"])
    pending_filter = (
        OutboxEvent.event_type.in_(RAG_QUEUE_EVENT_TYPES),
        OutboxEvent.published_at.is_(None),
        OutboxEvent.failed_at.is_(None),
    )
    pending = db.session.scalar(
        select(func.count(OutboxEvent.id)).where(*pending_filter)
    )
    oldest = db.session.scalar(
        select(func.min(OutboxEvent.occurred_at)).where(*pending_filter)
    )
    failed = db.session.scalar(
        select(func.count(OutboxEvent.id)).where(
            OutboxEvent.event_type.in_(RAG_QUEUE_EVENT_TYPES),
            OutboxEvent.failed_at >= since,
        )
    )
    durations = list(
        db.session.scalars(
            select(OutboxEvent.processing_duration_ms)
            .where(
                OutboxEvent.event_type.in_(RAG_QUEUE_EVENT_TYPES),
                OutboxEvent.published_at >= since,
                OutboxEvent.processing_duration_ms.is_not(None),
            )
            .order_by(OutboxEvent.published_at.desc())
            .limit(10000)
        )
    )
    oldest_age = 0
    if oldest is not None:
        if oldest.tzinfo is None:
            oldest = oldest.replace(tzinfo=UTC)
        oldest_age = max(0, round((now - oldest).total_seconds()))
    max_age = current_app.config["RAG_SLO_QUEUE_MAX_AGE_SECONDS"]
    return {
        "status": "degraded" if failed or oldest_age > max_age else "ok",
        "queue": {
            "pending": pending or 0,
            "failedWindow": failed or 0,
            "oldestAgeSeconds": oldest_age,
        },
        "processing": {
            "samples": len(durations),
            "p95Ms": percentile(durations, 0.95),
        },
        "windowHours": current_app.config["RAG_METRICS_WINDOW_HOURS"],
        "slo": {"queueMaxAgeSeconds": max_age},
    }


def prometheus_metrics(snapshot: dict) -> str:
    queue = snapshot["queue"]
    processing = snapshot["processing"]
    healthy = 1 if snapshot["status"] == "ok" else 0
    values = (
        ("gabflow_rag_pipeline_healthy", healthy),
        ("gabflow_rag_outbox_pending", queue["pending"]),
        ("gabflow_rag_outbox_failed_window", queue["failedWindow"]),
        ("gabflow_rag_outbox_oldest_age_seconds", queue["oldestAgeSeconds"]),
        ("gabflow_rag_processing_duration_p95_ms", processing["p95Ms"] or 0),
        ("gabflow_rag_processing_samples", processing["samples"]),
    )
    return "\n".join(f"# TYPE {name} gauge\n{name} {value}" for name, value in values) + "\n"


def percentile(values: list[int], quantile: float) -> int | None:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, int((len(ordered) - 1) * quantile + 0.9999)))
    return ordered[index]
