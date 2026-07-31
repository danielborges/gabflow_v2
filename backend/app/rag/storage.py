import hashlib
import uuid
from pathlib import Path

from flask import current_app
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from werkzeug.datastructures import FileStorage
from werkzeug.utils import secure_filename

from app.security.encryption import write_encrypted
from app.security.malware import MalwareScanError, require_clean_upload

RAG_MIME_TYPES = {
    "application/pdf",
    "image/jpeg",
    "image/png",
    "text/plain",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


class RagStorageError(ValueError):
    pass


def store_generated_rag_text(
    tenant_id: uuid.UUID,
    document_id: uuid.UUID,
    version_id: uuid.UUID,
    content: str,
) -> dict:
    encoded = content.encode("utf-8")
    if not encoded or len(encoded) > current_app.config["RAG_MAX_DOCUMENT_BYTES"]:
        raise RagStorageError("Conteúdo gerado inválido para a memória operacional.")
    original_name = "memoria-operacional.txt"
    key = (
        Path("tenants")
        / str(tenant_id)
        / "rag"
        / str(document_id)
        / str(version_id)
        / original_name
    )
    encryption = _write_rag_object(key, encoded, scope=f"tenant:{tenant_id}")
    return {
        "storage_key": key.as_posix(),
        "original_name": original_name,
        "mime_type": "text/plain",
        "size_bytes": len(encoded),
        "checksum": hashlib.sha256(encoded).hexdigest(),
        **encryption,
    }


def store_rag_document(
    tenant_id: uuid.UUID,
    document_id: uuid.UUID,
    version_id: uuid.UUID,
    uploaded_file: FileStorage,
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
    try:
        scan = require_clean_upload(content, mime_type)
    except MalwareScanError as error:
        raise RagStorageError(str(error)) from error
    key = (
        Path("tenants")
        / str(tenant_id)
        / "rag"
        / str(document_id)
        / str(version_id)
        / original_name
    )
    root = Path(current_app.config["RAG_STORAGE_PATH"]).resolve()
    target = (root / key).resolve()
    if root not in target.parents:
        raise RagStorageError("Destino de armazenamento inválido.")
    target.parent.mkdir(parents=True, exist_ok=True)
    encryption = write_encrypted(target, content, f"tenant:{tenant_id}")
    return {
        "storage_key": key.as_posix(),
        "original_name": original_name,
        "mime_type": mime_type,
        "size_bytes": len(content),
        "checksum": hashlib.sha256(content).hexdigest(),
        **encryption,
        **_malware_metadata(scan),
    }


def store_global_rag_document(
    document_id: uuid.UUID,
    version_id: uuid.UUID,
    uploaded_file: FileStorage,
) -> dict:
    original_name, mime_type, content, scan = _validated_upload(uploaded_file)
    key = Path("global") / "rag" / str(document_id) / str(version_id) / original_name
    encryption = _write_rag_object(key, content, scope="global")
    return {
        "storage_key": key.as_posix(),
        "original_name": original_name,
        "mime_type": mime_type,
        "size_bytes": len(content),
        "checksum": hashlib.sha256(content).hexdigest(),
        **encryption,
        **_malware_metadata(scan),
    }


def global_rag_document_path(
    storage_key: str,
    *,
    document_id: uuid.UUID,
    version_id: uuid.UUID,
) -> Path:
    key = Path(storage_key)
    parts = key.parts
    expected_prefix = ("global", "rag", str(document_id), str(version_id))
    if len(parts) != 5 or tuple(parts[:4]) != expected_prefix or parts[4] != Path(parts[4]).name:
        raise NonRetryableFileError("Chave de armazenamento RAG global inválida.")
    root = Path(current_app.config["RAG_STORAGE_PATH"]).resolve()
    target = (root / key).resolve()
    if root not in target.parents or not target.is_file():
        raise NonRetryableFileError("Arquivo do catálogo global não encontrado.")
    return target


def signed_global_rag_download_token(document_id: uuid.UUID, version_id: uuid.UUID) -> str:
    return _download_serializer().dumps(
        {
            "document_id": str(document_id),
            "version_id": str(version_id),
            "purpose": "rag-global-download",
        }
    )


def verify_global_rag_download_token(
    token: str,
    document_id: uuid.UUID,
    version_id: uuid.UUID,
) -> bool:
    try:
        data = _download_serializer().loads(
            token,
            max_age=current_app.config["RAG_DOWNLOAD_TOKEN_MAX_AGE"],
        )
    except (BadSignature, SignatureExpired):
        return False
    return data == {
        "document_id": str(document_id),
        "version_id": str(version_id),
        "purpose": "rag-global-download",
    }


def rag_document_path(
    storage_key: str,
    *,
    tenant_id: uuid.UUID,
    document_id: uuid.UUID,
    version_id: uuid.UUID,
) -> Path:
    _validate_storage_key(storage_key, tenant_id, document_id, version_id)
    root = Path(current_app.config["RAG_STORAGE_PATH"]).resolve()
    target = (root / storage_key).resolve()
    if root not in target.parents or not target.is_file():
        raise NonRetryableFileError("Arquivo da base documental não encontrado.")
    return target


def delete_rag_object(
    storage_key: str,
    *,
    tenant_id: uuid.UUID,
    document_id: uuid.UUID,
    version_id: uuid.UUID,
) -> bool:
    _validate_storage_key(storage_key, tenant_id, document_id, version_id)
    root = Path(current_app.config["RAG_STORAGE_PATH"]).resolve()
    target = root / storage_key
    resolved = target.resolve(strict=False)
    if root not in resolved.parents:
        raise NonRetryableFileError("Chave de armazenamento RAG fora do tenant.")
    if not target.exists() and not target.is_symlink():
        return False
    if not target.is_file() and not target.is_symlink():
        raise NonRetryableFileError("Objeto RAG inválido para eliminação.")
    target.unlink()

    version_directory = target.parent
    canonical_version_directory = (
        root / "tenants" / str(tenant_id) / "rag" / str(document_id) / str(version_id)
    )
    if (
        version_directory.resolve(strict=False) == canonical_version_directory.resolve(strict=False)
        and version_directory.exists()
        and not any(version_directory.iterdir())
    ):
        version_directory.rmdir()
        document_directory = version_directory.parent
        if document_directory.exists() and not any(document_directory.iterdir()):
            document_directory.rmdir()
    return True


class NonRetryableFileError(RuntimeError):
    pass


def signed_rag_download_token(
    tenant_id: uuid.UUID, document_id: uuid.UUID, version_id: uuid.UUID
) -> str:
    return _download_serializer().dumps(
        {
            "tenant_id": str(tenant_id),
            "document_id": str(document_id),
            "version_id": str(version_id),
            "purpose": "rag-download",
        }
    )


def verify_rag_download_token(
    token: str,
    tenant_id: uuid.UUID,
    document_id: uuid.UUID,
    version_id: uuid.UUID,
) -> bool:
    try:
        data = _download_serializer().loads(
            token,
            max_age=current_app.config["RAG_DOWNLOAD_TOKEN_MAX_AGE"],
        )
    except (BadSignature, SignatureExpired):
        return False
    return data == {
        "tenant_id": str(tenant_id),
        "document_id": str(document_id),
        "version_id": str(version_id),
        "purpose": "rag-download",
    }


def _validate_storage_key(
    storage_key: str,
    tenant_id: uuid.UUID,
    document_id: uuid.UUID,
    version_id: uuid.UUID,
) -> None:
    key = Path(storage_key)
    parts = key.parts
    expected_prefix = (
        "tenants",
        str(tenant_id),
        "rag",
        str(document_id),
        str(version_id),
    )
    canonical = (
        len(parts) == 6 and tuple(parts[:5]) == expected_prefix and parts[5] == Path(parts[5]).name
    )
    legacy = (
        current_app.config["RAG_ALLOW_LEGACY_STORAGE_KEYS"]
        and len(parts) == 2
        and parts[0] == str(tenant_id)
        and parts[1].startswith(f"{version_id}-")
        and parts[1] == Path(parts[1]).name
    )
    if not canonical and not legacy:
        raise NonRetryableFileError("Chave de armazenamento RAG incompatível com o tenant.")


def _download_serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(current_app.config["SECRET_KEY"], salt="rag-download-v1")


def _validated_upload(uploaded_file: FileStorage) -> tuple[str, str, bytes, object]:
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
    try:
        scan = require_clean_upload(content, mime_type)
    except MalwareScanError as error:
        raise RagStorageError(str(error)) from error
    return original_name, mime_type, content, scan


def _malware_metadata(scan) -> dict:
    return {
        "malware_scan_status": scan.status.value,
        "malware_scan_provider": scan.provider,
        "malware_engine_version": scan.engine_version,
        "malware_signature_version": scan.signature_version,
        "malware_threat": scan.threat,
        "malware_scan_error_code": scan.error_code,
        "malware_scanned_at": scan.scanned_at,
    }


def _write_rag_object(key: Path, content: bytes, *, scope: str) -> dict:
    root = Path(current_app.config["RAG_STORAGE_PATH"]).resolve()
    target = (root / key).resolve()
    if root not in target.parents:
        raise RagStorageError("Destino de armazenamento inválido.")
    target.parent.mkdir(parents=True, exist_ok=True)
    return write_encrypted(target, content, scope)
