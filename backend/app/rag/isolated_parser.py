import json
import socket
import struct
from dataclasses import dataclass
from pathlib import Path

from flask import current_app


@dataclass(frozen=True)
class IsolatedParseResult:
    text: str
    pages: list[dict]
    confidence: float
    page_count: int
    parser_version: str


class IsolatedParserError(RuntimeError):
    pass


class NonRetryableIsolatedParserError(IsolatedParserError):
    pass


def parse_document_isolated(path: Path, mime_type: str) -> IsolatedParseResult:
    request = json.dumps(
        {"path": str(path.resolve()), "mimeType": mime_type},
        ensure_ascii=False,
    ).encode("utf-8")
    if len(request) > 8192:
        raise NonRetryableIsolatedParserError("Solicitacao de parsing invalida.")
    socket_path = str(current_app.config["DOCUMENT_PARSER_SOCKET_PATH"])
    timeout = float(current_app.config["DOCUMENT_PARSER_TIMEOUT_SECONDS"])
    maximum_response = int(current_app.config["DOCUMENT_PARSER_MAX_RESPONSE_BYTES"])
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
            connection.settimeout(timeout)
            connection.connect(socket_path)
            connection.sendall(struct.pack("!I", len(request)) + request)
            response_size = struct.unpack("!I", _receive_exact(connection, 4))[0]
            if response_size <= 0 or response_size > maximum_response:
                raise IsolatedParserError("Parser isolado excedeu o contrato de resposta.")
            response = json.loads(_receive_exact(connection, response_size).decode("utf-8"))
    except (OSError, TimeoutError, json.JSONDecodeError, struct.error) as error:
        raise IsolatedParserError("Parser isolado indisponivel.") from error
    return _validated_result(response)


def _validated_result(response) -> IsolatedParseResult:
    if not isinstance(response, dict) or response.get("status") not in {"OK", "ERROR"}:
        raise IsolatedParserError("Parser isolado retornou contrato invalido.")
    if response["status"] == "ERROR":
        if set(response) != {"status", "code", "message", "retryable"}:
            raise IsolatedParserError("Parser isolado retornou erro fora do contrato.")
        if not isinstance(response["retryable"], bool):
            raise IsolatedParserError("Parser isolado retornou erro invalido.")
        message = str(response.get("message") or "Falha no parsing isolado.")[:500]
        if response.get("retryable") is False:
            raise NonRetryableIsolatedParserError(message)
        raise IsolatedParserError(message)
    required = {
        "status",
        "text",
        "pages",
        "confidence",
        "pageCount",
        "parserVersion",
    }
    if (
        set(response) != required
        or not isinstance(response["text"], str)
        or not isinstance(response["pages"], list)
        or not isinstance(response["confidence"], int | float)
        or isinstance(response["confidence"], bool)
        or not 0 <= response["confidence"] <= 1
        or not isinstance(response["pageCount"], int)
        or isinstance(response["pageCount"], bool)
        or response["pageCount"] != len(response["pages"])
        or not isinstance(response["parserVersion"], str)
        or not response["parserVersion"].strip()
    ):
        raise IsolatedParserError("Parser isolado retornou campos fora do contrato.")
    if any(
        not isinstance(page, dict)
        or not {"pagina", "texto"}.issubset(page)
        or set(page).difference({"pagina", "texto", "confianca", "origem", "secao"})
        or not isinstance(page["pagina"], int)
        or isinstance(page["pagina"], bool)
        or page["pagina"] < 1
        or not isinstance(page["texto"], str)
        for page in response["pages"]
    ):
        raise IsolatedParserError("Parser isolado retornou paginas invalidas.")
    return IsolatedParseResult(
        text=response["text"],
        pages=response["pages"],
        confidence=float(response["confidence"]),
        page_count=response["pageCount"],
        parser_version=str(response["parserVersion"])[:80],
    )


def _receive_exact(connection: socket.socket, size: int) -> bytes:
    result = bytearray()
    while len(result) < size:
        chunk = connection.recv(size - len(result))
        if not chunk:
            raise OSError("Conexao encerrada durante o parsing.")
        result.extend(chunk)
    return bytes(result)
