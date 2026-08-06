from datetime import datetime

from flask import current_app
from itsdangerous import BadData, URLSafeSerializer


class CursorError(ValueError):
    pass


def encode_cursor(kind: str, **values) -> str:
    return _serializer().dumps({"kind": kind, **values})


def decode_cursor(value: str | None, kind: str) -> dict | None:
    if not value:
        return None
    try:
        data = _serializer().loads(value)
    except BadData as error:
        raise CursorError("Cursor de paginação inválido.") from error
    if not isinstance(data, dict) or data.get("kind") != kind:
        raise CursorError("Cursor de paginação inválido.")
    return data


def cursor_datetime(value: object) -> datetime:
    try:
        return datetime.fromisoformat(str(value))
    except (TypeError, ValueError) as error:
        raise CursorError("Cursor de paginação inválido.") from error


def page_limit(value: object, default: int = 30, maximum: int = 100) -> int:
    try:
        result = int(value or default)
    except (TypeError, ValueError) as error:
        raise CursorError("Limite de paginação inválido.") from error
    if result < 1 or result > maximum:
        raise CursorError(f"Limite deve estar entre 1 e {maximum}.")
    return result


def _serializer() -> URLSafeSerializer:
    return URLSafeSerializer(current_app.config["SECRET_KEY"], salt="directory-pagination-v1")
