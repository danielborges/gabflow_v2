import json
import uuid
from dataclasses import dataclass
from http.client import HTTPException, HTTPSConnection

from flask import current_app


class EmailDeliveryError(RuntimeError):
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
        raise EmailDeliveryError("O envio de e-mail ainda não está configurado.")

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
            raise EmailDeliveryError("O provedor recusou o envio do e-mail.")
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


def new_idempotency_key(request_id: uuid.UUID) -> str:
    return f"gabflow-response-{request_id}-{uuid.uuid4()}"
