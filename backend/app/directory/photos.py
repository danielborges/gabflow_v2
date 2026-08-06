import hashlib
import io
import uuid
from pathlib import Path

from flask import current_app
from PIL import Image, ImageOps, UnidentifiedImageError
from werkzeug.datastructures import FileStorage

from app.security.encryption import read_plaintext, write_encrypted
from app.security.malware import MalwareScanError, require_clean_upload

ALLOWED_INPUTS = {"image/jpeg", "image/png", "image/webp"}


class CitizenPhotoError(ValueError):
    pass


def store_citizen_photo(
    tenant_id: uuid.UUID, citizen_id: uuid.UUID, uploaded_file: FileStorage
) -> dict:
    declared_mime = str(uploaded_file.mimetype or "").lower()
    if declared_mime not in ALLOWED_INPUTS:
        raise CitizenPhotoError("Envie uma imagem JPEG, PNG ou WebP.")
    maximum = int(current_app.config["MAX_CITIZEN_PHOTO_BYTES"])
    content = uploaded_file.stream.read(maximum + 1)
    if not content:
        raise CitizenPhotoError("A imagem está vazia.")
    if len(content) > maximum:
        raise CitizenPhotoError("A imagem excede o limite de 8 MB.")
    try:
        scan = require_clean_upload(content, declared_mime)
        processed = _safe_profile_image(content)
    except MalwareScanError as error:
        raise CitizenPhotoError(str(error)) from error

    identifier = uuid.uuid4()
    relative_key = Path(str(tenant_id)) / "citizens" / str(citizen_id) / f"{identifier}.webp"
    target = _safe_target(relative_key)
    target.parent.mkdir(parents=True, exist_ok=True)
    write_encrypted(target, processed, f"tenant:{tenant_id}:citizen-photo")
    return {
        "storage_key": relative_key.as_posix(),
        "mime_type": "image/webp",
        "size_bytes": len(processed),
        "sha256": hashlib.sha256(processed).hexdigest(),
        "scan_provider": scan.provider,
        "scan_engine_version": scan.engine_version,
    }


def read_citizen_photo(tenant_id: uuid.UUID, storage_key: str) -> bytes:
    target = _safe_target(Path(storage_key), must_exist=True)
    return read_plaintext(target, f"tenant:{tenant_id}:citizen-photo")


def delete_citizen_photo(storage_key: str | None) -> None:
    if not storage_key:
        return
    target = _safe_target(Path(storage_key), must_exist=True)
    if target.is_symlink():
        raise CitizenPhotoError("Objeto de imagem inválido.")
    target.unlink()


def _safe_profile_image(content: bytes) -> bytes:
    try:
        with Image.open(io.BytesIO(content)) as source:
            width, height = source.size
            if width < 1 or height < 1:
                raise CitizenPhotoError("A imagem possui dimensões inválidas.")
            if width * height > int(current_app.config["MAX_CITIZEN_PHOTO_PIXELS"]):
                raise CitizenPhotoError("A resolução da imagem excede o limite permitido.")
            source.load()
            image = ImageOps.exif_transpose(source).convert("RGB")
            size = int(current_app.config["CITIZEN_PHOTO_SIZE"])
            image = ImageOps.fit(image, (size, size), method=Image.Resampling.LANCZOS)
            output = io.BytesIO()
            image.save(output, format="WEBP", quality=84, method=6)
            return output.getvalue()
    except (UnidentifiedImageError, OSError, ValueError) as error:
        if isinstance(error, CitizenPhotoError):
            raise
        raise CitizenPhotoError("O arquivo não contém uma imagem válida.") from error


def _safe_target(relative_key: Path, *, must_exist: bool = False) -> Path:
    if relative_key.is_absolute():
        raise CitizenPhotoError("Destino de imagem inválido.")
    root = Path(current_app.config["ATTACHMENT_STORAGE_PATH"]).resolve()
    target = (root / relative_key).resolve()
    if root not in target.parents:
        raise CitizenPhotoError("Destino de imagem inválido.")
    if must_exist and (not target.is_file() or target.is_symlink()):
        raise CitizenPhotoError("Imagem não encontrada.")
    return target
