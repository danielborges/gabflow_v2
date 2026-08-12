import hashlib
import hmac
import json
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.communications.whatsapp_inbound import redact_expired_webhook_payloads
from app.communications.whatsapp_queue import (
    WhatsAppQueueUnavailable,
    reconcile_pending_webhook_events,
)
from app.extensions import db
from app.models import (
    ChannelMessage,
    OutboxEvent,
    Tenant,
    User,
    WhatsAppIntegration,
    WhatsAppIntegrationStatus,
    WhatsAppWebhookEvent,
    WhatsAppWebhookEventStatus,
)
from app.outbox.service import process_batch

TEST_META_SECRET = "meta-secret"  # noqa: S105
WRONG_META_SECRET = "wrong-secret"  # noqa: S105


def _integration(tenant: Tenant, user: User, *, phone_number_id: str, active: bool = True):
    integration = WhatsAppIntegration(
        tenant_id=tenant.id,
        business_portfolio_id="portfolio-1",
        waba_id="waba-1",
        phone_number_id=phone_number_id,
        status=(WhatsAppIntegrationStatus.ACTIVE if active else WhatsAppIntegrationStatus.PENDING),
        version=1,
        token_secret_ref="arn:aws:secretsmanager:sa-east-1:123:secret:test",  # noqa: S106
        created_by_id=user.id,
    )
    db.session.add(integration)
    db.session.commit()
    return integration


def _payload(phone_number_id: str = "phone-1", message_id: str = "wamid.1") -> dict:
    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "waba-1",
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "metadata": {
                                "phone_number_id": phone_number_id,
                                "display_phone_number": "5532999999999",
                            },
                            "contacts": [
                                {"wa_id": "5532888888888", "profile": {"name": "Cidadao"}}
                            ],
                            "messages": [
                                {
                                    "id": message_id,
                                    "from": "5532888888888",
                                    "timestamp": "1786500000",
                                    "type": "text",
                                    "text": {"body": "Preciso de atendimento"},
                                }
                            ],
                        },
                    }
                ],
            }
        ],
    }


def _post(client, payload: dict, secret: str | None = None):
    secret = secret or TEST_META_SECRET
    body = json.dumps(payload, separators=(",", ":")).encode()
    signature = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return client.post(
        "/api/v1/webhooks/meta/whatsapp",
        data=body,
        content_type="application/json",
        headers={"X-Hub-Signature-256": f"sha256={signature}"},
    )


def _login(client):
    return client.post(
        "/api/v1/auth/login",
        json={
            "tenant": "gabinete-a",
            "email": "admin@teste.local",
            "password": "SenhaForte123!",
        },
    )


def test_global_webhook_verification(app, client):
    app.config["WHATSAPP_WEBHOOK_VERIFY_TOKEN"] = "verify-token"  # noqa: S105
    response = client.get(
        "/api/v1/webhooks/meta/whatsapp",
        query_string={
            "hub.mode": "subscribe",
            "hub.verify_token": "verify-token",
            "hub.challenge": "challenge-123",
        },
    )
    assert response.status_code == 200
    assert response.text == "challenge-123"


def test_tenant_health_reports_webhook_and_last_inbound_without_secrets(app, client):
    app.config["META_APP_SECRET"] = TEST_META_SECRET
    with app.app_context():
        tenant = db.session.scalar(select(Tenant).where(Tenant.slug == "gabinete-a"))
        user = db.session.scalar(select(User).where(User.tenant_id == tenant.id))
        integration = _integration(tenant, user, phone_number_id="phone-1")
        integration.webhook_subscribed_at = datetime.now(UTC)
        db.session.commit()
        tenant_id = tenant.id

    assert _post(client, _payload()).status_code == 200
    assert _login(client).status_code == 200
    response = client.get(f"/api/v1/tenants/{tenant_id}/whatsapp/health")

    assert response.status_code == 200
    assert response.json["status"] == "HEALTHY"
    assert response.json["webhook"] is True
    assert response.json["messaging"] is True
    assert response.json["lastInboundAt"] is not None
    serialized = response.get_data(as_text=True)
    assert "token_secret_ref" not in serialized
    assert "arn:aws:secretsmanager" not in serialized


def test_webhook_persists_before_ack_and_processes_asynchronously(app, client):
    app.config["META_APP_SECRET"] = TEST_META_SECRET
    with app.app_context():
        tenant = db.session.scalar(select(Tenant).where(Tenant.slug == "gabinete-a"))
        user = db.session.scalar(select(User).where(User.tenant_id == tenant.id))
        _integration(tenant, user, phone_number_id="phone-1")

    response = _post(client, _payload())
    assert response.status_code == 200
    assert response.json["accepted"] == 1
    assert response.json["quarantined"] == 0

    with app.app_context():
        event = db.session.scalar(select(WhatsAppWebhookEvent))
        assert event.status == WhatsAppWebhookEventStatus.QUEUED
        assert event.ack_duration_ms is not None
        assert event.tenant_id is not None
        assert event.payload_hash
        assert db.session.scalar(select(OutboxEvent)) is not None

        result = process_batch("whatsapp-test-worker")
        assert result.succeeded == 1
        db.session.refresh(event)
        assert event.status == WhatsAppWebhookEventStatus.PROCESSED
        message = db.session.scalar(select(ChannelMessage))
        assert message.external_id == "wamid.1"
        assert message.content == "Preciso de atendimento"
        assert "raw" not in message.metadata_data


def test_duplicate_event_is_acknowledged_without_duplicate_side_effect(app, client):
    app.config["META_APP_SECRET"] = TEST_META_SECRET
    with app.app_context():
        tenant = db.session.scalar(select(Tenant).where(Tenant.slug == "gabinete-a"))
        user = db.session.scalar(select(User).where(User.tenant_id == tenant.id))
        _integration(tenant, user, phone_number_id="phone-1")

    assert _post(client, _payload()).status_code == 200
    duplicate = _post(client, _payload())
    assert duplicate.status_code == 200
    assert duplicate.json["accepted"] == 0
    assert duplicate.json["duplicated"] == 1

    with app.app_context():
        assert len(list(db.session.scalars(select(WhatsAppWebhookEvent)))) == 1
        assert len(list(db.session.scalars(select(OutboxEvent)))) == 1


def test_unknown_phone_number_is_quarantined_without_tenant(app, client):
    app.config["META_APP_SECRET"] = TEST_META_SECRET
    response = _post(client, _payload(phone_number_id="unknown-phone"))
    assert response.status_code == 200
    assert response.json["quarantined"] == 1

    with app.app_context():
        event = db.session.scalar(select(WhatsAppWebhookEvent))
        assert event.status == WhatsAppWebhookEventStatus.QUARANTINED
        assert event.tenant_id is None
        assert event.quarantine_reason == "UNKNOWN_OR_INACTIVE_PHONE_NUMBER"
        assert db.session.scalar(select(OutboxEvent)) is None


def test_pending_integration_does_not_route_event(app, client):
    app.config["META_APP_SECRET"] = TEST_META_SECRET
    with app.app_context():
        tenant = db.session.scalar(select(Tenant).where(Tenant.slug == "gabinete-a"))
        user = db.session.scalar(select(User).where(User.tenant_id == tenant.id))
        _integration(tenant, user, phone_number_id="phone-1", active=False)

    response = _post(client, _payload())
    assert response.status_code == 200
    assert response.json["quarantined"] == 1


def test_phone_number_routes_only_to_owning_tenant(app, client):
    app.config["META_APP_SECRET"] = TEST_META_SECRET
    with app.app_context():
        tenant_a = db.session.scalar(select(Tenant).where(Tenant.slug == "gabinete-a"))
        tenant_b = db.session.scalar(select(Tenant).where(Tenant.slug == "gabinete-b"))
        user_a = db.session.scalar(select(User).where(User.tenant_id == tenant_a.id))
        user_b = db.session.scalar(select(User).where(User.tenant_id == tenant_b.id))
        _integration(tenant_a, user_a, phone_number_id="phone-a")
        _integration(tenant_b, user_b, phone_number_id="phone-b")
        tenant_b_id = tenant_b.id

    assert _post(client, _payload(phone_number_id="phone-b")).status_code == 200
    with app.app_context():
        event = db.session.scalar(select(WhatsAppWebhookEvent))
        assert event.tenant_id == tenant_b_id
        assert process_batch("tenant-routing-worker").succeeded == 1
        message = db.session.scalar(select(ChannelMessage))
        assert message.tenant_id == tenant_b_id


def test_invalid_signature_is_rejected_without_persisting(app, client):
    app.config["META_APP_SECRET"] = TEST_META_SECRET
    response = _post(client, _payload(), secret=WRONG_META_SECRET)
    assert response.status_code == 401
    with app.app_context():
        assert db.session.scalar(select(WhatsAppWebhookEvent)) is None


def test_sqs_outage_does_not_lose_persisted_event_and_reconciliation_recovers(app, client):
    class FailingQueue:
        def publish(self, _event):
            raise WhatsAppQueueUnavailable("queue unavailable")

    class RecordingQueue:
        def __init__(self):
            self.event_ids = []

        def publish(self, event):
            self.event_ids.append(event.id)

    app.config["META_APP_SECRET"] = TEST_META_SECRET
    app.config["WHATSAPP_INBOUND_QUEUE_BACKEND"] = "aws-sqs"
    app.extensions["whatsapp_inbound_queue"] = FailingQueue()
    with app.app_context():
        tenant = db.session.scalar(select(Tenant).where(Tenant.slug == "gabinete-a"))
        user = db.session.scalar(select(User).where(User.tenant_id == tenant.id))
        _integration(tenant, user, phone_number_id="phone-1")

    response = _post(client, _payload())
    assert response.status_code == 200

    with app.app_context():
        event = db.session.scalar(select(WhatsAppWebhookEvent))
        assert event.status == WhatsAppWebhookEventStatus.RECEIVED
        recording_queue = RecordingQueue()
        app.extensions["whatsapp_inbound_queue"] = recording_queue
        assert reconcile_pending_webhook_events() == 1
        db.session.refresh(event)
        assert event.status == WhatsAppWebhookEventStatus.QUEUED
        assert recording_queue.event_ids == [event.id]


def test_expired_raw_payload_is_redacted_but_hash_and_route_are_preserved(app, client):
    app.config["META_APP_SECRET"] = TEST_META_SECRET
    with app.app_context():
        tenant = db.session.scalar(select(Tenant).where(Tenant.slug == "gabinete-a"))
        user = db.session.scalar(select(User).where(User.tenant_id == tenant.id))
        _integration(tenant, user, phone_number_id="phone-1")

    assert _post(client, _payload()).status_code == 200
    with app.app_context():
        event = db.session.scalar(select(WhatsAppWebhookEvent))
        original_hash = event.payload_hash
        tenant_id = event.tenant_id
        event.retention_until = datetime.now(UTC) - timedelta(seconds=1)
        db.session.commit()

        assert redact_expired_webhook_payloads() == 1
        db.session.commit()
        db.session.refresh(event)
        assert event.payload == {}
        assert event.payload_redacted_at is not None
        assert event.payload_hash == original_hash
        assert event.tenant_id == tenant_id
