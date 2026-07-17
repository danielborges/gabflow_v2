import hashlib
import uuid
from pathlib import Path

from flask import current_app
from werkzeug.datastructures import FileStorage
from werkzeug.utils import secure_filename

from app.attachments import EICAR_SIGNATURE

RAG_MIME_TYPES = {
    "application/pdf",
    "image/jpeg",
    "image/png",
    "text/plain",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


class RagStorageError(ValueError):
    pass


def store_rag_document(
    tenant_id: uuid.UUID, version_id: uuid.UUID, uploaded_file: FileStorage
) -> dict:
    original_name = secure_filename(uploaded_file.filename or "")
    if not original_name:
        raise RagStorageError("Selecione um arquivo válido.")
    mime_type = uploaded_file.mimetype or "application/octet-stream"
    if mime_type not in RAG_MIME_TYPES:
        raise RagStorageError("Tipo de arquivo não permitido na base documental.")
    content = uploaded_file.stream.read(current_app.config["RAG_MAX_DOCUMENT_BYTES"] + 1)
    if len(content) > current_app.config["RAG_MAX_DOCUMENT_BYTES"]:
        raise RagStorageError("O documento excede o limite permitido.")
    if not content:
        raise RagStorageError("O documento está vazio.")
    if EICAR_SIGNATURE in content:
        raise RagStorageError("O documento foi bloqueado pela verificação de segurança.")
    key = Path(str(tenant_id)) / f"{version_id}-{original_name}"
    root = Path(current_app.config["RAG_STORAGE_PATH"]).resolve()
    target = (root / key).resolve()
    if root not in target.parents:
        raise RagStorageError("Destino de armazenamento inválido.")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)
    return {
        "storage_key": key.as_posix(),
        "original_name": original_name,
        "mime_type": mime_type,
        "size_bytes": len(content),
        "checksum": hashlib.sha256(content).hexdigest(),
    }


def rag_document_path(storage_key: str) -> Path:
    root = Path(current_app.config["RAG_STORAGE_PATH"]).resolve()
    target = (root / storage_key).resolve()
    if root not in target.parents or not target.is_file():
        raise NonRetryableFileError("Arquivo da base documental não encontrado.")
    return target


class NonRetryableFileError(RuntimeError):
    pass
