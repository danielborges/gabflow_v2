from sqlalchemy import select

from app.communications.whatsapp_pilot import PILOT_GATES
from app.extensions import db
from app.models import Tenant, WhatsAppPilotControl, WhatsAppPilotGate


def _login(client):
    response = client.post(
        "/api/v1/auth/login",
        json={
            "tenant": "gabinete-a",
            "email": "admin@teste.local",
            "password": "SenhaForte123!",
        },
    )
    assert response.status_code == 200
    return client.get_cookie("csrf_access_token").value


def _pilot_ready_config(app):
    app.config.update(
        APP_ENV="production",
        WHATSAPP_PLATFORM_ENABLED=True,
        WHATSAPP_EMBEDDED_SIGNUP_ENABLED=True,
        WHATSAPP_ROLLOUT_STAGE="pilot",
        WHATSAPP_PILOT_TENANT_SLUGS=("gabinete-a",),
        WHATSAPP_META_APP_ID="app-id",
        WHATSAPP_META_CONFIGURATION_ID="configuration-id",
        WHATSAPP_GRAPH_API_VERSION="v99.0",
        WHATSAPP_META_REDIRECT_URI="https://gabflow.test/meta/callback",
        META_APP_SECRET="meta-secret",  # noqa: S106
        WHATSAPP_WEBHOOK_VERIFY_TOKEN="verify-token",  # noqa: S106
        WHATSAPP_SECRET_BACKEND="aws-secrets-manager",  # noqa: S106
        WHATSAPP_SECRET_BACKEND_READY=True,
        WHATSAPP_AWS_KMS_KEY_ID="alias/gabflow-production-application",
        WHATSAPP_AWS_SECRET_PREFIX="gabflow/production/whatsapp",  # noqa: S106
        WHATSAPP_INBOUND_QUEUE_BACKEND="aws-sqs",
        WHATSAPP_AWS_SQS_QUEUE_URL="https://sqs.sa-east-1.amazonaws.com/123/inbound.fifo",
        WHATSAPP_META_BUSINESS_VERIFIED=True,
        WHATSAPP_META_TECH_PROVIDER_APPROVED=True,
        WHATSAPP_META_APP_REVIEW_APPROVED=True,
        WHATSAPP_PRIVACY_REVIEW_APPROVED=True,
        WHATSAPP_DPA_APPROVED=True,
    )


def _tenant_id(app, slug="gabinete-a"):
    with app.app_context():
        return db.session.scalar(select(Tenant.id).where(Tenant.slug == slug))


def test_pilot_requires_evidence_and_all_gates_before_start(app, client):
    _pilot_ready_config(app)
    csrf = _login(client)
    tenant_id = _tenant_id(app)

    rejected = client.put(
        f"/api/v1/tenants/{tenant_id}/whatsapp/pilot/gates/{PILOT_GATES[0][0]}",
        json={"status": "PASSED"},
        headers={"X-CSRF-TOKEN": csrf},
    )
    assert rejected.status_code == 422

    premature = client.post(
        f"/api/v1/tenants/{tenant_id}/whatsapp/pilot/actions",
        json={"action": "START"},
        headers={"X-CSRF-TOKEN": csrf},
    )
    assert premature.status_code == 422

    for gate_key, _ in PILOT_GATES:
        response = client.put(
            f"/api/v1/tenants/{tenant_id}/whatsapp/pilot/gates/{gate_key}",
            json={"status": "PASSED", "evidenciaReferencia": f"ticket:{gate_key}"},
            headers={"X-CSRF-TOKEN": csrf},
        )
        assert response.status_code == 200

    started = client.post(
        f"/api/v1/tenants/{tenant_id}/whatsapp/pilot/actions",
        json={"action": "START"},
        headers={"X-CSRF-TOKEN": csrf},
    )
    assert started.status_code == 200
    assert started.json["status"] == "RUNNING"
    assert started.json["saidasPausadas"] is False

    with app.app_context():
        gates = list(db.session.scalars(select(WhatsAppPilotGate)))
        assert all(item.evidence_hash and len(item.evidence_hash) == 64 for item in gates)


def test_pause_is_audited_control_and_tenant_isolation_is_enforced(app, client):
    csrf = _login(client)
    tenant_id = _tenant_id(app)
    other_tenant_id = _tenant_id(app, "gabinete-b")

    response = client.post(
        f"/api/v1/tenants/{tenant_id}/whatsapp/pilot/actions",
        json={"action": "PAUSE", "reason": "Taxa de falha acima do limite"},
        headers={"X-CSRF-TOKEN": csrf},
    )
    assert response.status_code == 200
    assert response.json["status"] == "PAUSED"
    assert response.json["saidasPausadas"] is True

    hidden = client.get(f"/api/v1/tenants/{other_tenant_id}/whatsapp/pilot")
    assert hidden.status_code == 404
    with app.app_context():
        control = db.session.scalar(select(WhatsAppPilotControl))
        assert control.pause_reason == "Taxa de falha acima do limite"


def test_whatsapp_health_and_prometheus_metrics_are_protected(app, client):
    unauthorized = client.get("/api/v1/health/whatsapp")
    assert unauthorized.status_code == 401

    response = client.get(
        "/api/v1/health/whatsapp",
        headers={"Authorization": f"Bearer {app.config['METRICS_BEARER_TOKEN']}"},
    )
    assert response.status_code == 200
    assert response.json["status"] == "GOOD"

    metrics = client.get(
        "/api/v1/metrics",
        headers={"Authorization": f"Bearer {app.config['METRICS_BEARER_TOKEN']}"},
    )
    assert metrics.status_code == 200
    assert "gabflow_whatsapp_pipeline_healthy 1" in metrics.text
    assert "tenant" not in metrics.text.lower()
