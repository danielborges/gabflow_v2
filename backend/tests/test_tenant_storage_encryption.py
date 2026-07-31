import io
import uuid

import pytest
from werkzeug.datastructures import FileStorage

from app.attachments import attachment_path, store_attachment
from app.security.encryption import StorageEncryptionError, read_plaintext


def test_attachment_is_encrypted_with_tenant_bound_aead(app):
    tenant_id = uuid.uuid4()
    content = b"conteudo legislativo reservado"
    uploaded = FileStorage(
        stream=io.BytesIO(content),
        filename="nota.txt",
        content_type="text/plain",
    )
    with app.app_context():
        metadata = store_attachment(tenant_id, uuid.uuid4(), uploaded)
        path = attachment_path(metadata["storage_key"])

        assert content not in path.read_bytes()
        assert metadata["encryption_algorithm"] == "AES-256-GCM"
        assert read_plaintext(path, f"tenant:{tenant_id}") == content
        with pytest.raises(StorageEncryptionError):
            read_plaintext(path, f"tenant:{uuid.uuid4()}")
