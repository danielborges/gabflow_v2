import uuid

import pytest

from app.extensions import db
from app.tenant_context import (
    TenantContextError,
    activate_tenant_context,
    clear_tenant_context,
    current_tenant_id,
)


def test_tenant_context_rejects_switch_inside_same_transaction(app):
    tenant_a = uuid.uuid4()
    tenant_b = uuid.uuid4()

    with app.app_context():
        assert activate_tenant_context(tenant_a) == tenant_a
        assert current_tenant_id() == tenant_a
        with pytest.raises(TenantContextError):
            activate_tenant_context(tenant_b)
        clear_tenant_context()
        assert current_tenant_id(required=False) is None
        db.session.rollback()


def test_request_context_is_cleared_after_tenant_request(app, client):
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@teste.local", "password": "SenhaForte123!"},
    )
    assert response.status_code == 200

    assert client.get("/api/v1/rag/documentos").status_code == 200
    with app.app_context():
        assert current_tenant_id(required=False) is None
