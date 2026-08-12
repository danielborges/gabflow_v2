import base64
import hashlib
import hmac
import json
import re
import secrets
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol

from flask import current_app
from sqlalchemy import func, select

from app.extensions import db
from app.models import (
    Tenant,
    WhatsAppIntegration,
    WhatsAppIntegrationStatus,
    WhatsAppOnboardingSession,
    WhatsAppOnboardingStatus,
)

LIVE_INTEGRATION_STATUSES = (
    WhatsAppIntegrationStatus.PENDING,
    WhatsAppIntegrationStatus.ACTIVE,
    WhatsAppIntegrationStatus.DEGRADED,
    WhatsAppIntegrationStatus.SUSPENDED,
)
META_ID_PATTERN = re.compile(r"^[0-9]{5,80}$")
IDEMPOTENCY_KEY_PATTERN = re.compile(r"^[A-Za-z0-9._:/+-]{8,128}$")


class WhatsAppOnboardingError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 400):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


class MetaOnboardingError(Exception):
    pass


class SecretBackendUnavailable(Exception):
    pass


@dataclass(frozen=True)
class MetaOnboardingResult:
    business_portfolio_id: str
    waba_id: str
    phone_number_id: str
    display_phone: str | None
    display_name: str | None
    access_token: str
    webhook_subscribed: bool
    phone_registered: bool
    two_step_pin: str


class MetaOnboardingAdapter(Protocol):
    def complete(self, code: str) -> MetaOnboardingResult: ...


class WhatsAppSecretStore(Protocol):
    def put(self, *, tenant_id: uuid.UUID, integration_id: uuid.UUID, value: str) -> str: ...

    def delete(self, reference: str) -> None: ...


class UnconfiguredWhatsAppSecretStore:
    def put(self, *, tenant_id: uuid.UUID, integration_id: uuid.UUID, value: str) -> str:
        del tenant_id, integration_id, value
        raise SecretBackendUnavailable("Cofre de segredos do WhatsApp nao configurado.")

    def delete(self, reference: str) -> None:
        del reference


class GraphMetaOnboardingAdapter:
    def __init__(self, config: dict):
        self.app_id = str(config.get("WHATSAPP_META_APP_ID") or "")
        self.app_secret = str(config.get("META_APP_SECRET") or "")
        self.version = str(config.get("WHATSAPP_GRAPH_API_VERSION") or "")
        self.base_url = str(
            config.get("WHATSAPP_GRAPH_API_BASE_URL") or "https://graph.facebook.com"
        ).rstrip("/")
        if not self.base_url.startswith("https://"):
            raise MetaOnboardingError("A URL da Graph API deve usar HTTPS.")
        self.timeout = float(config.get("WHATSAPP_META_TIMEOUT_SECONDS", 15))

    def complete(self, code: str) -> MetaOnboardingResult:
        token_payload = self._request(
            "POST",
            "/oauth/access_token",
            form={
                "client_id": self.app_id,
                "client_secret": self.app_secret,
                "code": code,
            },
        )
        access_token = str(token_payload.get("access_token") or "")
        if not access_token:
            raise MetaOnboardingError("A Meta nao retornou uma credencial valida.")

        debug = self._request(
            "GET",
            "/debug_token",
            query={"input_token": access_token},
            bearer=f"{self.app_id}|{self.app_secret}",
        ).get("data", {})
        if not debug.get("is_valid"):
            raise MetaOnboardingError("A credencial retornada pela Meta e invalida.")
        waba_ids = self._waba_targets(debug)
        if len(waba_ids) != 1:
            raise MetaOnboardingError(
                "O onboarding deve conceder acesso a exatamente uma conta WhatsApp."
            )
        waba_id = waba_ids[0]

        waba = self._request(
            "GET",
            f"/{waba_id}",
            query={"fields": "id,name,owner_business_info"},
            bearer=access_token,
        )
        owner = waba.get("owner_business_info") or {}
        business_portfolio_id = str(owner.get("id") or "")
        phones = self._request(
            "GET",
            f"/{waba_id}/phone_numbers",
            query={
                "fields": "id,display_phone_number,verified_name,name_status,status,quality_rating",
            },
            bearer=access_token,
        ).get("data", [])
        if len(phones) != 1:
            raise MetaOnboardingError(
                "A conta selecionada deve possuir exatamente um numero autorizado."
            )
        phone = phones[0]
        phone_number_id = str(phone.get("id") or "")
        self._validate_meta_ids(business_portfolio_id, waba_id, phone_number_id)

        two_step_pin = f"{secrets.randbelow(1_000_000):06d}"
        registered = self._request(
            "POST",
            f"/{phone_number_id}/register",
            json_body={"messaging_product": "whatsapp", "pin": two_step_pin},
            bearer=access_token,
        )

        subscribed = self._request(
            "POST",
            f"/{waba_id}/subscribed_apps",
            bearer=access_token,
        )
        return MetaOnboardingResult(
            business_portfolio_id=business_portfolio_id,
            waba_id=waba_id,
            phone_number_id=phone_number_id,
            display_phone=str(phone.get("display_phone_number") or "") or None,
            display_name=str(phone.get("verified_name") or "") or None,
            access_token=access_token,
            webhook_subscribed=subscribed.get("success") is True,
            phone_registered=registered.get("success") in {True, "true"},
            two_step_pin=two_step_pin,
        )

    @staticmethod
    def _waba_targets(debug: dict) -> list[str]:
        targets: set[str] = set()
        for scope in debug.get("granular_scopes") or []:
            if scope.get("scope") not in {
                "whatsapp_business_management",
                "whatsapp_business_messaging",
            }:
                continue
            targets.update(str(item) for item in scope.get("target_ids") or [])
        return sorted(target for target in targets if META_ID_PATTERN.fullmatch(target))

    @staticmethod
    def _validate_meta_ids(*values: str) -> None:
        if not all(META_ID_PATTERN.fullmatch(value) for value in values):
            raise MetaOnboardingError("A Meta retornou identificadores invalidos.")

    def _request(
        self,
        method: str,
        path: str,
        *,
        query: dict | None = None,
        form: dict | None = None,
        json_body: dict | None = None,
        bearer: str | None = None,
    ) -> dict:
        url = f"{self.base_url}/{self.version}{path}"
        if query:
            url = f"{url}?{urllib.parse.urlencode(query)}"
        data = None
        content_type = "application/x-www-form-urlencoded"
        if form:
            data = urllib.parse.urlencode(form).encode()
        elif json_body is not None:
            data = json.dumps(json_body).encode()
            content_type = "application/json"
        headers = {"Accept": "application/json", "Content-Type": content_type}
        if bearer:
            headers["Authorization"] = f"Bearer {bearer}"
        request = urllib.request.Request(  # noqa: S310 - base URL is restricted to HTTPS
            url,
            data=data,
            method=method,
            headers=headers,
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:  # noqa: S310
                payload = json.loads(response.read().decode("utf-8"))
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, ValueError) as exc:
            raise MetaOnboardingError("Nao foi possivel concluir o onboarding na Meta.") from exc
        if not isinstance(payload, dict) or payload.get("error"):
            raise MetaOnboardingError("A Meta rejeitou uma etapa do onboarding.")
        return payload


def get_meta_onboarding_adapter() -> MetaOnboardingAdapter:
    return current_app.extensions.get("whatsapp_meta_onboarding_adapter") or (
        GraphMetaOnboardingAdapter(current_app.config)
    )


def get_whatsapp_secret_store() -> WhatsAppSecretStore:
    configured = current_app.extensions.get("whatsapp_secret_store")
    if configured:
        return configured
    backend = str(current_app.config.get("WHATSAPP_SECRET_BACKEND") or "").lower()
    if backend == "aws-secrets-manager":
        from app.communications.aws_secret_store import AWSSecretsManagerWhatsAppStore

        store = AWSSecretsManagerWhatsAppStore(current_app.config)
        current_app.extensions["whatsapp_secret_store"] = store
        return store
    return UnconfiguredWhatsAppSecretStore()


def normalize_idempotency_key(value: str | None) -> str:
    key = str(value or "").strip()
    if not IDEMPOTENCY_KEY_PATTERN.fullmatch(key):
        raise WhatsAppOnboardingError(
            "invalid_idempotency_key",
            "Informe Idempotency-Key valido entre 8 e 128 caracteres.",
        )
    return key


def build_onboarding_state(session: WhatsAppOnboardingSession, secret_key: str) -> str:
    if not session.state_nonce:
        raise WhatsAppOnboardingError("invalid_state", "Sessao de onboarding indisponivel.")
    payload = f"{session.id}.{session.state_nonce}"
    signature = hmac.new(secret_key.encode(), payload.encode(), hashlib.sha256).digest()
    encoded_signature = base64.urlsafe_b64encode(signature).decode().rstrip("=")
    return f"{payload}.{encoded_signature}"


def hash_onboarding_state(state: str) -> str:
    return hashlib.sha256(state.encode()).hexdigest()


def create_onboarding_session(
    *,
    tenant: Tenant,
    user_id: uuid.UUID,
    idempotency_key: str,
) -> tuple[WhatsAppOnboardingSession, bool]:
    existing = db.session.execute(
        select(WhatsAppOnboardingSession).where(
            WhatsAppOnboardingSession.tenant_id == tenant.id,
            WhatsAppOnboardingSession.idempotency_key == idempotency_key,
        )
    ).scalar_one_or_none()
    if existing:
        if existing.initiated_by_id != user_id:
            raise WhatsAppOnboardingError(
                "idempotency_conflict",
                "A chave de idempotencia ja foi utilizada.",
                409,
            )
        return existing, False

    conflict = db.session.execute(
        select(WhatsAppIntegration.id).where(
            WhatsAppIntegration.tenant_id == tenant.id,
            WhatsAppIntegration.status.in_(LIVE_INTEGRATION_STATUSES),
        )
    ).first()
    if conflict:
        raise WhatsAppOnboardingError(
            "integration_conflict",
            "O gabinete ja possui uma integracao WhatsApp em andamento ou conectada.",
            409,
        )

    session = WhatsAppOnboardingSession(
        tenant_id=tenant.id,
        initiated_by_id=user_id,
        idempotency_key=idempotency_key,
        state_nonce=secrets.token_urlsafe(32),
        state_hash=secrets.token_hex(32),
        expires_at=datetime.now(UTC)
        + timedelta(seconds=int(current_app.config["WHATSAPP_ONBOARDING_SESSION_TTL_SECONDS"])),
    )
    db.session.add(session)
    db.session.flush()
    state = build_onboarding_state(session, str(current_app.config["SECRET_KEY"]))
    session.state_hash = hash_onboarding_state(state)
    return session, True


def validate_onboarding_state(*, tenant_id: uuid.UUID, state: str) -> WhatsAppOnboardingSession:
    parts = state.split(".")
    if len(parts) != 3:
        raise WhatsAppOnboardingError("invalid_state", "Estado de onboarding invalido.")
    try:
        session_id = uuid.UUID(parts[0])
    except ValueError:
        raise WhatsAppOnboardingError("invalid_state", "Estado de onboarding invalido.") from None
    session = db.session.execute(
        select(WhatsAppOnboardingSession).where(
            WhatsAppOnboardingSession.id == session_id,
            WhatsAppOnboardingSession.tenant_id == tenant_id,
        )
    ).scalar_one_or_none()
    if session is None or not session.state_nonce:
        raise WhatsAppOnboardingError("invalid_state", "Estado de onboarding invalido.")
    expected = build_onboarding_state(session, str(current_app.config["SECRET_KEY"]))
    if not hmac.compare_digest(expected, state) or not hmac.compare_digest(
        session.state_hash, hash_onboarding_state(state)
    ):
        raise WhatsAppOnboardingError("invalid_state", "Estado de onboarding invalido.")
    now = datetime.now(UTC)
    expires_at = session.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if expires_at <= now:
        if session.status == WhatsAppOnboardingStatus.PENDING:
            session.status = WhatsAppOnboardingStatus.EXPIRED
        raise WhatsAppOnboardingError("expired_state", "Sessao de onboarding expirada.")
    if session.status != WhatsAppOnboardingStatus.PENDING:
        raise WhatsAppOnboardingError("state_already_used", "Sessao de onboarding ja utilizada.")
    return session


def next_integration_version(tenant_id: uuid.UUID) -> int:
    current = db.session.execute(
        select(func.max(WhatsAppIntegration.version)).where(
            WhatsAppIntegration.tenant_id == tenant_id
        )
    ).scalar_one()
    return int(current or 0) + 1


def resolve_active_whatsapp_tenant(phone_number_id: str) -> uuid.UUID | None:
    matches = (
        db.session.execute(
            select(WhatsAppIntegration.tenant_id).where(
                WhatsAppIntegration.phone_number_id == phone_number_id,
                WhatsAppIntegration.status == WhatsAppIntegrationStatus.ACTIVE,
            )
        )
        .scalars()
        .all()
    )
    return matches[0] if len(matches) == 1 else None


def integration_data(integration: WhatsAppIntegration) -> dict:
    return {
        "id": str(integration.id),
        "tenantId": str(integration.tenant_id),
        "status": integration.status.value,
        "version": integration.version,
        "displayPhone": integration.display_phone,
        "displayName": integration.display_name,
        "connectedAt": integration.connected_at.isoformat() if integration.connected_at else None,
        "disconnectedAt": (
            integration.disconnected_at.isoformat() if integration.disconnected_at else None
        ),
        "webhookSubscribed": integration.webhook_subscribed_at is not None,
    }
