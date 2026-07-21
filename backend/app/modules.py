import uuid

from flask import jsonify
from flask_jwt_extended import get_jwt, verify_jwt_in_request

from app.extensions import db
from app.models import ContractStatus, Tenant, TenantStatus

AVAILABLE_MODULES = {
    "solicitacoes",
    "cidadaos",
    "ia",
    "rag",
    "documentos",
    "agenda",
    "fiscalizacao",
    "canais",
    "privacidade",
    "integracoes",
}

DEFAULT_MODULES = sorted(AVAILABLE_MODULES)

BLUEPRINT_MODULES = {
    "requests": "solicitacoes",
    "request_operations": "solicitacoes",
    "directory": "cidadaos",
    "ai": "ia",
    "rag": "rag",
    "legislative": "documentos",
    "agenda": "agenda",
    "oversight": "fiscalizacao",
    "communications": "canais",
    "privacy": "privacidade",
}

ROUTE_MODULES = {
    "admin.list_integrations": "integracoes",
    "admin.upsert_integration": "integracoes",
}

PUBLIC_ENDPOINTS = {
    "communications.receive_channel_webhook",
    "communications.receive_resend_inbound_email",
    "communications.verify_whatsapp_webhook",
    "communications.receive_whatsapp_business_webhook",
    "communications.verify_meta_social_webhook",
    "communications.receive_meta_social_webhook",
    "communications.public_form_config",
    "communications.submit_public_request",
}

BLOCKING_CONTRACT_STATUSES = {ContractStatus.SUSPENDED, ContractStatus.CANCELLED}


def normalize_modules(value: list | None) -> list[str]:
    if not value:
        return DEFAULT_MODULES
    return sorted({str(item).strip().lower() for item in value if str(item).strip()})


def validate_modules(value: list) -> list[str]:
    if not isinstance(value, list):
        raise ValueError("Modulos habilitados devem ser uma lista.")
    modules = sorted({str(item).strip().lower() for item in value if str(item).strip()})
    if not modules:
        raise ValueError("Informe ao menos um modulo habilitado.")
    invalid = [item for item in modules if item not in AVAILABLE_MODULES]
    if invalid:
        raise ValueError(f"Modulo invalido: {', '.join(invalid)}.")
    return modules


def module_for_endpoint(endpoint: str | None, blueprint: str | None) -> str | None:
    if endpoint in ROUTE_MODULES:
        return ROUTE_MODULES[endpoint]
    return BLUEPRINT_MODULES.get(blueprint or "")


def enforce_tenant_access(endpoint: str | None, blueprint: str | None):
    if endpoint in PUBLIC_ENDPOINTS:
        return None
    if blueprint in {None, "auth", "health", "platform", "public_requests"}:
        return None
    verify_jwt_in_request(optional=True)
    claims = get_jwt()
    tenant_claim = claims.get("tenant_id")
    if not tenant_claim:
        return None
    tenant = db.session.get(Tenant, uuid.UUID(tenant_claim))
    if tenant is None or tenant.status != TenantStatus.ACTIVE:
        return jsonify(error="tenant_inactive", message="Gabinete inativo ou indisponivel."), 403
    if tenant.contract_status in BLOCKING_CONTRACT_STATUSES:
        return (
            jsonify(
                error="contract_blocked",
                message="Contrato suspenso ou cancelado. Contate o Administrador Geral.",
            ),
            403,
        )
    required_module = module_for_endpoint(endpoint, blueprint)
    if required_module and required_module not in normalize_modules(tenant.enabled_modules):
        return (
            jsonify(
                error="module_disabled",
                message="Modulo nao habilitado para este gabinete.",
                module=required_module,
            ),
            403,
        )
    return None
