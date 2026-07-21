import base64
import binascii
import hashlib
import hmac
import json
import time
import uuid
from dataclasses import dataclass
from http.client import HTTPException, HTTPSConnection

from flask import current_app


class EmailDeliveryError(RuntimeError):
    def __init__(self, message: str, *, retryable: bool = True) -> None:
        super().__init__(message)
        self.retryable = retryable


class WebhookVerificationError(ValueError):
    pass


@dataclass(frozen=True)
class EmailDelivery:
    provider: str
    message_id: str


def send_email(
    *,
    recipient: str,
    subject: str,
    text: str,
    idempotency_key: str,
) -> EmailDelivery:
    api_key = current_app.config.get("RESEND_API_KEY")
    sender = current_app.config.get("RESEND_FROM_EMAIL")
    if not api_key or not sender:
        raise EmailDeliveryError(
            "O envio de e-mail ainda não está configurado.",
            retryable=False,
        )

    payload = json.dumps(
        {
            "from": sender,
            "to": [recipient],
            "subject": subject,
            "text": text,
            "tags": [{"name": "application", "value": "gabflow"}],
        }
    ).encode("utf-8")
    connection = HTTPSConnection(
        "api.resend.com", timeout=current_app.config["RESEND_TIMEOUT_SECONDS"]
    )
    try:
        connection.request(
            "POST",
            "/emails",
            body=payload,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "Idempotency-Key": idempotency_key,
                "User-Agent": "GabFlow/1.0",
            },
        )
        response = connection.getresponse()
        body = response.read()
        if response.status >= 400:
            current_app.logger.warning(
                "Resend rejected an email with status %s.", response.status
            )
            retryable = response.status in {408, 429} or response.status >= 500
            raise EmailDeliveryError(
                "O provedor recusou o envio do e-mail.",
                retryable=retryable,
            )
        result = json.loads(body.decode("utf-8"))
    except EmailDeliveryError:
        raise
    except (OSError, HTTPException, TimeoutError, json.JSONDecodeError):
        current_app.logger.exception("Resend email delivery failed.")
        raise EmailDeliveryError("O provedor de e-mail está indisponível.") from None
    finally:
        connection.close()

    message_id = result.get("id")
    if not message_id:
        raise EmailDeliveryError("O provedor não confirmou o envio do e-mail.")
    return EmailDelivery(provider="RESEND", message_id=str(message_id))


def retrieve_received_email(email_id: str) -> dict | None:
    api_key = current_app.config.get("RESEND_API_KEY")
    if not api_key:
        return None

    connection = HTTPSConnection(
        "api.resend.com", timeout=current_app.config["RESEND_TIMEOUT_SECONDS"]
    )
    try:
        connection.request(
            "GET",
            f"/emails/receiving/{email_id}",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Accept": "application/json",
                "User-Agent": "GabFlow/1.0",
            },
        )
        response = connection.getresponse()
        body = response.read()
        if response.status >= 400:
            current_app.logger.warning(
                "Resend rejected received-email lookup %s with status %s.",
                email_id,
                response.status,
            )
            return None
        return json.loads(body.decode("utf-8"))
    except (OSError, HTTPException, TimeoutError, json.JSONDecodeError):
        current_app.logger.exception("Resend received-email lookup failed.")
        return None
    finally:
        connection.close()


def verify_resend_webhook(
    raw_body: bytes,
    headers,
    secret: str,
    *,
    tolerance_seconds: int,
) -> dict:
    message_id = headers.get("svix-id")
    timestamp = headers.get("svix-timestamp")
    signature = headers.get("svix-signature")
    if not message_id or not timestamp or not signature:
        raise WebhookVerificationError("CabeÃ§alhos Svix ausentes.")

    try:
        timestamp_int = int(timestamp)
    except (TypeError, ValueError):
        raise WebhookVerificationError("Timestamp Svix invÃ¡lido.") from None
    if abs(time.time() - timestamp_int) > tolerance_seconds:
        raise WebhookVerificationError("Timestamp Svix expirado.")

    expected_signature = _svix_signature(secret, message_id, timestamp, raw_body)
    provided_signatures = [
        value.removeprefix("v1,")
        for value in str(signature).split()
        if value.startswith("v1,")
    ]
    if not any(
        hmac.compare_digest(expected_signature, provided)
        for provided in provided_signatures
    ):
        raise WebhookVerificationError("Assinatura Svix invÃ¡lida.")

    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise WebhookVerificationError("Payload JSON invÃ¡lido.") from None
    if not isinstance(payload, dict):
        raise WebhookVerificationError("Payload JSON invÃ¡lido.")
    return payload


def _svix_signature(secret: str, message_id: str, timestamp: str, raw_body: bytes) -> str:
    secret_value = secret.removeprefix("whsec_")
    padding = "=" * (-len(secret_value) % 4)
    try:
        key = base64.b64decode(f"{secret_value}{padding}")
    except (binascii.Error, ValueError):
        raise WebhookVerificationError("Segredo Svix invÃ¡lido.") from None
    signed_content = b".".join(
        [message_id.encode("utf-8"), timestamp.encode("utf-8"), raw_body]
    )
    digest = hmac.new(key, signed_content, hashlib.sha256).digest()
    return base64.b64encode(digest).decode("utf-8")


def email_idempotency_key(event_id: uuid.UUID) -> str:
    return f"gabflow-email-{event_id}"
