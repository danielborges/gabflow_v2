import hmac

from flask import Blueprint, Response, current_app, jsonify, request
from sqlalchemy import text

from app.extensions import db
from app.observability import (
    prometheus_metrics,
    rag_pipeline_snapshot,
    whatsapp_prometheus_metrics,
)

health_bp = Blueprint("health", __name__)


@health_bp.get("/health")
def health():
    return jsonify(status="ok", service="gabflow-api")


@health_bp.get("/ready")
def ready():
    try:
        db.session.execute(text("SELECT 1"))
    except Exception:
        return jsonify(status="unavailable", database="down"), 503
    return jsonify(status="ok", database="up")


@health_bp.get("/health/rag")
def rag_health():
    if not _authorized_metrics_request():
        return jsonify(error="unauthorized", message="Token de métricas inválido."), 401
    snapshot = rag_pipeline_snapshot()
    return jsonify(snapshot), 200 if snapshot["status"] == "ok" else 503


@health_bp.get("/metrics")
def metrics():
    if not _authorized_metrics_request():
        return Response(status=401)
    from app.communications.whatsapp_pilot import operations_snapshot

    return Response(
        prometheus_metrics(rag_pipeline_snapshot())
        + whatsapp_prometheus_metrics(operations_snapshot(None)),
        content_type="text/plain; version=0.0.4; charset=utf-8",
    )


@health_bp.get("/health/whatsapp")
def whatsapp_health():
    if not _authorized_metrics_request():
        return jsonify(error="unauthorized", message="Token de metricas invalido."), 401
    from app.communications.whatsapp_pilot import operations_snapshot

    snapshot = operations_snapshot(None)
    return jsonify(snapshot), 503 if snapshot["status"] == "PROBLEM" else 200


def _authorized_metrics_request() -> bool:
    expected = current_app.config.get("METRICS_BEARER_TOKEN")
    supplied = request.headers.get("Authorization", "")
    if not expected or not supplied.startswith("Bearer "):
        return False
    return hmac.compare_digest(supplied[7:], expected)
