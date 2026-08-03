import uuid
from datetime import UTC, datetime
from functools import wraps

from flask import g, jsonify
from flask_jwt_extended import get_jwt, get_jwt_identity, verify_jwt_in_request
from sqlalchemy import select

from app.audit import add_audit
from app.electoral.service import active_mandate
from app.extensions import db
from app.models import ElectoralAccessDelegation, Role

ELECTORAL_CAPABILITIES = frozenset(
    {
        "consultar_dados_publicos",
        "ver_camadas_mandato",
        "comparar_candidatos",
        "usar_ia",
        "criar_cenario",
        "exportar",
        "delegar_acesso",
    }
)


def electoral_access_required(capability: str):
    if capability not in ELECTORAL_CAPABILITIES:
        raise ValueError(f"Capacidade eleitoral desconhecida: {capability}.")

    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            verify_jwt_in_request()
            claims = get_jwt()
            tenant_id = uuid.UUID(claims["tenant_id"])
            user_id = uuid.UUID(get_jwt_identity())
            mandate = active_mandate(tenant_id)
            if mandate is None:
                return _deny(tenant_id, user_id, capability, "active_mandate_required")

            role = str(claims.get("role") or "")
            if role == Role.REPRESENTATIVE.value and mandate.representative_user_id == user_id:
                capabilities = ELECTORAL_CAPABILITIES
            else:
                capabilities = _delegated_capabilities(tenant_id, mandate.id, user_id)
            if capability not in capabilities:
                return _deny(tenant_id, user_id, capability, "capability_required")

            g.electoral_mandate = mandate
            g.electoral_capabilities = sorted(capabilities)
            return fn(*args, **kwargs)

        return wrapper

    return decorator


def _delegated_capabilities(tenant_id, mandate_id, user_id) -> set[str]:
    now = datetime.now(UTC)
    delegations = db.session.execute(
        select(ElectoralAccessDelegation).where(
            ElectoralAccessDelegation.tenant_id == tenant_id,
            ElectoralAccessDelegation.mandate_id == mandate_id,
            ElectoralAccessDelegation.grantee_user_id == user_id,
            ElectoralAccessDelegation.revoked_at.is_(None),
            ElectoralAccessDelegation.valid_from <= now,
            ElectoralAccessDelegation.valid_until > now,
        )
    ).scalars()
    return {
        capability
        for delegation in delegations
        for capability in delegation.capabilities or []
        if capability in ELECTORAL_CAPABILITIES
    }


def _deny(tenant_id, user_id, capability: str, reason: str):
    add_audit(
        tenant_id,
        user_id,
        "electoral.access.denied",
        "electoral_module",
        None,
        after={"capability": capability, "reason": reason},
    )
    db.session.commit()
    message = (
        "O gabinete nao possui mandato parlamentar ativo."
        if reason == "active_mandate_required"
        else "Permissao insuficiente para a Inteligencia Eleitoral."
    )
    return jsonify(error=reason, message=message), 403
