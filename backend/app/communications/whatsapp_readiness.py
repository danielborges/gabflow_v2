import re
from collections.abc import Mapping
from urllib.parse import urlparse

ROLLOUT_STAGES = {"disabled", "sandbox", "pilot", "ga"}
GRAPH_VERSION_RE = re.compile(r"^v\d+\.\d+$")
AWS_SECRETS_MANAGER_BACKEND = "aws-secrets-manager"


def whatsapp_readiness_data(config: Mapping, tenant_slug: str) -> dict:
    environment = str(config.get("APP_ENV") or "development").lower()
    stage = str(config.get("WHATSAPP_ROLLOUT_STAGE") or "disabled").lower()
    pilot_tenants = {
        str(value).strip().lower()
        for value in config.get("WHATSAPP_PILOT_TENANT_SLUGS", ())
        if str(value).strip()
    }
    platform_enabled = bool(config.get("WHATSAPP_PLATFORM_ENABLED"))
    tenant_enabled = _tenant_enabled(platform_enabled, stage, pilot_tenants, tenant_slug)
    secret_backend = str(config.get("WHATSAPP_SECRET_BACKEND") or "unconfigured").lower()
    secret_backend_ready = bool(config.get("WHATSAPP_SECRET_BACKEND_READY"))

    checks = [
        _check(
            "platform_flag",
            "Pipeline WhatsApp v2 habilitado",
            platform_enabled,
            "technical",
        ),
        _check(
            "rollout_stage",
            "Estagio de rollout valido",
            stage in ROLLOUT_STAGES and stage != "disabled",
            "technical",
            detail=f"Estagio atual: {stage}",
        ),
        _check(
            "tenant_rollout",
            "Gabinete incluido no rollout",
            tenant_enabled,
            "technical",
        ),
        _configured_check(config, "WHATSAPP_META_APP_ID", "App ID da Meta configurado"),
        _configured_check(
            config,
            "WHATSAPP_META_CONFIGURATION_ID",
            "Configuration ID do Embedded Signup configurado",
        ),
        _check(
            "graph_api_version",
            "Versao da Graph API fixada",
            bool(
                GRAPH_VERSION_RE.fullmatch(
                    str(config.get("WHATSAPP_GRAPH_API_VERSION") or "")
                )
            ),
            "technical",
        ),
        _check(
            "redirect_uri",
            "Redirect URI HTTPS configurada",
            _is_https_url(config.get("WHATSAPP_META_REDIRECT_URI")),
            "technical",
        ),
        _configured_check(config, "META_APP_SECRET", "App Secret da Meta configurado"),
        _configured_check(
            config,
            "WHATSAPP_WEBHOOK_VERIFY_TOKEN",
            "Verify token do webhook configurado",
        ),
        _check(
            "inbound_queue",
            "Fila confiavel de recebimento configurada",
            environment not in {"staging", "production"}
            or (
                str(config.get("WHATSAPP_INBOUND_QUEUE_BACKEND") or "").lower()
                == "aws-sqs"
                and _is_https_url(config.get("WHATSAPP_AWS_SQS_QUEUE_URL"))
            ),
            "technical",
        ),
        _check(
            "webhook_retention",
            "Retencao temporaria do payload configurada",
            1 <= int(config.get("WHATSAPP_WEBHOOK_PAYLOAD_RETENTION_DAYS") or 0) <= 30,
            "technical",
        ),
        _check(
            "embedded_signup_flag",
            "Embedded Signup habilitado",
            bool(config.get("WHATSAPP_EMBEDDED_SIGNUP_ENABLED")),
            "pilot",
        ),
        _check(
            "secret_backend",
            "AWS Secrets Manager validado para producao",
            environment != "production"
            or (
                secret_backend == AWS_SECRETS_MANAGER_BACKEND
                and secret_backend_ready
                and bool(str(config.get("WHATSAPP_AWS_KMS_KEY_ID") or "").strip())
                and bool(str(config.get("WHATSAPP_AWS_SECRET_PREFIX") or "").strip())
            ),
            "pilot",
            detail=f"Backend declarado: {secret_backend}",
        ),
        _boolean_check(
            config,
            "WHATSAPP_META_BUSINESS_VERIFIED",
            "Business Portfolio verificado pela Meta",
        ),
        _boolean_check(
            config,
            "WHATSAPP_META_TECH_PROVIDER_APPROVED",
            "Tech Provider aprovado",
        ),
        _boolean_check(
            config,
            "WHATSAPP_META_APP_REVIEW_APPROVED",
            "App Review e permissoes aprovados",
        ),
        _boolean_check(
            config,
            "WHATSAPP_PRIVACY_REVIEW_APPROVED",
            "Aviso de privacidade e bases legais aprovados",
        ),
        _boolean_check(config, "WHATSAPP_DPA_APPROVED", "DPA e subprocessadores aprovados"),
    ]
    sandbox_checks = [item for item in checks if item["gate"] == "technical"]
    return {
        "incremento": 0,
        "ambiente": environment,
        "estagio": stage,
        "plataformaHabilitada": platform_enabled,
        "embeddedSignupHabilitado": bool(config.get("WHATSAPP_EMBEDDED_SIGNUP_ENABLED")),
        "tenantHabilitado": tenant_enabled,
        "prontoSandbox": all(item["ok"] for item in sandbox_checks),
        "prontoPiloto": all(item["ok"] for item in checks),
        "pendencias": [item["key"] for item in checks if not item["ok"]],
        "verificacoes": checks,
    }


def _tenant_enabled(enabled: bool, stage: str, pilots: set[str], tenant_slug: str) -> bool:
    if not enabled or stage == "disabled" or stage not in ROLLOUT_STAGES:
        return False
    if stage == "ga":
        return True
    return tenant_slug.strip().lower() in pilots


def _is_https_url(value) -> bool:
    parsed = urlparse(str(value or ""))
    return parsed.scheme == "https" and bool(parsed.netloc)


def _configured_check(config: Mapping, key: str, label: str) -> dict:
    return _check(key.lower(), label, bool(str(config.get(key) or "").strip()), "technical")


def _boolean_check(config: Mapping, key: str, label: str) -> dict:
    return _check(key.lower(), label, bool(config.get(key)), "pilot")


def _check(key: str, label: str, ok: bool, gate: str, detail: str | None = None) -> dict:
    result = {"key": key, "titulo": label, "ok": ok, "gate": gate}
    if detail:
        result["detalhe"] = detail
    return result
