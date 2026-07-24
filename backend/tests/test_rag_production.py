from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.extensions import db
from app.models import OutboxEvent, RagAssistantQuery, Tenant, User

PASSWORD = "SenhaForte123!"  # noqa: S105
METRICS_HEADERS = {"Authorization": "Bearer test-metrics-token"}


def _login(client):
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@teste.local", "password": PASSWORD},
    )
    assert response.status_code == 200


def test_tenant_rag_quality_metrics_do_not_cross_tenant(app, client):
    with app.app_context():
        users = list(db.session.scalars(select(User).order_by(User.email)))
        for index, user in enumerate(users):
            db.session.add(
                RagAssistantQuery(
                    tenant_id=user.tenant_id,
                    user_id=user.id,
                    query_text=f"consulta {index}",
                    query_hash=f"{index:064d}",
                    response="resposta",
                    sources=[],
                    safety_flags={},
                    grounded=index == 1,
                    refused=index == 0,
                    evidence_threshold=0.42,
                    embedding_model="local",
                    fallback_used=index == 0,
                    latency_ms=100 + index * 100,
                )
            )
        db.session.commit()

    _login(client)
    response = client.get("/api/v1/assistente/metricas")
    assert response.status_code == 200
    assert response.json["consultas"] == 1
    assert response.json["latenciaP95Ms"] in {100, 200}
    assert response.json["fundamentadas"] + response.json["recusadas"] == 1


def test_rag_health_degrades_when_queue_age_exceeds_slo(app, client):
    with app.app_context():
        tenant_id = db.session.scalar(select(Tenant.id))
        db.session.add(
            OutboxEvent(
                tenant_id=tenant_id,
                event_type="SincronizacaoMemoriaOperacional",
                aggregate_type="SERVICE_REQUEST",
                aggregate_id="stalled",
                payload={},
                occurred_at=datetime.now(UTC) - timedelta(hours=1),
            )
        )
        db.session.commit()

    response = client.get("/api/v1/health/rag", headers=METRICS_HEADERS)
    assert response.status_code == 503
    assert response.json["status"] == "degraded"
    assert response.json["queue"]["oldestAgeSeconds"] >= 3500
