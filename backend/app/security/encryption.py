import hashlib
import hmac
import os
import tempfile
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from flask import current_app

MAGIC = b"GABFLOW-AESGCM\x00"
NONCE_BYTES = 12


class StorageEncryptionError(RuntimeError):
    pass


def encrypt_for_scope(content: bytes, scope: str, *, version: int | None = None) -> bytes:
    key_version = version or int(current_app.config["STORAGE_ENCRYPTION_KEY_VERSION"])
    nonce = os.urandom(NONCE_BYTES)
    aad = _aad(scope, key_version)
    ciphertext = AESGCM(_derive_key(scope, key_version)).encrypt(nonce, content, aad)
    return MAGIC + key_version.to_bytes(4, "big") + nonce + ciphertext


def decrypt_for_scope(content: bytes, scope: str) -> bytes:
    if not is_encrypted(content):
        return content
    header = len(MAGIC)
    key_version = int.from_bytes(content[header : header + 4], "big")
    nonce_start = header + 4
    nonce = content[nonce_start : nonce_start + NONCE_BYTES]
    ciphertext = content[nonce_start + NONCE_BYTES :]
    try:
        return AESGCM(_derive_key(scope, key_version)).decrypt(
            nonce,
            ciphertext,
            _aad(scope, key_version),
        )
    except Exception as error:
        raise StorageEncryptionError("Falha na autenticacao criptografica do objeto.") from error


def is_encrypted(content: bytes) -> bool:
    return content.startswith(MAGIC)


def read_plaintext(path: Path, scope: str) -> bytes:
    return decrypt_for_scope(path.read_bytes(), scope)


def write_encrypted(path: Path, content: bytes, scope: str) -> dict:
    path.write_bytes(encrypt_for_scope(content, scope))
    return encryption_metadata()


def ensure_encrypted(path: Path, scope: str) -> dict:
    content = path.read_bytes()
    target_version = int(current_app.config["STORAGE_ENCRYPTION_KEY_VERSION"])
    if is_encrypted(content):
        current_version = int.from_bytes(content[len(MAGIC) : len(MAGIC) + 4], "big")
        if current_version == target_version:
            return encryption_metadata(current_version)
        content = decrypt_for_scope(content, scope)
    path.write_bytes(encrypt_for_scope(content, scope, version=target_version))
    return encryption_metadata(target_version)


@contextmanager
def plaintext_file(path: Path, scope: str, *, suffix: str = ""):
    descriptor, temporary_name = tempfile.mkstemp(prefix="gabflow-dec-", suffix=suffix)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(read_plaintext(path, scope))
        yield Path(temporary_name)
    finally:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass


def encryption_metadata(version: int | None = None) -> dict:
    return {
        "encryption_key_version": version
        or int(current_app.config["STORAGE_ENCRYPTION_KEY_VERSION"]),
        "encryption_algorithm": "AES-256-GCM",
        "encrypted_at": datetime.now(UTC),
    }


def _derive_key(scope: str, version: int) -> bytes:
    master = str(current_app.config["STORAGE_ENCRYPTION_MASTER_KEY"]).encode("utf-8")
    if len(master) < 16:
        raise StorageEncryptionError("Chave mestra de armazenamento deve ter ao menos 16 bytes.")
    salt = b"gabflow-storage-key-v1"
    pseudo_random = hmac.new(salt, master, hashlib.sha256).digest()
    info = f"{scope}:v{version}".encode()
    return hmac.new(pseudo_random, info + b"\x01", hashlib.sha256).digest()


def _aad(scope: str, version: int) -> bytes:
    return f"gabflow:{scope}:v{version}".encode()
