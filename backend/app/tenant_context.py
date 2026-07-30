import uuid
from collections.abc import Iterator
from contextlib import contextmanager

from flask import g, has_request_context
from sqlalchemy import event, text
from sqlalchemy.orm import Session

from app.extensions import db

TENANT_SETTING = "app.tenant_id"
GLOBAL_KNOWLEDGE_ADMIN_SETTING = "app.global_knowledge_admin"


class TenantContextError(RuntimeError):
    pass


@event.listens_for(Session, "after_begin")
def restore_transaction_local_context(
    session: Session, _transaction, connection
) -> None:
    if connection.dialect.name != "postgresql":
        return

    tenant_id = session.info.get("tenant_id")
    if tenant_id is not None:
        connection.execute(
            text("SELECT set_config(:setting, :tenant_id, true)"),
            {"setting": TENANT_SETTING, "tenant_id": str(tenant_id)},
        )
        return

    if session.info.get("global_knowledge_admin"):
        connection.execute(
            text("SELECT set_config(:setting, 'true', true)"),
            {"setting": GLOBAL_KNOWLEDGE_ADMIN_SETTING},
        )


def activate_tenant_context(tenant_id: uuid.UUID | str) -> uuid.UUID:
    try:
        resolved = tenant_id if isinstance(tenant_id, uuid.UUID) else uuid.UUID(str(tenant_id))
    except (TypeError, ValueError) as error:
        raise TenantContextError("Tenant inválido para o contexto transacional.") from error

    active = db.session.info.get("tenant_id")
    if active is not None and active != resolved:
        raise TenantContextError("A transação já está vinculada a outro tenant.")

    if db.engine.dialect.name == "postgresql":
        db.session.execute(
            text("SELECT set_config(:setting, :tenant_id, true)"),
            {"setting": TENANT_SETTING, "tenant_id": str(resolved)},
        )

    db.session.info["tenant_id"] = resolved
    if has_request_context():
        g.tenant_id = resolved
    return resolved


def current_tenant_id(*, required: bool = True) -> uuid.UUID | None:
    value = db.session.info.get("tenant_id")
    if value is None and has_request_context():
        value = getattr(g, "tenant_id", None)
    if value is None and required:
        raise TenantContextError("Contexto transacional de tenant não configurado.")
    return value


def clear_tenant_context() -> None:
    db.session.info.pop("tenant_id", None)
    db.session.info.pop("global_knowledge_admin", None)
    if has_request_context():
        g.pop("tenant_id", None)


@contextmanager
def tenant_context(tenant_id: uuid.UUID | str) -> Iterator[uuid.UUID]:
    resolved = activate_tenant_context(tenant_id)
    try:
        yield resolved
    finally:
        clear_tenant_context()


def activate_global_knowledge_context() -> None:
    if db.session.info.get("tenant_id") is not None:
        raise TenantContextError(
            "Contexto global de conhecimento não pode ser ativado em transação de tenant."
        )
    if db.engine.dialect.name == "postgresql":
        db.session.execute(
            text("SELECT set_config(:setting, 'true', true)"),
            {"setting": GLOBAL_KNOWLEDGE_ADMIN_SETTING},
        )
    db.session.info["global_knowledge_admin"] = True
