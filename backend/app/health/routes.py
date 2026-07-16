from flask import Blueprint, jsonify
from sqlalchemy import text

from app.extensions import db

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
