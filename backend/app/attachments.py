import hashlib
import uuid
from pathlib import Path

from flask import current_app
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from werkzeug.datastructures import FileStorage
from werkzeug.utils import secure_filename

ALLOWED_MIME_TYPES = {
    "application/pdf",
    "image/jpeg",
    "image/png",
    "text/plain",
    "audio/mpeg",
    "audio/ogg",
    "video/mp4",
}
EICAR_SIGNATURE = b"X5O!P%@AP[4\\PZX54(P^)7CC)7}$EICAR"


class AttachmentError(ValueError):
    pass


def store_attachment(
    tenant_id: uuid.UUID, attachment_id: uuid.UUID, uploaded_file: FileStorage
) -> dict:
    original_name = secure_filename(uploaded_file.filename or "")
    if not original_name:
        raise AttachmentError("Selecione um arquivo válido.")
    mime_type = uploaded_file.mimetype or "application/octet-stream"
    if mime_type not in ALLOWED_MIME_TYPES:
        raise AttachmentError("Tipo de arquivo não permitido.")

    content = uploaded_file.stream.read(current_app.config["MAX_ATTACHMENT_BYTES"] + 1)
    if len(content) > current_app.config["MAX_ATTACHMENT_BYTES"]:
        raise AttachmentError("O arquivo excede o limite permitido.")
    if not content:
        raise AttachmentError("O arquivo está vazio.")
    if EICAR_SIGNATURE in content:
        raise AttachmentError("O arquivo foi bloqueado pela verificação de segurança.")

    relative_key = Path(str(tenant_id)) / f"{attachment_id}-{original_name}"
    storage_root = Path(current_app.config["ATTACHMENT_STORAGE_PATH"]).resolve()
    target = (storage_root / relative_key).resolve()
    if storage_root not in target.parents:
        raise AttachmentError("Destino de armazenamento inválido.")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)

    return {
        "storage_key": relative_key.as_posix(),
        "original_name": original_name,
        "mime_type": mime_type,
        "size_bytes": len(content),
        "sha256": hashlib.sha256(content).hexdigest(),
    }


def attachment_path(storage_key: str) -> Path:
    storage_root = Path(current_app.config["ATTACHMENT_STORAGE_PATH"]).resolve()
    target = (storage_root / storage_key).resolve()
    if storage_root not in target.parents or not target.is_file():
        raise AttachmentError("Arquivo não encontrado.")
    return target


def signed_attachment_token(attachment_id: uuid.UUID, tenant_id: uuid.UUID) -> str:
    serializer = URLSafeTimedSerializer(current_app.config["SECRET_KEY"], salt="attachment")
    return serializer.dumps({"attachment_id": str(attachment_id), "tenant_id": str(tenant_id)})


def verify_attachment_token(token: str, attachment_id: uuid.UUID, tenant_id: uuid.UUID) -> bool:
    serializer = URLSafeTimedSerializer(current_app.config["SECRET_KEY"], salt="attachment")
    try:
        data = serializer.loads(
            token,
            max_age=current_app.config["ATTACHMENT_TOKEN_MAX_AGE"],
        )
    except (BadSignature, SignatureExpired):
        return False
    return data == {"attachment_id": str(attachment_id), "tenant_id": str(tenant_id)}
