import base64
import hashlib
import hmac
import re
import uuid
from datetime import date

from flask import current_app

from app.security.encryption import decrypt_for_scope, encrypt_for_scope


def normalize_digits(value: object) -> str:
    return re.sub(r"\D", "", str(value or ""))


def normalize_cpf(value: object) -> str | None:
    digits = normalize_digits(value)
    return digits or None


def valid_cpf(value: object) -> bool:
    digits = normalize_digits(value)
    if len(digits) != 11 or digits == digits[0] * 11:
        return False
    for size in (9, 10):
        total = sum(
            int(digit) * weight
            for digit, weight in zip(
                digits[:size], range(size + 1, 1, -1), strict=True
            )
        )
        verifier = (total * 10 % 11) % 10
        if verifier != int(digits[size]):
            return False
    return True


def cpf_fingerprint(tenant_id: uuid.UUID, cpf: str) -> str:
    version = int(current_app.config["CITIZEN_IDENTITY_HMAC_KEY_VERSION"])
    secret = str(current_app.config["CITIZEN_IDENTITY_HMAC_KEY"]).encode("utf-8")
    message = f"citizen-cpf:{tenant_id}:v{version}:{cpf}".encode()
    return hmac.new(secret, message, hashlib.sha256).hexdigest()


def encrypt_document(tenant_id: uuid.UUID, kind: str, value: str | None) -> str | None:
    if not value:
        return None
    encrypted = encrypt_for_scope(value.encode("utf-8"), _scope(tenant_id, kind))
    return base64.urlsafe_b64encode(encrypted).decode("ascii")


def decrypt_document(tenant_id: uuid.UUID, kind: str, value: str | None) -> str | None:
    if not value:
        return None
    encrypted = base64.urlsafe_b64decode(value.encode("ascii"))
    return decrypt_for_scope(encrypted, _scope(tenant_id, kind)).decode("utf-8")


def parse_birth_date(value: object) -> date | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = date.fromisoformat(text)
    except ValueError as error:
        raise ValueError("Informe uma data de nascimento válida.") from error
    if parsed > date.today():
        raise ValueError("A data de nascimento não pode estar no futuro.")
    return parsed


def normalize_electoral_title(value: object) -> str | None:
    digits = normalize_digits(value)
    if not digits:
        return None
    if len(digits) != 12:
        raise ValueError("Informe um título de eleitor com 12 dígitos.")
    return digits


def _scope(tenant_id: uuid.UUID, kind: str) -> str:
    return f"tenant:{tenant_id}:citizen:{kind}"
