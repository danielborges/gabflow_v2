import json
from datetime import UTC, datetime, timedelta

from app.communications.whatsapp_onboarding import (
    GraphMetaOnboardingAdapter,
    MetaOnboardingResult,
    get_whatsapp_secret_store,
    resolve_active_whatsapp_tenant,
)
from app.extensions import db
from app.models import (
    Tenant,
    User,
    WhatsAppIntegration,
    WhatsAppIntegrationStatus,
    WhatsAppOnboardingSession,
    WhatsAppOnboardingStatus,
)


class FakeMetaOnboardingAdapter:
    def __init__(self, *, phone_number_id="3333333333"):
        self.phone_number_id = phone_number_id
        self.codes = []

    def complete(self, code):
        self.codes.append(code)
        return MetaOnboardingResult(
            business_portfolio_id="1111111111",
            waba_id="2222222222",
            phone_number_id=self.phone_number_id,
            display_phone="+55 32 99999-0000",
            display_name="Gabinete A",
            access_token="meta-access-token-must-not-leak",  # noqa: S106
            webhook_subscribed=True,
            phone_registered=True,
            two_step_pin="123456",  # noqa: S106
        )


class FakeSecretStore:
    def __init__(self):
        self.values = {}

    def put(self, *, tenant_id, integration_id, value):
        reference = f"vault://whatsapp/{tenant_id}/{integration_id}"
        self.values[reference] = value
        return reference

    def delete(self, reference):
        self.values.pop(reference, None)


class RecordingGraphAdapter(GraphMetaOnboardingAdapter):
    def __init__(self):
        super().__init__(
            {
                "WHATSAPP_META_APP_ID": "1234567890",
                "META_APP_SECRET": "app-secret",  # noqa: S106
                "WHATSAPP_GRAPH_API_VERSION": "v99.0",
            }
        )
        self.calls = []

    def _request(self, method, path, **kwargs):
        self.calls.append((method, path, kwargs))
        if path == "/oauth/access_token":
            return {"access_token": "access-token"}
        if path == "/debug_token":
            return {
                "data": {
                    "is_valid": True,
                    "granular_scopes": [
                        {
                            "scope": "whatsapp_business_management",
                            "target_ids": ["2222222222"],
                        }
                    ],
                }
            }
        if path == "/2222222222":
            return {"id": "2222222222", "owner_business_info": {"id": "1111111111"}}
        if path == "/2222222222/phone_numbers":
            return {
                "data": [
                    {
                        "id": "3333333333",
                        "display_phone_number": "+55 32 99999-0000",
                        "verified_name": "Gabinete A",
                    }
                ]
            }
        if path in {"/3333333333/register", "/2222222222/subscribed_apps"}:
            return {"success": True}
        raise AssertionError(path)


def login(
    client,
    *,
    tenant="gabinete-a",
    email="admin@teste.local",
    password="SenhaForte123!",  # noqa: S107
):
    return client.post(
        "/api/v1/auth/login",
        json={"tenant": tenant, "email": email, "password": password},
    )


def configure_onboarding(app):
    app.config.update(
        WHATSAPP_PLATFORM_ENABLED=True,
        WHATSAPP_EMBEDDED_SIGNUP_ENABLED=True,
        WHATSAPP_ROLLOUT_STAGE="sandbox",
        WHATSAPP_PILOT_TENANT_SLUGS=("gabinete-a",),
        WHATSAPP_META_APP_ID="1234567890",
        WHATSAPP_META_CONFIGURATION_ID="9876543210",
        WHATSAPP_GRAPH_API_VERSION="v99.0",
        WHATSAPP_META_REDIRECT_URI="https://app.gabflow.test/meta/callback",
        META_APP_SECRET="app-secret",  # noqa: S106
        WHATSAPP_WEBHOOK_VERIFY_TOKEN="verify-token",  # noqa: S106
    )
    adapter = FakeMetaOnboardingAdapter()
    secret_store = FakeSecretStore()
    app.extensions["whatsapp_meta_onboarding_adapter"] = adapter
    app.extensions["whatsapp_secret_store"] = secret_store
    return adapter, secret_store


def tenant_id(app, slug="gabinete-a"):
    with app.app_context():
        return db.session.execute(db.select(Tenant.id).where(Tenant.slug == slug)).scalar_one()


def start_session(client, tenant_uuid, key="onboarding-request-001"):
    return client.post(
        f"/api/v1/tenants/{tenant_uuid}/whatsapp/onboarding-sessions",
        headers={
            "Idempotency-Key": key,
            "X-CSRF-TOKEN": client.get_cookie("csrf_access_token").value,
        },
    )


def test_graph_adapter_registers_phone_and_subscribes_waba():
    adapter = RecordingGraphAdapter()

    result = adapter.complete("single-use-code")

    assert result.phone_registered is True
    assert result.webhook_subscribed is True
    assert len(result.two_step_pin) == 6
    assert result.two_step_pin.isdigit()
    register_call = next(call for call in adapter.calls if call[1].endswith("/register"))
    assert register_call[2]["json_body"] == {
        "messaging_product": "whatsapp",
        "pin": result.two_step_pin,
    }
    assert register_call[2]["bearer"] == "access-token"


def test_secret_store_factory_selects_aws_backend(app):
    fake_store = FakeSecretStore()
    app.config.update(
        WHATSAPP_SECRET_BACKEND="aws-secrets-manager",  # noqa: S106
        WHATSAPP_AWS_KMS_KEY_ID="alias/gabflow-test-application",
    )
    with app.app_context():
        app.extensions["whatsapp_secret_store"] = fake_store
        assert get_whatsapp_secret_store() is fake_store


def complete_session(client, tenant_uuid, payload):
    return client.post(
        f"/api/v1/tenants/{tenant_uuid}/whatsapp/onboarding-callback",
        json=payload,
        headers={"X-CSRF-TOKEN": client.get_cookie("csrf_access_token").value},
    )


def test_onboarding_session_is_tenant_scoped_and_idempotent(app, client):
    configure_onboarding(app)
    assert login(client).status_code == 200
    current_tenant_id = tenant_id(app)

    first = start_session(client, current_tenant_id)
    repeated = start_session(client, current_tenant_id)

    assert first.status_code == 201
    assert repeated.status_code == 200
    assert repeated.json == first.json
    assert first.json["configurationId"] == "9876543210"
    serialized = first.get_data(as_text=True)
    assert "app-secret" not in serialized
    assert "verify-token" not in serialized


def test_onboarding_is_blocked_when_increment_zero_gates_are_closed(app, client):
    assert login(client).status_code == 200
    response = start_session(client, tenant_id(app))

    assert response.status_code == 503
    assert response.json["error"] == "whatsapp_not_ready"


def test_onboarding_hides_another_tenant(app, client):
    configure_onboarding(app)
    assert login(client).status_code == 200

    response = start_session(client, tenant_id(app, "gabinete-b"))

    assert response.status_code == 404


def test_callback_creates_pending_version_and_stores_only_secret_reference(app, client):
    adapter, secret_store = configure_onboarding(app)
    assert login(client).status_code == 200
    current_tenant_id = tenant_id(app)
    session = start_session(client, current_tenant_id)

    response = complete_session(
        client,
        current_tenant_id,
        {"code": "single-use-meta-code", "state": session.json["state"]},
    )

    assert response.status_code == 202
    assert response.json["status"] == "PENDING"
    assert response.json["version"] == 1
    assert adapter.codes == ["single-use-meta-code"]
    secret_bundle = json.loads(next(iter(secret_store.values.values())))
    assert secret_bundle == {
        "access_token": "meta-access-token-must-not-leak",
        "two_step_pin": "123456",
    }
    assert "meta-access-token-must-not-leak" not in response.get_data(as_text=True)
    assert "123456" not in response.get_data(as_text=True)
    with app.app_context():
        integration = db.session.execute(db.select(WhatsAppIntegration)).scalar_one()
        onboarding = db.session.execute(db.select(WhatsAppOnboardingSession)).scalar_one()
        assert integration.token_secret_ref.startswith("vault://")
        assert onboarding.status == WhatsAppOnboardingStatus.COMPLETED
        assert onboarding.state_nonce is None


def test_callback_state_is_single_use(app, client):
    configure_onboarding(app)
    assert login(client).status_code == 200
    current_tenant_id = tenant_id(app)
    session = start_session(client, current_tenant_id)
    payload = {"code": "single-use-meta-code", "state": session.json["state"]}

    assert complete_session(client, current_tenant_id, payload).status_code == 202
    repeated = complete_session(client, current_tenant_id, payload)

    assert repeated.status_code == 400
    assert repeated.json["error"] == "invalid_state"


def test_callback_fails_closed_when_secret_backend_is_unavailable(app, client):
    configure_onboarding(app)
    app.extensions.pop("whatsapp_secret_store")
    assert login(client).status_code == 200
    current_tenant_id = tenant_id(app)
    session = start_session(client, current_tenant_id)

    response = complete_session(
        client,
        current_tenant_id,
        {"code": "single-use-meta-code", "state": session.json["state"]},
    )

    assert response.status_code == 503
    assert response.json["error"] == "secret_backend_unavailable"
    with app.app_context():
        assert db.session.execute(db.select(WhatsAppIntegration)).scalar_one_or_none() is None
        onboarding = db.session.execute(db.select(WhatsAppOnboardingSession)).scalar_one()
        assert onboarding.status == WhatsAppOnboardingStatus.FAILED
        assert onboarding.failure_code == "secret_backend_unavailable"


def test_callback_cannot_claim_phone_from_another_tenant(app, client):
    _, secret_store = configure_onboarding(app)
    assert login(client).status_code == 200
    current_tenant_id = tenant_id(app)
    with app.app_context():
        other_tenant_id = db.session.execute(
            db.select(Tenant.id).where(Tenant.slug == "gabinete-b")
        ).scalar_one()
        other_user_id = db.session.execute(
            db.select(User.id).where(User.tenant_id == other_tenant_id)
        ).scalar_one()
        db.session.add(
            WhatsAppIntegration(
                tenant_id=other_tenant_id,
                business_portfolio_id="4444444444",
                waba_id="5555555555",
                phone_number_id="3333333333",
                status=WhatsAppIntegrationStatus.ACTIVE,
                version=1,
                token_secret_ref="vault://other-tenant",  # noqa: S106
                created_by_id=other_user_id,
            )
        )
        db.session.commit()
    session = start_session(client, current_tenant_id)

    response = complete_session(
        client,
        current_tenant_id,
        {"code": "single-use-meta-code", "state": session.json["state"]},
    )

    assert response.status_code == 409
    assert response.json["error"] == "phone_number_conflict"
    assert secret_store.values == {}
    with app.app_context():
        integrations = db.session.execute(db.select(WhatsAppIntegration)).scalars().all()
        assert len(integrations) == 1
        assert integrations[0].tenant_id == other_tenant_id


def test_expired_session_cannot_be_consumed(app, client):
    configure_onboarding(app)
    assert login(client).status_code == 200
    current_tenant_id = tenant_id(app)
    response = start_session(client, current_tenant_id)
    with app.app_context():
        session = db.session.execute(db.select(WhatsAppOnboardingSession)).scalar_one()
        session.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        db.session.commit()

    callback = complete_session(
        client,
        current_tenant_id,
        {"code": "meta-code", "state": response.json["state"]},
    )

    assert callback.status_code == 400
    assert callback.json["error"] == "expired_state"


def test_active_phone_resolution_never_falls_back_to_another_tenant(app):
    with app.app_context():
        current_tenant_id = db.session.execute(
            db.select(Tenant.id).where(Tenant.slug == "gabinete-a")
        ).scalar_one()
        integration = WhatsAppIntegration(
            tenant_id=current_tenant_id,
            business_portfolio_id="1111111111",
            waba_id="2222222222",
            phone_number_id="3333333333",
            status=WhatsAppIntegrationStatus.ACTIVE,
            version=1,
            token_secret_ref="vault://reference",  # noqa: S106
            created_by_id=db.session.execute(
                db.select(User.id).where(User.tenant_id == current_tenant_id)
            ).scalar_one(),
        )
        db.session.add(integration)
        db.session.commit()

        assert resolve_active_whatsapp_tenant("3333333333") == current_tenant_id
        assert resolve_active_whatsapp_tenant("9999999999") is None
