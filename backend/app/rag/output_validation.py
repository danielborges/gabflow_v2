import hashlib
import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.parse import urlsplit

from flask import current_app

from app.extensions import db
from app.models import AuditLog, RagOutputValidationProfile

OUTPUT_REFUSAL_MESSAGE = (
    "Não foi possível liberar a resposta porque a validação independente de saída "
    "identificou um risco de segurança ou fundamentação."
)
CRITICAL_SIGNALS = {
    "PROMPT_OR_INSTRUCTION_LEAKAGE",
    "SECRET_OR_CREDENTIAL_LEAKAGE",
    "UNAUTHORIZED_ACTION_CLAIM",
}
_PROMPT_LEAKAGE = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\b(?:system|developer)\s+(?:prompt|message)\b",
        r"\b(?:prompt|instru[cç][oõ]es?)\s+(?:intern[oa]s?|ocult[oa]s?|do sistema)\b",
        r"<\/?(?:system|developer|assistant|tool)>",
        r"\bBEGIN (?:SYSTEM|DEVELOPER) (?:PROMPT|MESSAGE)\b",
    )
)
_SECRETS = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----",
        r"\b(?:sk|rk)-[A-Za-z0-9_-]{20,}\b",
        r"\bAKIA[0-9A-Z]{16}\b",
        r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b",
        r"\b(?:api[_ -]?key|token|password|senha|secret)\s*[:=]\s*[^\s,;]{8,}",
    )
)


def rollback_output_validation(
    profile: RagOutputValidationProfile,
    actor_id: uuid.UUID,
    *,
    reason: str,
) -> RagOutputValidationProfile:
    normalized_reason = reason.strip()[:500]
    if not normalized_reason:
        raise ValueError("O motivo do rollback e obrigatorio.")
    now = datetime.now(UTC)
    profile.rollout_state = "ROLLBACK"
    profile.rollout_percentage = 0
    history = list(profile.rollout_history or [])
    history.append(
        {"at": now.isoformat(), "state": "ROLLBACK", "reason": normalized_reason, "manual": True}
    )
    profile.rollout_history = history
    db.session.add(
        AuditLog(
            tenant_id=profile.tenant_id,
            user_id=actor_id,
            action="rag_output_validation.rollout_rolled_back",
            entity_type="rag_output_validation_profile",
            entity_id=str(profile.tenant_id),
            after={"reason": normalized_reason, "percentage": 0},
        )
    )
    return profile
_ACTION_CLAIMS = re.compile(
    r"\b(?:eu |já )?(?:enviei|publiquei|apaguei|excluí|executei|transferi|"
    r"alterei|protocolei)\b",
    re.IGNORECASE,
)
_URL = re.compile(r"https?://[^\s<>\]\)\}\"']+", re.IGNORECASE)
_CITATION = re.compile(r"\[(\d{1,3})\]")


@dataclass(frozen=True)
class OutputValidationDecision:
    status: str
    action: str
    signals: tuple[str, ...]
    policy_version: str
    validator_version: str
    output_hash: str
    validated_at: datetime
    rollout_percentage: int
    rollout_bucket: int
    candidate_selected: bool
    enforced: bool

    def as_dict(self) -> dict:
        return {
            "status": self.status,
            "action": self.action,
            "signals": list(self.signals),
            "policyVersion": self.policy_version,
            "validatorVersion": self.validator_version,
            "outputHash": self.output_hash,
            "validatedAt": self.validated_at.isoformat(),
            "rolloutPercentage": self.rollout_percentage,
            "rolloutBucket": self.rollout_bucket,
            "candidateSelected": self.candidate_selected,
            "enforced": self.enforced,
        }


def validate_and_apply_output(tenant_id: uuid.UUID, query: str, answer: dict) -> dict:
    response = str(answer.get("resposta") or "")
    citations = list(answer.get("citacoes") or [])
    sources = list(answer.get("fontes") or [])
    profile = db.session.get(RagOutputValidationProfile, tenant_id)
    policy_version = (
        profile.policy_version
        if profile
        else str(current_app.config["RAG_OUTPUT_VALIDATION_POLICY_VERSION"])
    )
    validator_version = (
        profile.validator_version
        if profile
        else str(current_app.config["RAG_OUTPUT_VALIDATOR_VERSION"])
    )
    rollout_percentage = _rollout_percentage(profile)
    bucket = int(
        hashlib.sha256(f"{tenant_id}:{validator_version}:{query}".encode()).hexdigest()[:8],
        16,
    ) % 100
    candidate_selected = bucket < rollout_percentage
    signals = _signals(response, citations, sources, grounded=bool(answer.get("fundamentada")))
    critical = bool(set(signals) & CRITICAL_SIGNALS)
    blocked = bool(signals)
    enforced = blocked and (critical or candidate_selected)
    decision = OutputValidationDecision(
        status="BLOCKED" if blocked else "CLEAN",
        action="REFUSE" if enforced else "ALLOW",
        signals=tuple(signals),
        policy_version=policy_version,
        validator_version=validator_version,
        output_hash=hashlib.sha256(response.encode("utf-8")).hexdigest(),
        validated_at=datetime.now(UTC),
        rollout_percentage=rollout_percentage,
        rollout_bucket=bucket,
        candidate_selected=candidate_selected,
        enforced=enforced,
    )
    state = decision.as_dict()
    answer.setdefault("seguranca", {})["saida"] = state
    answer["validacaoSaida"] = state
    if enforced:
        answer["resposta"] = OUTPUT_REFUSAL_MESSAGE
        answer["fundamentada"] = False
        answer["recusaConclusiva"] = True
        answer["fallbackUtilizado"] = True
        generation = dict(answer.get("geracao") or {})
        generation["outputValidationRejected"] = True
        answer["geracao"] = generation
    if profile is not None:
        _record_rollout_sample(profile, decision)
    return state


def start_output_validation_rollout(
    tenant_id: uuid.UUID,
    actor_id: uuid.UUID,
    *,
    stages: list[int] | None = None,
    minimum_samples: int | None = None,
    maximum_block_rate: float | None = None,
) -> RagOutputValidationProfile:
    configured_stages = stages or list(current_app.config["RAG_OUTPUT_ROLLOUT_STAGES"])
    if (
        not configured_stages
        or configured_stages[-1] != 100
        or configured_stages != sorted(set(configured_stages))
        or any(value < 1 or value > 100 for value in configured_stages)
    ):
        raise ValueError("As etapas devem ser crescentes, únicas e terminar em 100.")
    samples = int(
        minimum_samples
        if minimum_samples is not None
        else current_app.config["RAG_OUTPUT_ROLLOUT_MIN_SAMPLES"]
    )
    max_rate = float(
        maximum_block_rate
        if maximum_block_rate is not None
        else current_app.config["RAG_OUTPUT_ROLLOUT_MAX_BLOCK_RATE"]
    )
    if samples < 1 or not 0 <= max_rate <= 1:
        raise ValueError("Gates do rollout inválidos.")
    now = datetime.now(UTC)
    profile = db.session.get(RagOutputValidationProfile, tenant_id)
    if profile is None:
        profile = RagOutputValidationProfile(tenant_id=tenant_id, initiated_by_id=actor_id)
        db.session.add(profile)
    profile.policy_version = str(current_app.config["RAG_OUTPUT_VALIDATION_POLICY_VERSION"])
    profile.validator_version = str(current_app.config["RAG_OUTPUT_VALIDATOR_VERSION"])
    profile.rollout_state = "MONITORANDO"
    profile.rollout_percentage = configured_stages[0]
    profile.rollout_stage_index = 0
    profile.rollout_stages = configured_stages
    profile.minimum_stage_samples = samples
    profile.maximum_block_rate = max_rate
    profile.metrics = _empty_metrics()
    profile.rollout_history = [
        {"at": now.isoformat(), "state": "MONITORANDO", "percentage": configured_stages[0]}
    ]
    profile.initiated_by_id = actor_id
    profile.started_at = now
    profile.updated_at = now
    db.session.add(
        AuditLog(
            tenant_id=tenant_id,
            user_id=actor_id,
            action="rag_output_validation.rollout_started",
            entity_type="rag_output_validation_profile",
            entity_id=str(tenant_id),
            after=output_validation_profile_data(profile),
        )
    )
    return profile


def output_validation_profile_data(profile) -> dict:
    if profile is None:
        return {
            "estado": "BASELINE",
            "percentual": 100,
            "versaoPolitica": current_app.config["RAG_OUTPUT_VALIDATION_POLICY_VERSION"],
            "versaoValidador": current_app.config["RAG_OUTPUT_VALIDATOR_VERSION"],
            "metricas": {},
            "historico": [],
        }
    return {
        "tenantId": str(profile.tenant_id),
        "estado": profile.rollout_state,
        "percentual": profile.rollout_percentage,
        "etapa": profile.rollout_stage_index,
        "etapas": profile.rollout_stages,
        "amostraMinima": profile.minimum_stage_samples,
        "taxaBloqueioMaxima": profile.maximum_block_rate,
        "versaoPolitica": profile.policy_version,
        "versaoValidador": profile.validator_version,
        "metricas": profile.metrics,
        "historico": profile.rollout_history,
        "iniciadoEm": profile.started_at.isoformat(),
        "atualizadoEm": profile.updated_at.isoformat() if profile.updated_at else None,
    }


def _signals(response: str, citations: list, sources: list, *, grounded: bool) -> list[str]:
    signals = []
    if any(pattern.search(response) for pattern in _PROMPT_LEAKAGE):
        signals.append("PROMPT_OR_INSTRUCTION_LEAKAGE")
    if any(pattern.search(response) for pattern in _SECRETS):
        signals.append("SECRET_OR_CREDENTIAL_LEAKAGE")
    if _ACTION_CLAIMS.search(response):
        signals.append("UNAUTHORIZED_ACTION_CLAIM")

    allowed_hosts = {
        urlsplit(str(source.get("urlFonte") or "")).hostname
        for source in sources
        if source.get("urlFonte")
    }
    output_hosts = {urlsplit(url.rstrip(".,;:")).hostname for url in _URL.findall(response)}
    if any(host and host not in allowed_hosts for host in output_hosts):
        signals.append("UNAPPROVED_EXTERNAL_DESTINATION")

    allowed_citations = {int(item["numero"]) for item in citations if "numero" in item}
    used_citations = {int(value) for value in _CITATION.findall(response)}
    if used_citations - allowed_citations:
        signals.append("INVALID_CITATION_REFERENCE")
    if grounded and citations and not used_citations:
        signals.append("CITATION_REFERENCE_MISSING")
    return list(dict.fromkeys(signals))


def _rollout_percentage(profile) -> int:
    if profile is None or profile.rollout_state == "PROMOVIDO":
        return 100
    if profile.rollout_state in {"ROLLBACK", "ERRO"}:
        return 0
    return max(0, min(100, profile.rollout_percentage))


def _record_rollout_sample(profile, decision: OutputValidationDecision) -> None:
    metrics = dict(profile.metrics or _empty_metrics())
    metrics["totalSamples"] = int(metrics.get("totalSamples", 0)) + 1
    metrics["blockedSamples"] = int(metrics.get("blockedSamples", 0)) + int(
        decision.status == "BLOCKED"
    )
    metrics["enforcedSamples"] = int(metrics.get("enforcedSamples", 0)) + int(
        decision.enforced
    )
    if decision.candidate_selected:
        metrics["stageSamples"] = int(metrics.get("stageSamples", 0)) + 1
        metrics["stageBlocked"] = int(metrics.get("stageBlocked", 0)) + int(
            decision.status == "BLOCKED"
        )
    profile.metrics = metrics
    if profile.rollout_state != "MONITORANDO":
        return
    stage_samples = int(metrics.get("stageSamples", 0))
    if stage_samples < profile.minimum_stage_samples:
        return
    block_rate = int(metrics.get("stageBlocked", 0)) / stage_samples
    now = datetime.now(UTC)
    history = list(profile.rollout_history or [])
    if block_rate > profile.maximum_block_rate:
        profile.rollout_state = "ROLLBACK"
        profile.rollout_percentage = 0
        history.append(
            {
                "at": now.isoformat(),
                "state": "ROLLBACK",
                "blockRate": round(block_rate, 6),
                "samples": stage_samples,
            }
        )
    else:
        next_index = profile.rollout_stage_index + 1
        if next_index >= len(profile.rollout_stages):
            profile.rollout_state = "PROMOVIDO"
            profile.rollout_percentage = 100
            state = "PROMOVIDO"
        else:
            profile.rollout_stage_index = next_index
            profile.rollout_percentage = profile.rollout_stages[next_index]
            state = "MONITORANDO"
        history.append(
            {
                "at": now.isoformat(),
                "state": state,
                "percentage": profile.rollout_percentage,
                "blockRate": round(block_rate, 6),
                "samples": stage_samples,
            }
        )
        metrics["stageSamples"] = 0
        metrics["stageBlocked"] = 0
        profile.metrics = metrics
    profile.rollout_history = history


def _empty_metrics() -> dict:
    return {
        "totalSamples": 0,
        "blockedSamples": 0,
        "enforcedSamples": 0,
        "stageSamples": 0,
        "stageBlocked": 0,
    }
