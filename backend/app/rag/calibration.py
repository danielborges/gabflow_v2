import hashlib
import json
import uuid
from datetime import UTC, timedelta

from flask import current_app
from sqlalchemy import func, select

from app.audit import add_audit
from app.extensions import db
from app.models import (
    OutboxEvent,
    RagLearningArtifact,
    RagLearningArtifactStatus,
    RagLearningArtifactType,
    RagLearningRun,
    RagLearningRunStatus,
    Tenant,
    utc_now,
)
from app.rag.learning import (
    LearningValidationError,
    activate_learning_artifact,
    active_learning_artifacts,
    evaluate_learning_artifact,
    rollback_learning_artifact,
)

QUALITY_PROFILE_SCHEMA = "rag-quality-profile-v1"
QUALITY_CALIBRATION_EVENT = "AvaliacaoPerfilQualidadeRag"
QUALITY_ROLLOUT_EVENT = "AvaliacaoRolloutPerfilQualidadeRag"
QUALITY_PARAMETER_RANGES = {
    "retrievalScoreThreshold": (0.05, 0.95),
    "minEvidenceScore": (0.05, 0.95),
    "neuralMinScore": (0.0, 1.0),
    "citationLexicalThreshold": (0.0, 1.0),
    "entailmentMinScore": (0.0, 1.0),
}


def default_quality_parameters() -> dict:
    return {
        "retrievalScoreThreshold": float(
            current_app.config["RAG_RETRIEVAL_SCORE_THRESHOLD"]
        ),
        "minEvidenceScore": float(
            current_app.config["RAG_RETRIEVAL_MIN_EVIDENCE_SCORE"]
        ),
        "neuralMinScore": float(
            current_app.config["RAG_NEURAL_RERANK_MIN_SCORE"]
        ),
        "citationLexicalThreshold": float(
            current_app.config["RAG_ANSWER_CITATION_SUPPORT_THRESHOLD"]
        ),
        "entailmentMinScore": float(
            current_app.config["RAG_NLI_MIN_SCORE"]
        ),
    }


def quality_parameters_from_artifact(item: RagLearningArtifact | None) -> dict:
    defaults = default_quality_parameters()
    if item is None or item.artifact_type != RagLearningArtifactType.QUALITY_PROFILE:
        return defaults
    values = item.payload.get("parametros")
    if not isinstance(values, dict):
        return defaults
    return {
        key: float(values.get(key, default))
        for key, default in defaults.items()
    }


def create_quality_calibration(
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    role: str | None,
    payload: dict,
) -> RagLearningArtifact:
    if not isinstance(payload, dict):
        raise LearningValidationError("O corpo da calibração deve ser um objeto.")
    unknown = set(payload) - {"parametros", "k", "justificativaSemMelhora"}
    if unknown:
        raise LearningValidationError(
            f"Campos de calibração não permitidos: {', '.join(sorted(unknown))}."
        )
    requested = payload.get("parametros")
    if not isinstance(requested, dict) or not requested:
        raise LearningValidationError(
            "Informe ao menos um parâmetro candidato para calibração."
        )
    unknown_parameters = set(requested) - set(QUALITY_PARAMETER_RANGES)
    if unknown_parameters:
        raise LearningValidationError(
            "Parâmetros de qualidade não permitidos: "
            f"{', '.join(sorted(unknown_parameters))}."
        )
    active = active_learning_artifacts(tenant_id, force_all=True)
    current_profile = active.get(RagLearningArtifactType.QUALITY_PROFILE)
    baseline_parameters = quality_parameters_from_artifact(current_profile)
    candidate_parameters = dict(baseline_parameters)
    for key, value in requested.items():
        if isinstance(value, bool):
            raise LearningValidationError(f"{key} deve ser numérico.")
        try:
            normalized = float(value)
        except (TypeError, ValueError) as error:
            raise LearningValidationError(f"{key} deve ser numérico.") from error
        minimum, maximum = QUALITY_PARAMETER_RANGES[key]
        if not minimum <= normalized <= maximum:
            raise LearningValidationError(
                f"{key} deve estar entre {minimum} e {maximum}."
            )
        candidate_parameters[key] = normalized
    if (
        candidate_parameters["retrievalScoreThreshold"]
        > candidate_parameters["minEvidenceScore"]
    ):
        raise LearningValidationError(
            "retrievalScoreThreshold não pode superar minEvidenceScore."
        )
    if candidate_parameters == baseline_parameters:
        raise LearningValidationError(
            "O perfil candidato deve alterar ao menos um parâmetro efetivo."
        )
    k = payload.get("k", current_app.config["RAG_LEARNING_EVALUATION_K"])
    try:
        k = max(1, min(int(k), 10))
    except (TypeError, ValueError) as error:
        raise LearningValidationError("k deve ser um inteiro entre 1 e 10.") from error

    now = utc_now()
    configuration = {
        "origin": "QUALITY_CALIBRATION",
        "schemaVersion": QUALITY_PROFILE_SCHEMA,
        "baselineParameters": baseline_parameters,
        "candidateParameters": candidate_parameters,
        "k": k,
        "role": role,
        "humanJustification": payload.get("justificativaSemMelhora"),
        "minimumSignals": 0,
        "smallSampleExplicitlyApproved": True,
    }
    run = RagLearningRun(
        tenant_id=tenant_id,
        window_start=now - timedelta(microseconds=1),
        window_end=now,
        configuration=configuration,
        configuration_hash=_hash(configuration),
        baseline={"parametros": baseline_parameters},
        status=RagLearningRunStatus.PENDENTE,
        initiated_by_id=user_id,
    )
    db.session.add(run)
    db.session.flush()
    latest_version = db.session.scalar(
        select(func.max(RagLearningArtifact.version)).where(
            RagLearningArtifact.tenant_id == tenant_id,
            RagLearningArtifact.artifact_type
            == RagLearningArtifactType.QUALITY_PROFILE,
        )
    )
    artifact_payload = {
        "schemaVersion": QUALITY_PROFILE_SCHEMA,
        "parametros": candidate_parameters,
        "baselineParametros": baseline_parameters,
    }
    artifact = RagLearningArtifact(
        tenant_id=tenant_id,
        run_id=run.id,
        artifact_type=RagLearningArtifactType.QUALITY_PROFILE,
        version=(latest_version or 0) + 1,
        payload=artifact_payload,
        payload_hash=_hash(artifact_payload),
        source_feedback_ids=[],
        baseline={"parametros": baseline_parameters},
        status=RagLearningArtifactStatus.CANDIDATO,
    )
    db.session.add(artifact)
    db.session.flush()
    db.session.add(
        OutboxEvent(
            tenant_id=tenant_id,
            event_type=QUALITY_CALIBRATION_EVENT,
            aggregate_type="PerfilQualidadeRag",
            aggregate_id=str(artifact.id),
            payload={"artifactId": str(artifact.id)},
        )
    )
    add_audit(
        tenant_id,
        user_id,
        "rag_quality.calibration_requested",
        "rag_learning_artifact",
        artifact.id,
        after={
            "versao": artifact.version,
            "parametrosBase": baseline_parameters,
            "parametrosCandidatos": candidate_parameters,
            "k": k,
        },
    )
    return artifact


def execute_quality_calibration(artifact: RagLearningArtifact) -> None:
    run = db.session.scalar(
        select(RagLearningRun).where(
            RagLearningRun.tenant_id == artifact.tenant_id,
            RagLearningRun.id == artifact.run_id,
        )
    )
    if run is None:
        raise LearningValidationError("Execução da calibração não encontrada.")
    if run.status == RagLearningRunStatus.CONCLUIDA:
        return
    run.status = RagLearningRunStatus.PROCESSANDO
    run.error = None
    db.session.flush()
    approved, reasons = evaluate_learning_artifact(
        artifact,
        run.initiated_by_id,
        str(run.configuration.get("role") or "admin"),
        {
            "k": int(run.configuration.get("k") or 5),
            "justificativaSemMelhora": run.configuration.get(
                "humanJustification"
            ),
        },
    )
    run.metrics = {
        "antes": artifact.metrics_before,
        "depois": artifact.metrics_after,
        "aprovado": approved,
        "motivos": reasons,
    }
    run.status = RagLearningRunStatus.CONCLUIDA
    run.completed_at = utc_now()
    if approved:
        start_quality_rollout(artifact, run.initiated_by_id)
    add_audit(
        artifact.tenant_id,
        run.initiated_by_id,
        "rag_quality.calibration_completed",
        "rag_learning_artifact",
        artifact.id,
        after={
            "versao": artifact.version,
            "aprovado": approved,
            "parametrosBase": run.configuration.get("baselineParameters", {}),
            "parametrosCandidatos": run.configuration.get(
                "candidateParameters",
                {},
            ),
            "motivos": reasons or ["GATES_ATENDIDOS"],
        },
    )


def fail_quality_calibration(
    artifact: RagLearningArtifact,
    error_message: str,
) -> None:
    run = db.session.scalar(
        select(RagLearningRun).where(
            RagLearningRun.tenant_id == artifact.tenant_id,
            RagLearningRun.id == artifact.run_id,
        )
    )
    if run is not None:
        run.status = RagLearningRunStatus.ERRO
        run.error = error_message[:2000]
        run.completed_at = utc_now()
    if artifact.status in {
        RagLearningArtifactStatus.CANDIDATO,
        RagLearningArtifactStatus.EM_AVALIACAO,
    }:
        artifact.status = RagLearningArtifactStatus.REJEITADO
        artifact.evaluation_details = {
            "decision": "REJEITADO",
            "reasons": ["ERRO_NA_CALIBRACAO"],
            "error": error_message[:300],
            "evaluatedAt": utc_now().isoformat(),
        }


def start_quality_rollout(
    artifact: RagLearningArtifact,
    actor_id: uuid.UUID,
) -> None:
    if artifact.artifact_type != RagLearningArtifactType.QUALITY_PROFILE:
        raise LearningValidationError("Somente perfil de qualidade aceita rollout.")
    stages = _rollout_stages()
    first_stage = stages[0]
    activate_learning_artifact(
        artifact,
        actor_id,
        {"percentualCanario": first_stage},
    )
    now = utc_now()
    artifact.rollout_state = "MONITORANDO"
    artifact.rollout_stage_index = 0
    artifact.rollout_started_at = now
    artifact.rollout_stage_started_at = now
    artifact.rollout_history = [
        {
            "etapa": 0,
            "percentual": first_stage,
            "estado": "INICIADA",
            "instante": now.isoformat(),
        }
    ]
    _schedule_rollout_check(artifact, now=now)
    add_audit(
        artifact.tenant_id,
        actor_id,
        "rag_quality.rollout_started",
        "rag_learning_artifact",
        artifact.id,
        after={"etapas": stages, "percentual": first_stage},
    )


def execute_quality_rollout_check(
    artifact: RagLearningArtifact,
    *,
    expected_stage_index: int | None = None,
) -> None:
    db.session.scalar(
        select(Tenant).where(Tenant.id == artifact.tenant_id).with_for_update()
    )
    db.session.refresh(artifact)
    if artifact.artifact_type != RagLearningArtifactType.QUALITY_PROFILE:
        raise LearningValidationError("Artefato de rollout inválido.")
    if (
        artifact.status != RagLearningArtifactStatus.ATIVO
        or artifact.rollout_state != "MONITORANDO"
    ):
        return
    if (
        expected_stage_index is not None
        and artifact.rollout_stage_index != expected_stage_index
    ):
        return
    now = utc_now()
    metrics = dict(artifact.online_metrics or {})
    samples = int(metrics.get("stageQualitySamples", 0))
    minimum_samples = max(
        1, int(current_app.config["RAG_QUALITY_ROLLOUT_MIN_SAMPLES"])
    )
    minimum_window = max(
        0, int(current_app.config["RAG_QUALITY_ROLLOUT_MIN_WINDOW_SECONDS"])
    )
    stage_started = artifact.rollout_stage_started_at or now
    if stage_started.tzinfo is None:
        stage_started = stage_started.replace(tzinfo=UTC)
    elapsed = max(0, int((now - stage_started).total_seconds()))
    if samples < minimum_samples or elapsed < minimum_window:
        _schedule_rollout_check(artifact, now=now)
        return

    gates = _online_rollout_gates(metrics)
    history = list(artifact.rollout_history or [])
    snapshot = {
        "etapa": artifact.rollout_stage_index,
        "percentual": artifact.rollout_percentage,
        "estado": "REPROVADA" if gates else "APROVADA",
        "instante": now.isoformat(),
        "amostras": samples,
        "janelaSegundos": elapsed,
        "metricas": {
            "fallbackRate": float(metrics.get("stageFallbackRate", 0)),
            "semanticRejectionRate": float(
                metrics.get("stageSemanticRejectionRate", 0)
            ),
            "refusalRate": float(metrics.get("stageRefusalRate", 0)),
            "negativeRate": float(metrics.get("stageNegativeRate", 0)),
            "latencyBudgetExceededRate": float(
                metrics.get("stageLatencyBudgetExceededRate", 0)
            ),
        },
        "motivos": gates or ["GATES_ONLINE_ATENDIDOS"],
    }
    history.append(snapshot)
    artifact.rollout_history = history
    actor_id = artifact.activated_by_id
    if actor_id is None:
        raise LearningValidationError("Rollout sem responsável pela ativação.")
    if gates:
        artifact.rollout_state = "ROLLBACK"
        artifact.rollout_next_check_at = None
        rollback_learning_artifact(
            artifact,
            actor_id,
            "Rollout automático reprovado: " + ", ".join(gates),
            automatic=True,
        )
        return

    stages = _rollout_stages()
    next_index = artifact.rollout_stage_index + 1
    if next_index >= len(stages):
        artifact.rollout_state = "PROMOVIDO"
        artifact.rollout_next_check_at = None
        artifact.activation_mode = "TOTAL"
        add_audit(
            artifact.tenant_id,
            actor_id,
            "rag_quality.rollout_promoted",
            "rag_learning_artifact",
            artifact.id,
            after={
                "percentual": artifact.rollout_percentage,
                "etapasConcluidas": len(stages),
            },
        )
        return

    next_percentage = stages[next_index]
    activate_learning_artifact(
        artifact,
        actor_id,
        {"percentualCanario": next_percentage},
    )
    artifact.rollout_stage_index = next_index
    artifact.rollout_stage_started_at = now
    reset = dict(artifact.online_metrics or {})
    reset.update(
        {
            "stageQualitySamples": 0,
            "stageGenerationFallbacks": 0,
            "stageSemanticRejections": 0,
            "stageRefusedQueries": 0,
            "stageFallbackRate": 0.0,
            "stageSemanticRejectionRate": 0.0,
            "stageRefusalRate": 0.0,
            "stageRatedQueries": 0,
            "stageNegativeRatings": 0,
            "stageNegativeRate": 0.0,
            "stageLatencyBudgetExceeded": 0,
            "stageLatencyBudgetExceededRate": 0.0,
        }
    )
    artifact.online_metrics = reset
    history.append(
        {
            "etapa": next_index,
            "percentual": next_percentage,
            "estado": "INICIADA",
            "instante": now.isoformat(),
        }
    )
    artifact.rollout_history = history
    _schedule_rollout_check(artifact, now=now)


def fail_quality_rollout(
    artifact: RagLearningArtifact,
    error_message: str,
) -> None:
    if (
        artifact.status == RagLearningArtifactStatus.ATIVO
        and artifact.rollout_state == "MONITORANDO"
        and artifact.activated_by_id is not None
    ):
        artifact.rollout_state = "ERRO"
        artifact.rollout_next_check_at = None
        rollback_learning_artifact(
            artifact,
            artifact.activated_by_id,
            "Falha permanente no monitoramento do rollout: "
            + str(error_message)[:500],
            automatic=True,
        )


def _online_rollout_gates(metrics: dict) -> list[str]:
    gates = []
    values = {
        "FALLBACK": (
            float(metrics.get("stageFallbackRate", 0)),
            float(current_app.config["RAG_QUALITY_ONLINE_MAX_FALLBACK_RATE"]),
            "fallbackRate",
        ),
        "REJEICAO_SEMANTICA": (
            float(metrics.get("stageSemanticRejectionRate", 0)),
            float(
                current_app.config[
                    "RAG_QUALITY_ONLINE_MAX_SEMANTIC_REJECTION_RATE"
                ]
            ),
            "semanticRejectionRate",
        ),
        "RECUSA": (
            float(metrics.get("stageRefusalRate", 0)),
            float(current_app.config["RAG_QUALITY_ONLINE_MAX_REFUSAL_RATE"]),
            "refusalRate",
        ),
        "FEEDBACK_NEGATIVO": (
            float(metrics.get("stageNegativeRate", 0)),
            float(current_app.config["RAG_LEARNING_ONLINE_MAX_NEGATIVE_RATE"]),
            "negativeRate",
        ),
        "LATENCIA": (
            float(metrics.get("stageLatencyBudgetExceededRate", 0)),
            float(
                current_app.config[
                    "RAG_QUALITY_ONLINE_MAX_LATENCY_BUDGET_RATE"
                ]
            ),
            "latencyBudgetExceededRate",
        ),
    }
    baseline = metrics.get("rolloutBaselineMetrics") or {}
    tolerance = max(
        0.0,
        float(current_app.config["RAG_QUALITY_ROLLOUT_MAX_RATE_REGRESSION"]),
    )
    for name, (value, maximum, baseline_key) in values.items():
        if value > maximum:
            gates.append(f"TAXA_{name}_ACIMA_DO_LIMITE")
        baseline_samples = int(
            baseline.get(
                "qualitySamples"
                if baseline_key != "negativeRate"
                else "ratedQueries",
                0,
            )
        )
        if baseline_samples > 0:
            baseline_value = float(baseline.get(baseline_key, 0))
            if value - baseline_value > tolerance:
                gates.append(f"REGRESSAO_ONLINE_{name}")
    return sorted(set(gates))


def _rollout_stages() -> list[int]:
    raw = str(current_app.config["RAG_QUALITY_ROLLOUT_STAGES"])
    try:
        stages = [int(value.strip()) for value in raw.split(",") if value.strip()]
    except ValueError as error:
        raise LearningValidationError(
            "RAG_QUALITY_ROLLOUT_STAGES deve conter percentuais inteiros."
        ) from error
    if (
        not stages
        or stages[-1] != 100
        or any(value < 1 or value > 100 for value in stages)
        or stages != sorted(set(stages))
    ):
        raise LearningValidationError(
            "As etapas do rollout devem ser crescentes, únicas e terminar em 100."
        )
    return stages


def _schedule_rollout_check(
    artifact: RagLearningArtifact,
    *,
    now,
) -> None:
    delay = max(
        0,
        int(current_app.config["RAG_QUALITY_ROLLOUT_CHECK_INTERVAL_SECONDS"]),
    )
    available_at = now + timedelta(seconds=delay)
    artifact.rollout_next_check_at = available_at
    db.session.add(
        OutboxEvent(
            tenant_id=artifact.tenant_id,
            event_type=QUALITY_ROLLOUT_EVENT,
            aggregate_type="PerfilQualidadeRag",
            aggregate_id=str(artifact.id),
            payload={
                "artifactId": str(artifact.id),
                "stageIndex": artifact.rollout_stage_index,
            },
            available_at=available_at,
        )
    )


def validate_quality_profile_payload(payload: dict) -> list[str]:
    if not isinstance(payload, dict):
        return ["PERFIL_QUALIDADE_INVALIDO"]
    if payload.get("schemaVersion") != QUALITY_PROFILE_SCHEMA:
        return ["VERSAO_SCHEMA_PERFIL_QUALIDADE_INVALIDA"]
    parameters = payload.get("parametros")
    if not isinstance(parameters, dict) or set(parameters) != set(
        QUALITY_PARAMETER_RANGES
    ):
        return ["PARAMETROS_PERFIL_QUALIDADE_INVALIDOS"]
    errors = []
    for key, (minimum, maximum) in QUALITY_PARAMETER_RANGES.items():
        value = parameters.get(key)
        if (
            isinstance(value, bool)
            or not isinstance(value, int | float)
            or not minimum <= float(value) <= maximum
        ):
            errors.append(f"PARAMETRO_INVALIDO_{key.upper()}")
    if (
        not errors
        and float(parameters["retrievalScoreThreshold"])
        > float(parameters["minEvidenceScore"])
    ):
        errors.append("LIMIARES_RETRIEVAL_INCONSISTENTES")
    return errors


def _hash(value: dict) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
