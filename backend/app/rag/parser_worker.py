import json
import os
import sys
import tempfile
from pathlib import Path

PARSER_VERSION = "gabflow-isolated-parser-v1"
DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def main() -> int:
    try:
        maximum_bytes = int(os.environ.get("PARSER_MAX_FILE_BYTES", "31457280"))
        request = sys.stdin.buffer.read(maximum_bytes + 8193)
        result = parse_request(request)
    except Exception as error:
        result = {
            "status": "ERROR",
            "code": "PARSER_REJECTED",
            "message": _safe_message(error),
            "retryable": False,
        }
    sys.stdout.write(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
    return 0


def parse_request(request: bytes) -> dict:
    header_bytes, separator, content = request.partition(b"\n")
    payload = json.loads(header_bytes if separator else request)
    if not separator:
        return parse(payload)
    if not isinstance(payload, dict) or set(payload) != {
        "mimeType",
        "contentLength",
        "suffix",
    }:
        raise ValueError("Solicitacao de parsing invalida.")
    content_length = payload["contentLength"]
    if (
        not isinstance(content_length, int)
        or isinstance(content_length, bool)
        or content_length != len(content)
    ):
        raise ValueError("Conteudo do parsing esta incompleto.")
    maximum_bytes = int(os.environ.get("PARSER_MAX_FILE_BYTES", "31457280"))
    if content_length > maximum_bytes:
        raise ValueError("Arquivo excede o limite do parser isolado.")
    suffix = str(payload["suffix"])
    allowed_suffix_characters = ".-_abcdefghijklmnopqrstuvwxyz0123456789"
    if len(suffix) > 16 or any(
        character not in allowed_suffix_characters for character in suffix.lower()
    ):
        raise ValueError("Extensao de arquivo invalida.")
    descriptor, temporary_name = tempfile.mkstemp(prefix="gabflow-parser-", suffix=suffix)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
        return _parse_path(Path(temporary_name), str(payload["mimeType"]))
    finally:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass


def parse(payload: dict) -> dict:
    if not isinstance(payload, dict) or set(payload) != {"path", "mimeType"}:
        raise ValueError("Solicitacao de parsing invalida.")
    path = _validated_path(str(payload["path"]))
    mime_type = str(payload["mimeType"])
    return _parse_path(path, mime_type)


def _parse_path(path: Path, mime_type: str) -> dict:
    maximum_bytes = int(os.environ.get("PARSER_MAX_FILE_BYTES", "31457280"))
    if path.stat().st_size > maximum_bytes:
        raise ValueError("Arquivo excede o limite do parser isolado.")

    if mime_type == "text/plain":
        text = path.read_text(encoding="utf-8")
        pages = [{"pagina": 1, "texto": text, "confianca": 1.0, "origem": "NATIVO"}]
        confidence = 1.0
    elif mime_type == DOCX_MIME:
        from docx import Document

        paragraphs = [
            paragraph.text.strip()
            for paragraph in Document(path).paragraphs
            if paragraph.text.strip()
        ]
        text = "\n\n".join(paragraphs)
        pages = [{"pagina": 1, "texto": text, "confianca": 1.0, "origem": "NATIVO"}]
        confidence = 1.0
    elif mime_type in {"application/pdf", "image/jpeg", "image/png"}:
        sys.path.insert(0, "/app")
        from app.ai.ocr import TesseractOcrProvider

        provider = TesseractOcrProvider(
            model=os.environ.get("DOCUMENT_OCR_MODEL", "tesseract-5"),
            language=os.environ.get("DOCUMENT_OCR_LANGUAGE", "por"),
            maximum_pages=int(os.environ.get("DOCUMENT_OCR_MAX_PAGES", "500")),
            maximum_pixels=int(os.environ.get("DOCUMENT_OCR_MAX_PIXELS", "25000000")),
            native_text_minimum_chars=int(os.environ.get("DOCUMENT_OCR_NATIVE_MIN_CHARS", "40")),
            batch_size=int(os.environ.get("DOCUMENT_OCR_BATCH_SIZE", "8")),
        )
        extracted = provider.extract(path, mime_type)
        text = extracted.text
        pages = extracted.pages
        confidence = extracted.confidence
    else:
        raise ValueError("Tipo de documento nao compativel com o parser isolado.")

    maximum_output = int(os.environ.get("PARSER_MAX_OUTPUT_CHARS", "5000000"))
    if len(text) > maximum_output:
        raise ValueError("Texto extraido excede o limite do parser isolado.")
    return {
        "status": "OK",
        "text": text,
        "pages": pages,
        "confidence": confidence,
        "pageCount": len(pages),
        "parserVersion": PARSER_VERSION,
    }


def _validated_path(raw_path: str) -> Path:
    path = Path(raw_path).resolve(strict=True)
    allowed_roots = [
        Path(value).resolve()
        for value in os.environ.get(
            "PARSER_ALLOWED_ROOTS", "/app/data/attachments:/app/data/rag"
        ).split(":")
        if value
    ]
    if not path.is_file() or not any(root in path.parents for root in allowed_roots):
        raise ValueError("Arquivo fora das raizes autorizadas do parser.")
    return path


def _safe_message(error: Exception) -> str:
    if isinstance(error, UnicodeDecodeError):
        return "O arquivo de texto deve estar em UTF-8."
    message = str(error).replace("\n", " ").strip()
    return message[:500] or "Falha ao processar o documento."


if __name__ == "__main__":
    raise SystemExit(main())
