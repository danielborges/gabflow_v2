from app.communications.whatsapp_readiness import whatsapp_readiness_data
from app.extensions import db
from app.models import Tenant


def configured_readiness(**overrides):
    config = {
        "APP_ENV": "homologation",
        "WHATSAPP_PLATFORM_ENABLED": True,
        "WHATSAPP_EMBEDDED_SIGNUP_ENABLED": True,
        "WHATSAPP_ROLLOUT_STAGE": "sandbox",
        "WHATSAPP_PILOT_TENANT_SLUGS": ("gabinete-a",),
        "WHATSAPP_META_APP_ID": "meta-app-id",
        "WHATSAPP_META_CONFIGURATION_ID": "configuration-id",
        "WHATSAPP_GRAPH_API_VERSION": "v99.0",
        "WHATSAPP_META_REDIRECT_URI": "https://app.gabflow.test/meta/callback",
        "META_APP_SECRET": "secret-for-test",
        "WHATSAPP_WEBHOOK_VERIFY_TOKEN": "verify-token-for-test",
        "WHATSAPP_SECRET_BACKEND": "environment",
        "WHATSAPP_SECRET_BACKEND_READY": False,
        "WHATSAPP_AWS_KMS_KEY_ID": "alias/gabflow-production-application",
        "WHATSAPP_AWS_SECRET_PREFIX": "gabflow/production/whatsapp",
        "WHATSAPP_INBOUND_QUEUE_BACKEND": "aws-sqs",
        "WHATSAPP_AWS_SQS_QUEUE_URL": "https://sqs.sa-east-1.amazonaws.com/123/inbound.fifo",
        "WHATSAPP_WEBHOOK_PAYLOAD_RETENTION_DAYS": 7,
        "WHATSAPP_META_BUSINESS_VERIFIED": False,
        "WHATSAPP_META_TECH_PROVIDER_APPROVED": False,
        "WHATSAPP_META_APP_REVIEW_APPROVED": False,
        "WHATSAPP_PRIVACY_REVIEW_APPROVED": False,
        "WHATSAPP_DPA_APPROVED": False,
    }
    config.update(overrides)
    return config


def login(client):
    return client.post(
        "/api/v1/auth/login",
        json={
            "tenant": "gabinete-a",
            "email": "admin@teste.local",
            "password": "SenhaForte123!",
        },
    )


def test_readiness_distinguishes_sandbox_and_external_pilot_gates():
    report = whatsapp_readiness_data(configured_readiness(), "gabinete-a")

    assert report["tenantHabilitado"] is True
    assert report["prontoSandbox"] is True
    assert report["prontoPiloto"] is False
    assert "whatsapp_meta_app_review_approved" in report["pendencias"]


def test_production_requires_external_secret_backend():
    report = whatsapp_readiness_data(
        configured_readiness(
            APP_ENV="production",
            WHATSAPP_META_BUSINESS_VERIFIED=True,
            WHATSAPP_META_TECH_PROVIDER_APPROVED=True,
            WHATSAPP_META_APP_REVIEW_APPROVED=True,
            WHATSAPP_PRIVACY_REVIEW_APPROVED=True,
            WHATSAPP_DPA_APPROVED=True,
        ),
        "gabinete-a",
    )

    assert report["prontoPiloto"] is False
    assert "secret_backend" in report["pendencias"]


def test_readiness_endpoint_never_exposes_configuration_values(app, client):
    assert login(client).status_code == 200
    app.config.update(configured_readiness())
    with app.app_context():
        tenant_id = db.session.execute(
            db.select(Tenant.id).where(Tenant.slug == "gabinete-a")
        ).scalar_one()

    response = client.get(f"/api/v1/tenants/{tenant_id}/whatsapp/readiness")

    assert response.status_code == 200
    serialized = response.get_data(as_text=True)
    assert response.json["prontoSandbox"] is True
    assert "secret-for-test" not in serialized
    assert "configuration-id" not in serialized


def test_pilot_can_only_be_ready_with_all_external_gates():
    report = whatsapp_readiness_data(
        configured_readiness(
            APP_ENV="production",
            WHATSAPP_ROLLOUT_STAGE="pilot",
            WHATSAPP_SECRET_BACKEND_READY=True,
            WHATSAPP_META_BUSINESS_VERIFIED=True,
            WHATSAPP_META_TECH_PROVIDER_APPROVED=True,
            WHATSAPP_META_APP_REVIEW_APPROVED=True,
            WHATSAPP_PRIVACY_REVIEW_APPROVED=True,
            WHATSAPP_DPA_APPROVED=True,
            **{"WHATSAPP_SECRET_BACKEND": "aws-secrets-manager"},
        ),
        "gabinete-a",
    )

    assert report["prontoSandbox"] is True
    assert report["prontoPiloto"] is True


def test_readiness_endpoint_hides_another_tenant(app, client):
    assert login(client).status_code == 200
    with app.app_context():
        tenant_id = db.session.execute(
            db.select(Tenant.id).where(Tenant.slug == "gabinete-b")
        ).scalar_one()

    response = client.get(f"/api/v1/tenants/{tenant_id}/whatsapp/readiness")

    assert response.status_code == 404
