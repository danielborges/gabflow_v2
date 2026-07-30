import hashlib
import json
import math
import uuid
from collections import defaultdict
from datetime import UTC, datetime, timedelta

from flask import current_app
from sqlalchemy import func, select

from app.audit import add_audit
from app.extensions import db
from app.models import (
    AuditLog,
    OutboxEvent,
    RagAssistantQuery,
    RagDocument,
    RagDocumentVersion,
    RagEvaluationQuestion,
    RagEvaluationRun,
    RagFeedbackSourceJudgment,
    RagFeedbackSourceJudgmentValue,
    RagFeedbackStatus,
    RagLearningArtifact,
    RagLearningArtifactFeedback,
    RagLearningArtifactStatus,
    RagLearningArtifactType,
    RagLearningRun,
    RagLearningRunStatus,
    RagQueryFeedback,
    RagQueryFeedbackRating,
    Tenant,
    utc_now,
)

LEARNING_COMPILATION_EVENT = "CompilacaoSinaisRag"
SCHEMA_VERSION = "rag-learning-candidate-v1"
MAX_WINDOW_DAYS = 366
REQUEST_KEYS = {
    "inicio",
    "fim",
    "tiposArtefato",
    "permitirAmostraPequena",
}


class LearningValidationError(ValueError):
    pass


class LearningConflictError(ValueError):
    pass


def active_learning_artifacts(
    tenant_id: uuid.UUID,
    *,
    canary_key: str | None = None,
    force_all: bool = False,
) -> dict:
    items = db.session.scalars(
        select(RagLearningArtifact).where(
            RagLearningArtifact.tenant_id == tenant_id,
            RagLearningArtifact.status == RagLearningArtifactStatus.ATIVO,
        )
    )
    result = {}
    for item in items:
        percentage = max(0, min(100, item.rollout_percentage))
        if not force_all and canary_key is not None:
            bucket = int(
                hashlib.sha256(
                    f"{tenant_id}:{item.id}:{canary_key}".encode()
                ).hexdigest()[:8],
                16,
            ) % 100
            if bucket >= percentage:
                continue
        result[item.artifact_type] = item
    return result


def learning_influence_data(item: RagLearningArtifact) -> dict:
    return {
        "id": str(item.id),
        "tipo": item.artifact_type.value,
        "versao": item.version,
        "modoAtivacao": item.activation_mode,
        "percentualCanario": item.rollout_percentage,
    }


def evaluate_learning_artifact(
    item: RagLearningArtifact,
    user_id: uuid.UUID,
    role: str | None,
    payload: dict,
) -> tuple[bool, list[str]]:
    if not isinstance(payload, dict):
        raise LearningValidationError("O corpo da avaliação deve ser um objeto.")
    unknown = set(payload) - {"k", "justificativaSemMelhora"}
    if unknown:
        raise LearningValidationError(
            f"Campos de avaliação não permitidos: {', '.join(sorted(unknown))}."
        )
    if item.status not in {
        RagLearningArtifactStatus.CANDIDATO,
        RagLearningArtifactStatus.REJEITADO,
    }:
        raise LearningConflictError(
            f"Artefato no estado {item.status.value} não pode ser avaliado."
        )
    k = payload.get("k", current_app.config["RAG_LEARNING_EVALUATION_K"])
    try:
        k = max(1, min(int(k), 10))
    except (TypeError, ValueError) as error:
        raise LearningValidationError("k deve ser um inteiro entre 1 e 10.") from error
    justification = _optional_reason(payload.get("justificativaSemMelhora"))

    db.session.scalar(
        select(Tenant).where(Tenant.id == item.tenant_id).with_for_update()
    )
    db.session.refresh(item)
    if item.status not in {
        RagLearningArtifactStatus.CANDIDATO,
        RagLearningArtifactStatus.REJEITADO,
    }:
        raise LearningConflictError(
            f"Artefato no estado {item.status.value} não pode ser avaliado."
        )
    item.status = RagLearningArtifactStatus.EM_AVALIACAO
    db.session.flush()
    eligibility_errors = _artifact_eligibility_errors(item)
    if eligibility_errors:
        return _reject_evaluation(item, user_id, eligibility_errors, k)

    from app.rag.curation import reconcile_curated_questions
    from app.rag.evaluation import evaluate_tenant_dataset

    reconcile_curated_questions(item.tenant_id, user_id)
    baseline_artifacts = active_learning_artifacts(
        item.tenant_id,
        force_all=True,
    )
    baseline = evaluate_tenant_dataset(
        item.tenant_id,
        role,
        k=k,
        learning_artifacts=baseline_artifacts,
    )
    candidate_artifacts = dict(baseline_artifacts)
    candidate_artifacts[item.artifact_type] = item
    candidate = evaluate_tenant_dataset(
        item.tenant_id,
        role,
        k=k,
        learning_artifacts=candidate_artifacts,
    )
    before = baseline["metrics"]
    after = candidate["metrics"]
    gate = _quality_gate(item.artifact_type, before, after)
    errors = list(gate["regressions"])
    if not gate["improved"] and not justification:
        errors.append("SEM_MELHORIA_NA_METRICA_ALVO")

    item.metrics_before = before
    item.metrics_after = after
    item.evaluation_details = {
        "k": k,
        "datasetQuestions": baseline["questionCount"],
        "baselineResults": baseline["results"],
        "candidateResults": candidate["results"],
        "comparisons": gate["comparisons"],
        "targetMetrics": gate["targetMetrics"],
        "improvedTarget": gate["improved"],
        "humanJustification": justification,
        "evaluatedAt": utc_now().isoformat(),
        "decision": "REJEITADO" if errors else "APROVADO",
        "reasons": errors or ["GATES_ATENDIDOS"],
    }
    if errors:
        item.status = RagLearningArtifactStatus.REJEITADO
    else:
        item.status = RagLearningArtifactStatus.APROVADO
        item.approved_by_id = user_id
        item.approved_at = utc_now()
    add_audit(
        item.tenant_id,
        user_id,
        "rag_learning.artifact_evaluated",
        "rag_learning_artifact",
        item.id,
        after={
            "tipo": item.artifact_type.value,
            "versao": item.version,
            "decisao": item.status.value,
            "k": k,
            "motivos": item.evaluation_details["reasons"],
            "metricasAntes": before,
            "metricasDepois": after,
            "justificativaHumana": bool(justification),
        },
    )
    return not errors, errors


def activate_learning_artifact(
    item: RagLearningArtifact,
    user_id: uuid.UUID,
    payload: dict,
) -> None:
    if not isinstance(payload, dict):
        raise LearningValidationError("O corpo da ativação deve ser um objeto.")
    unknown = set(payload) - {"percentualCanario"}
    if unknown:
        raise LearningValidationError(
            f"Campos de ativação não permitidos: {', '.join(sorted(unknown))}."
        )
    percentage = payload.get(
        "percentualCanario",
        current_app.config["RAG_LEARNING_CANARY_PERCENT"],
    )
    if isinstance(percentage, bool):
        raise LearningValidationError(
            "percentualCanario deve ser um inteiro entre 1 e 100."
        )
    try:
        percentage = int(percentage)
    except (TypeError, ValueError) as error:
        raise LearningValidationError(
            "percentualCanario deve ser um inteiro entre 1 e 100."
        ) from error
    if not 1 <= percentage <= 100:
        raise LearningValidationError(
            "percentualCanario deve ser um inteiro entre 1 e 100."
        )

    db.session.scalar(
        select(Tenant).where(Tenant.id == item.tenant_id).with_for_update()
    )
    db.session.refresh(item)
    if item.status == RagLearningArtifactStatus.ATIVO:
        if percentage < item.rollout_percentage:
            raise LearningConflictError(
                "A expansão do canário não pode reduzir o percentual ativo."
            )
        before = item.rollout_percentage
        item.rollout_percentage = percentage
        item.activation_mode = "TOTAL" if percentage == 100 else "CANARIO"
        add_audit(
            item.tenant_id,
            user_id,
            "rag_learning.canary_expanded",
            "rag_learning_artifact",
            item.id,
            before={"percentualCanario": before},
            after={"percentualCanario": percentage},
        )
        return
    if item.status != RagLearningArtifactStatus.APROVADO:
        raise LearningConflictError(
            "Somente artefato aprovado nos gates de qualidade pode ser ativado."
        )

    current = db.session.scalar(
        select(RagLearningArtifact)
        .where(
            RagLearningArtifact.tenant_id == item.tenant_id,
            RagLearningArtifact.artifact_type == item.artifact_type,
            RagLearningArtifact.status == RagLearningArtifactStatus.ATIVO,
        )
        .with_for_update()
    )
    if current is not None:
        current.status = RagLearningArtifactStatus.SUBSTITUIDO
        current.replaced_by_id = item.id
    now = utc_now()
    item.status = RagLearningArtifactStatus.ATIVO
    item.activated_by_id = user_id
    item.activated_at = now
    item.activation_mode = "TOTAL" if percentage == 100 else "CANARIO"
    item.rollout_percentage = percentage
    item.online_metrics = {
        "influencedQueries": 0,
        "ratedQueries": 0,
        "positiveRatings": 0,
        "negativeRatings": 0,
        "negativeRate": 0.0,
        "activatedAt": now.isoformat(),
    }
    add_audit(
        item.tenant_id,
        user_id,
        "rag_learning.artifact_activated",
        "rag_learning_artifact",
        item.id,
        after={
            "tipo": item.artifact_type.value,
            "versao": item.version,
            "modo": item.activation_mode,
            "percentualCanario": percentage,
            "substituiuId": str(current.id) if current else None,
        },
    )


def rollback_learning_artifact(
    item: RagLearningArtifact,
    user_id: uuid.UUID,
    reason: object,
    *,
    automatic: bool = False,
) -> RagLearningArtifact | None:
    normalized_reason = _optional_reason(reason)
    if not normalized_reason:
        raise LearningValidationError("Informe o motivo do rollback.")
    db.session.scalar(
        select(Tenant).where(Tenant.id == item.tenant_id).with_for_update()
    )
    db.session.refresh(item)
    if item.status != RagLearningArtifactStatus.ATIVO:
        raise LearningConflictError("Somente artefato ativo pode sofrer rollback.")
    previous = db.session.scalar(
        select(RagLearningArtifact)
        .where(
            RagLearningArtifact.tenant_id == item.tenant_id,
            RagLearningArtifact.artifact_type == item.artifact_type,
            RagLearningArtifact.status == RagLearningArtifactStatus.SUBSTITUIDO,
            RagLearningArtifact.replaced_by_id == item.id,
        )
        .order_by(RagLearningArtifact.version.desc())
        .with_for_update()
    )
    if previous is None and not automatic:
        raise LearningConflictError("Não existe versão anterior elegível para rollback.")
    now = utc_now()
    item.status = RagLearningArtifactStatus.REVOGADO
    item.revoked_at = now
    item.revocation_reason = normalized_reason
    item.rollout_percentage = 0
    if previous is not None:
        previous.status = RagLearningArtifactStatus.ATIVO
        previous.activated_by_id = user_id
        previous.activated_at = now
        previous.activation_mode = previous.activation_mode or "TOTAL"
        previous.rollout_percentage = previous.rollout_percentage or 100
    add_audit(
        item.tenant_id,
        user_id,
        (
            "rag_learning.artifact_auto_rollback"
            if automatic
            else "rag_learning.artifact_rollback"
        ),
        "rag_learning_artifact",
        item.id,
        before={"estado": "ATIVO"},
        after={
            "estado": item.status.value,
            "motivo": normalized_reason,
            "versaoRestauradaId": str(previous.id) if previous else None,
        },
    )
    return previous


def record_learning_influence(
    tenant_id: uuid.UUID,
    influences: list[dict],
) -> None:
    for value in influences:
        try:
            artifact_id = uuid.UUID(str(value.get("id")))
        except (AttributeError, TypeError, ValueError):
            continue
        item = db.session.scalar(
            select(RagLearningArtifact).where(
                RagLearningArtifact.tenant_id == tenant_id,
                RagLearningArtifact.id == artifact_id,
                RagLearningArtifact.status == RagLearningArtifactStatus.ATIVO,
            )
        )
        if item is None:
            continue
        metrics = dict(item.online_metrics or {})
        metrics["influencedQueries"] = int(metrics.get("influencedQueries", 0)) + 1
        item.online_metrics = metrics


def record_learning_feedback(feedback: RagQueryFeedback) -> None:
    if feedback.status != RagFeedbackStatus.APROVADO:
        return
    query = db.session.scalar(
        select(RagAssistantQuery).where(
            RagAssistantQuery.tenant_id == feedback.tenant_id,
            RagAssistantQuery.id == feedback.query_id,
        )
    )
    if query is None:
        return
    for value in query.learning_artifacts or []:
        try:
            artifact_id = uuid.UUID(str(value.get("id")))
        except (AttributeError, TypeError, ValueError):
            continue
        item = db.session.scalar(
            select(RagLearningArtifact).where(
                RagLearningArtifact.tenant_id == feedback.tenant_id,
                RagLearningArtifact.id == artifact_id,
                RagLearningArtifact.status == RagLearningArtifactStatus.ATIVO,
            )
        )
        if item is None:
            continue
        metrics = dict(item.online_metrics or {})
        rated = int(metrics.get("ratedQueries", 0)) + 1
        positive = int(metrics.get("positiveRatings", 0))
        negative = int(metrics.get("negativeRatings", 0))
        if feedback.rating == RagQueryFeedbackRating.POSITIVA:
            positive += 1
        else:
            negative += 1
        negative_rate = negative / rated
        metrics.update(
            {
                "ratedQueries": rated,
                "positiveRatings": positive,
                "negativeRatings": negative,
                "negativeRate": round(negative_rate, 6),
                "lastRatingAt": utc_now().isoformat(),
            }
        )
        item.online_metrics = metrics
        minimum = max(
            1,
            int(current_app.config["RAG_LEARNING_ONLINE_MIN_SAMPLES"]),
        )
        maximum = max(
            0.0,
            min(
                1.0,
                float(
                    current_app.config[
                        "RAG_LEARNING_ONLINE_MAX_NEGATIVE_RATE"
                    ]
                ),
            ),
        )
        if rated >= minimum and negative_rate > maximum:
            rollback_learning_artifact(
                item,
                feedback.moderated_by_id or feedback.created_by_id,
                (
                    "Regressão online automática: taxa negativa "
                    f"{negative_rate:.2%} acima de {maximum:.2%}."
                ),
                automatic=True,
            )


def invalidate_learning_for_feedback(
    feedback: RagQueryFeedback,
    actor_id: uuid.UUID,
    reason: str,
) -> int:
    links = list(
        db.session.scalars(
            select(RagLearningArtifactFeedback).where(
                RagLearningArtifactFeedback.tenant_id == feedback.tenant_id,
                RagLearningArtifactFeedback.feedback_id == feedback.id,
            )
        )
    )
    if not links:
        return 0
    artifact_ids = [link.artifact_id for link in links]
    items = list(
        db.session.scalars(
            select(RagLearningArtifact).where(
                RagLearningArtifact.tenant_id == feedback.tenant_id,
                RagLearningArtifact.id.in_(artifact_ids),
                RagLearningArtifact.status.in_(
                    {
                        RagLearningArtifactStatus.CANDIDATO,
                        RagLearningArtifactStatus.EM_AVALIACAO,
                        RagLearningArtifactStatus.APROVADO,
                        RagLearningArtifactStatus.ATIVO,
                        RagLearningArtifactStatus.SUBSTITUIDO,
                    }
                ),
            )
        )
    )
    scheduled_runs = set()
    for item in items:
        was_active = item.status == RagLearningArtifactStatus.ATIVO
        item.status = RagLearningArtifactStatus.REVOGADO
        item.revoked_at = utc_now()
        item.revocation_reason = reason[:2000]
        item.rollout_percentage = 0
        if was_active:
            _restore_previous_eligible(item, actor_id)
        if item.run_id not in scheduled_runs:
            _schedule_recompilation(item, actor_id, feedback.id, reason)
            scheduled_runs.add(item.run_id)
        add_audit(
            item.tenant_id,
            actor_id,
            "rag_learning.artifact_invalidated",
            "rag_learning_artifact",
            item.id,
            after={
                "feedbackId": str(feedback.id),
                "motivo": reason,
                "recompilacaoAgendada": True,
            },
        )
    return len(items)


def invalidate_learning_for_source(
    tenant_id: uuid.UUID,
    document_id: uuid.UUID,
    version_ids: list[uuid.UUID],
    actor_id: uuid.UUID,
    reason: str,
) -> int:
    judgments = list(
        db.session.scalars(
            select(RagFeedbackSourceJudgment).where(
                RagFeedbackSourceJudgment.tenant_id == tenant_id,
                RagFeedbackSourceJudgment.document_id == document_id,
                RagFeedbackSourceJudgment.version_id.in_(version_ids),
            )
        )
    )
    feedback_ids = sorted({item.feedback_id for item in judgments}, key=str)
    feedbacks = (
        list(
            db.session.scalars(
                select(RagQueryFeedback).where(
                    RagQueryFeedback.tenant_id == tenant_id,
                    RagQueryFeedback.id.in_(feedback_ids),
                )
            )
        )
        if feedback_ids
        else []
    )
    return sum(
        invalidate_learning_for_feedback(feedback, actor_id, reason)
        for feedback in feedbacks
    )


def create_learning_run(
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    payload: dict,
) -> tuple[RagLearningRun, bool]:
    if not isinstance(payload, dict):
        raise LearningValidationError("O corpo da compilação deve ser um objeto.")
    unknown = set(payload) - REQUEST_KEYS
    if unknown:
        raise LearningValidationError(
            f"Campos de compilação não permitidos: {', '.join(sorted(unknown))}."
        )

    window_start = _parse_datetime(payload.get("inicio"), "inicio")
    window_end = _parse_datetime(payload.get("fim"), "fim")
    if window_start >= window_end:
        raise LearningValidationError("O início deve ser anterior ao fim da janela.")
    if window_end - window_start > timedelta(days=MAX_WINDOW_DAYS):
        raise LearningValidationError(
            f"A janela de compilação não pode exceder {MAX_WINDOW_DAYS} dias."
        )
    if window_end > datetime.now(UTC) + timedelta(minutes=5):
        raise LearningValidationError("O fim da janela não pode estar no futuro.")

    artifact_types = _artifact_types(payload.get("tiposArtefato"))
    allow_small_sample = payload.get("permitirAmostraPequena", False)
    if not isinstance(allow_small_sample, bool):
        raise LearningValidationError("permitirAmostraPequena deve ser booleano.")
    configuration = {
        "schemaVersion": SCHEMA_VERSION,
        "artifactTypes": [item.value for item in artifact_types],
        "minimumSignals": max(1, current_app.config["RAG_LEARNING_MIN_SIGNALS"]),
        "maximumAdjustment": min(
            0.25,
            max(0.0, current_app.config["RAG_LEARNING_MAX_ADJUSTMENT"]),
        ),
        "decayHalfLifeDays": max(
            1,
            current_app.config["RAG_LEARNING_DECAY_HALF_LIFE_DAYS"],
        ),
        "maximumExamples": max(1, current_app.config["RAG_LEARNING_MAX_EXAMPLES"]),
        "smallSampleExplicitlyApproved": allow_small_sample,
        "smallSampleApprovedById": str(user_id) if allow_small_sample else None,
    }
    configuration_hash = _hash(configuration)
    existing = db.session.scalar(
        select(RagLearningRun).where(
            RagLearningRun.tenant_id == tenant_id,
            RagLearningRun.window_start == window_start,
            RagLearningRun.window_end == window_end,
            RagLearningRun.configuration_hash == configuration_hash,
        )
    )
    if existing is not None:
        return existing, False

    run = RagLearningRun(
        tenant_id=tenant_id,
        window_start=window_start,
        window_end=window_end,
        configuration=configuration,
        configuration_hash=configuration_hash,
        baseline=_baseline_snapshot(tenant_id),
        status=RagLearningRunStatus.PENDENTE,
        initiated_by_id=user_id,
    )
    db.session.add(run)
    db.session.flush()
    db.session.add(
        OutboxEvent(
            tenant_id=tenant_id,
            event_type=LEARNING_COMPILATION_EVENT,
            aggregate_type="ExecucaoAprendizadoRag",
            aggregate_id=str(run.id),
            payload={"runId": str(run.id)},
        )
    )
    add_audit(
        tenant_id,
        user_id,
        "rag_learning.compilation_requested",
        "rag_learning_run",
        run.id,
        after={
            "inicio": window_start.isoformat(),
            "fim": window_end.isoformat(),
            "tipos": configuration["artifactTypes"],
            "configuracaoHash": configuration_hash,
            "amostraPequenaAprovada": allow_small_sample,
        },
    )
    return run, True


def execute_learning_run(run: RagLearningRun) -> None:
    if run.status == RagLearningRunStatus.CONCLUIDA:
        return
    db.session.scalar(
        select(Tenant).where(Tenant.id == run.tenant_id).with_for_update()
    )
    run.status = RagLearningRunStatus.PROCESSANDO
    run.error = None
    db.session.flush()

    feedback_rows = list(
        db.session.execute(
            select(RagQueryFeedback, RagAssistantQuery)
            .join(
                RagAssistantQuery,
                (
                    (RagAssistantQuery.tenant_id == RagQueryFeedback.tenant_id)
                    & (RagAssistantQuery.id == RagQueryFeedback.query_id)
                ),
            )
            .where(
                RagQueryFeedback.tenant_id == run.tenant_id,
                RagQueryFeedback.created_at >= run.window_start,
                RagQueryFeedback.created_at <= run.window_end,
            )
            .order_by(RagQueryFeedback.created_at, RagQueryFeedback.id)
        )
    )
    feedbacks = [row[0] for row in feedback_rows]
    approved_rows = [
        row for row in feedback_rows if row[0].status == RagFeedbackStatus.APROVADO
    ]
    approved_ids = [row[0].id for row in approved_rows]
    judgments = _judgments_by_feedback(run.tenant_id, approved_ids)

    run.total_feedbacks = len(feedbacks)
    run.total_approved = len(approved_rows)
    run.total_quarantine = sum(
        item.status == RagFeedbackStatus.QUARENTENA for item in feedbacks
    )
    minimum = int(run.configuration["minimumSignals"])
    minimum_met = len(approved_rows) >= minimum
    explicitly_approved = bool(
        run.configuration.get("smallSampleExplicitlyApproved")
    )
    artifacts = []
    skipped_unsafe = 0
    if minimum_met or explicitly_approved:
        payloads, skipped_unsafe = _compile_payloads(
            run,
            approved_rows,
            judgments,
        )
        for artifact_type in _configured_types(run):
            compiled = payloads.get(artifact_type)
            if compiled is None or not compiled["feedbackIds"]:
                continue
            artifact = _create_artifact(
                run,
                artifact_type,
                compiled["payload"],
                compiled["feedbackIds"],
                compiled["contributions"],
            )
            artifacts.append(artifact)

    run.metrics = {
        "minimumSignalsMet": minimum_met,
        "smallSampleExplicitlyApproved": explicitly_approved,
        "artifactCount": len(artifacts),
        "approvedSignalCount": len(approved_rows),
        "skippedUnsafeExemplars": skipped_unsafe,
        "artifactCounts": {
            item.artifact_type.value: len(item.source_feedback_ids)
            for item in artifacts
        },
    }
    run.status = RagLearningRunStatus.CONCLUIDA
    run.completed_at = utc_now()
    _add_worker_audit(
        run,
        "rag_learning.compilation_completed",
        "rag_learning_run",
        run.id,
        {
            "estado": run.status.value,
            "feedbacks": run.total_feedbacks,
            "aprovados": run.total_approved,
            "quarentena": run.total_quarantine,
            "artefatos": len(artifacts),
            "minimoAtingido": minimum_met,
        },
    )


def fail_learning_run(run: RagLearningRun, error_message: str) -> None:
    run.status = RagLearningRunStatus.ERRO
    run.error = str(error_message)[:2000]
    run.completed_at = utc_now()


def learning_run_data(item: RagLearningRun) -> dict:
    artifact_count = db.session.scalar(
        select(func.count(RagLearningArtifact.id)).where(
            RagLearningArtifact.tenant_id == item.tenant_id,
            RagLearningArtifact.run_id == item.id,
        )
    )
    return {
        "id": str(item.id),
        "estado": item.status.value,
        "inicio": item.window_start.isoformat(),
        "fim": item.window_end.isoformat(),
        "configuracao": item.configuration,
        "configuracaoHash": item.configuration_hash,
        "baseline": item.baseline,
        "totalFeedbacks": item.total_feedbacks,
        "totalAprovados": item.total_approved,
        "totalQuarentena": item.total_quarantine,
        "quantidadeArtefatos": artifact_count or 0,
        "metricas": item.metrics,
        "erro": item.error,
        "iniciadaPorId": str(item.initiated_by_id),
        "criadoEm": item.created_at.isoformat(),
        "concluidoEm": item.completed_at.isoformat() if item.completed_at else None,
    }


def learning_artifact_data(
    item: RagLearningArtifact,
    *,
    include_payload: bool = False,
) -> dict:
    data = {
        "id": str(item.id),
        "execucaoId": str(item.run_id),
        "tipo": item.artifact_type.value,
        "versao": item.version,
        "estado": item.status.value,
        "payloadHash": item.payload_hash,
        "feedbacksOrigem": item.source_feedback_ids,
        "baseline": item.baseline,
        "metricasAntes": item.metrics_before,
        "metricasDepois": item.metrics_after,
        "detalhesAvaliacao": item.evaluation_details,
        "aprovadoPorId": str(item.approved_by_id) if item.approved_by_id else None,
        "aprovadoEm": item.approved_at.isoformat() if item.approved_at else None,
        "ativadoPorId": str(item.activated_by_id) if item.activated_by_id else None,
        "modoAtivacao": item.activation_mode,
        "percentualCanario": item.rollout_percentage,
        "metricasOnline": item.online_metrics,
        "criadoEm": item.created_at.isoformat(),
        "ativadoEm": item.activated_at.isoformat() if item.activated_at else None,
    }
    if include_payload:
        data["payload"] = item.payload
        data["proveniencia"] = [
            {
                "feedbackId": str(link.feedback_id),
                "contribuicao": link.contribution,
            }
            for link in db.session.scalars(
                select(RagLearningArtifactFeedback)
                .where(
                    RagLearningArtifactFeedback.tenant_id == item.tenant_id,
                    RagLearningArtifactFeedback.artifact_id == item.id,
                )
                .order_by(RagLearningArtifactFeedback.created_at)
            )
        ]
    return data


def _compile_payloads(run, approved_rows, judgments):
    payloads = {}
    rerank = _rerank_payload(run, approved_rows, judgments)
    payloads[RagLearningArtifactType.RERANK_PROFILE] = rerank
    routing = _routing_payload(run, approved_rows)
    payloads[RagLearningArtifactType.ROUTING_EXAMPLES] = routing
    evaluation = _evaluation_payload(run, approved_rows)
    payloads[RagLearningArtifactType.EVALUATION_CASES] = evaluation
    exemplars, skipped = _answer_payload(run, approved_rows, judgments)
    payloads[RagLearningArtifactType.ANSWER_EXEMPLARS] = exemplars
    return payloads, skipped


def _rerank_payload(run, approved_rows, judgments):
    groups = {}
    for feedback, query in approved_rows:
        weight = _decay_weight(
            feedback.created_at,
            run.window_end,
            run.configuration["decayHalfLifeDays"],
        )
        for judgment in judgments.get(feedback.id, []):
            if judgment.judgment not in {
                RagFeedbackSourceJudgmentValue.RELEVANTE,
                RagFeedbackSourceJudgmentValue.IRRELEVANTE,
                RagFeedbackSourceJudgmentValue.AUSENTE,
            }:
                continue
            key = (
                query.query_hash,
                judgment.source_scope,
                str(judgment.document_id),
                str(judgment.version_id),
            )
            group = groups.setdefault(
                key,
                {
                    "queryHash": query.query_hash,
                    "escopo": judgment.source_scope,
                    "documentoId": str(judgment.document_id),
                    "versaoId": str(judgment.version_id),
                    "pesoPositivo": 0.0,
                    "pesoNegativo": 0.0,
                    "quantidadeSinais": 0,
                    "_feedbackIds": set(),
                },
            )
            if judgment.judgment == RagFeedbackSourceJudgmentValue.IRRELEVANTE:
                group["pesoNegativo"] += weight
            else:
                group["pesoPositivo"] += weight
            group["quantidadeSinais"] += 1
            group["_feedbackIds"].add(feedback.id)

    maximum = float(run.configuration["maximumAdjustment"])
    entries = []
    feedback_ids_by_entry = []
    for group in groups.values():
        total = group["pesoPositivo"] + group["pesoNegativo"]
        score = (group["pesoPositivo"] - group["pesoNegativo"]) / total if total else 0
        group["ajuste"] = round(max(-maximum, min(maximum, score * maximum)), 6)
        group["pesoPositivo"] = round(group["pesoPositivo"], 6)
        group["pesoNegativo"] = round(group["pesoNegativo"], 6)
        feedback_ids_by_entry.append(group.pop("_feedbackIds"))
        entries.append(group)
    paired_entries = sorted(
        zip(entries, feedback_ids_by_entry, strict=True),
        key=lambda pair: (
            pair[0]["queryHash"],
            pair[0]["escopo"],
            pair[0]["documentoId"],
            pair[0]["versaoId"],
        )
    )
    selected = paired_entries[: run.configuration["maximumExamples"]]
    contributions = defaultdict(list)
    for _entry, feedback_ids in selected:
        for feedback_id in feedback_ids:
            contributions[feedback_id].append("RERANK_PROFILE")
    return _compiled(
        {
            "schemaVersion": SCHEMA_VERSION,
            "limiarMinimoContinuaObrigatorio": True,
            "ajusteMaximo": maximum,
            "meiaVidaDias": run.configuration["decayHalfLifeDays"],
            "entradas": [entry for entry, _feedback_ids in selected],
        },
        contributions,
    )


def _routing_payload(run, approved_rows):
    contributions = defaultdict(list)
    examples = []
    for feedback, query in approved_rows:
        if len(examples) >= run.configuration["maximumExamples"]:
            break
        if feedback.expected_method is None and not feedback.expected_filters:
            continue
        examples.append(
            {
                "consultaId": str(query.id),
                "consultaHash": query.query_hash,
                "metodoEsperado": feedback.expected_method,
                "filtrosEsperados": feedback.expected_filters,
            }
        )
        contributions[feedback.id].append("ROUTING_EXAMPLES")
    return _compiled(
        {
            "schemaVersion": SCHEMA_VERSION,
            "exemplos": examples,
        },
        contributions,
    )


def _evaluation_payload(run, approved_rows):
    approved_ids = [feedback.id for feedback, _query in approved_rows]
    contributions = defaultdict(list)
    cases = []
    if approved_ids:
        questions = db.session.scalars(
            select(RagEvaluationQuestion)
            .where(
                RagEvaluationQuestion.tenant_id == run.tenant_id,
                RagEvaluationQuestion.active.is_(True),
                RagEvaluationQuestion.source_feedback_id.in_(approved_ids),
            )
            .order_by(RagEvaluationQuestion.created_at)
            .limit(run.configuration["maximumExamples"])
        )
        for question in questions:
            cases.append(
                {
                    "casoId": str(question.id),
                    "feedbackId": str(question.source_feedback_id),
                    "pergunta": question.question,
                    "fontesEsperadas": question.expected_source_refs,
                    "hardNegatives": question.hard_negative_source_refs,
                    "metodoEsperado": question.expected_method,
                    "filtrosEsperados": question.expected_filters,
                    "esperaRecusa": question.expected_refusal,
                }
            )
            contributions[question.source_feedback_id].append("EVALUATION_CASES")
    return _compiled(
        {"schemaVersion": SCHEMA_VERSION, "casos": cases},
        contributions,
    )


def _answer_payload(run, approved_rows, judgments):
    from app.rag.content_security import has_prompt_injection

    contributions = defaultdict(list)
    exemplars = []
    skipped = 0
    for feedback, query in approved_rows:
        if len(exemplars) >= run.configuration["maximumExamples"]:
            break
        if not feedback.corrected_response:
            continue
        if has_prompt_injection(feedback.corrected_response):
            skipped += 1
            continue
        source_refs = [
            {
                "documentoId": str(item.document_id),
                "versaoId": str(item.version_id),
                "escopo": item.source_scope,
                "julgamento": item.judgment.value,
            }
            for item in judgments.get(feedback.id, [])
            if item.judgment
            in {
                RagFeedbackSourceJudgmentValue.RELEVANTE,
                RagFeedbackSourceJudgmentValue.AUSENTE,
            }
        ]
        if not source_refs:
            continue
        exemplars.append(
            {
                "consultaId": str(query.id),
                "consultaHash": query.query_hash,
                "respostaExemplar": feedback.corrected_response,
                "fontes": source_refs,
                "usoPermitido": "AVALIACAO_E_FORMA",
                "evidenciaFactual": False,
            }
        )
        contributions[feedback.id].append("ANSWER_EXEMPLARS")
    return (
        _compiled(
            {
                "schemaVersion": SCHEMA_VERSION,
                "exemplares": exemplars,
            },
            contributions,
        ),
        skipped,
    )


def _create_artifact(
    run,
    artifact_type,
    payload,
    feedback_ids,
    contributions,
):
    latest_version = db.session.scalar(
        select(func.max(RagLearningArtifact.version)).where(
            RagLearningArtifact.tenant_id == run.tenant_id,
            RagLearningArtifact.artifact_type == artifact_type,
        )
    )
    artifact = RagLearningArtifact(
        tenant_id=run.tenant_id,
        run_id=run.id,
        artifact_type=artifact_type,
        version=(latest_version or 0) + 1,
        payload=payload,
        payload_hash=_hash(payload),
        source_feedback_ids=[str(item) for item in feedback_ids],
        baseline=run.baseline,
        metrics_before=run.baseline.get("metrics", {}),
        metrics_after={},
        status=RagLearningArtifactStatus.CANDIDATO,
    )
    db.session.add(artifact)
    db.session.flush()
    for feedback_id in feedback_ids:
        db.session.add(
            RagLearningArtifactFeedback(
                tenant_id=run.tenant_id,
                artifact_id=artifact.id,
                feedback_id=feedback_id,
                contribution={
                    "artifactType": artifact_type.value,
                    "signals": sorted(set(contributions.get(feedback_id, []))),
                },
            )
        )
    _add_worker_audit(
        run,
        "rag_learning.artifact_candidate_created",
        "rag_learning_artifact",
        artifact.id,
        {
            "execucaoId": str(run.id),
            "tipo": artifact_type.value,
            "versao": artifact.version,
            "payloadHash": artifact.payload_hash,
            "feedbacksOrigem": len(feedback_ids),
        },
    )
    return artifact


def _add_worker_audit(run, action, entity_type, entity_id, after):
    db.session.add(
        AuditLog(
            tenant_id=run.tenant_id,
            user_id=run.initiated_by_id,
            action=action,
            entity_type=entity_type,
            entity_id=str(entity_id),
            after=after,
        )
    )


def _compiled(payload, contributions):
    feedback_ids = sorted(contributions, key=str)
    return {
        "payload": payload,
        "feedbackIds": feedback_ids,
        "contributions": contributions,
    }


def _judgments_by_feedback(tenant_id, feedback_ids):
    result = defaultdict(list)
    if not feedback_ids:
        return result
    for item in db.session.scalars(
        select(RagFeedbackSourceJudgment).where(
            RagFeedbackSourceJudgment.tenant_id == tenant_id,
            RagFeedbackSourceJudgment.feedback_id.in_(feedback_ids),
        )
    ):
        result[item.feedback_id].append(item)
    return result


def _baseline_snapshot(tenant_id):
    latest = db.session.scalar(
        select(RagEvaluationRun)
        .where(RagEvaluationRun.tenant_id == tenant_id)
        .order_by(RagEvaluationRun.created_at.desc())
        .limit(1)
    )
    if latest is None:
        return {"evaluationRunId": None, "metrics": {}}
    return {
        "evaluationRunId": str(latest.id),
        "metrics": {
            "precisionAtK": latest.precision_at_k,
            "recallAtK": latest.recall_at_k,
            "groundedness": latest.groundedness,
            "citationPrecision": latest.citation_precision,
            "disconnectedSourceRate": latest.disconnected_source_rate,
            "refusalAccuracy": latest.refusal_accuracy,
            "routingAccuracy": latest.routing_accuracy,
            "filterAccuracy": latest.filter_accuracy,
            "hardNegativeRate": latest.hard_negative_rate,
        },
    }


def _artifact_types(value):
    if value is None:
        return list(RagLearningArtifactType)
    if not isinstance(value, list) or not value:
        raise LearningValidationError("tiposArtefato deve ser uma lista não vazia.")
    try:
        resolved = [RagLearningArtifactType(str(item).upper()) for item in value]
    except ValueError as error:
        raise LearningValidationError("Tipo de artefato inválido.") from error
    if len(resolved) != len(set(resolved)):
        raise LearningValidationError("tiposArtefato não pode conter duplicidades.")
    return resolved


def _configured_types(run):
    return [
        RagLearningArtifactType(value)
        for value in run.configuration.get("artifactTypes", [])
    ]


def _parse_datetime(value, field):
    if not isinstance(value, str):
        raise LearningValidationError(f"{field} deve usar data e hora ISO 8601.")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise LearningValidationError(
            f"{field} deve usar data e hora ISO 8601."
        ) from error
    if parsed.tzinfo is None:
        raise LearningValidationError(f"{field} deve informar o fuso horário.")
    return parsed.astimezone(UTC)


def _decay_weight(created_at, window_end, half_life_days):
    created = (
        created_at.replace(tzinfo=UTC) if created_at.tzinfo is None else created_at
    )
    end = window_end.replace(tzinfo=UTC) if window_end.tzinfo is None else window_end
    age_days = max(0.0, (end - created).total_seconds() / 86400)
    return math.pow(0.5, age_days / half_life_days)


def _hash(value):
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _artifact_eligibility_errors(item):
    errors = []
    links = list(
        db.session.scalars(
            select(RagLearningArtifactFeedback).where(
                RagLearningArtifactFeedback.tenant_id == item.tenant_id,
                RagLearningArtifactFeedback.artifact_id == item.id,
            )
        )
    )
    feedback_ids = [link.feedback_id for link in links]
    feedbacks = (
        list(
            db.session.scalars(
                select(RagQueryFeedback).where(
                    RagQueryFeedback.tenant_id == item.tenant_id,
                    RagQueryFeedback.id.in_(feedback_ids),
                )
            )
        )
        if feedback_ids
        else []
    )
    if not feedback_ids or len(feedbacks) != len(feedback_ids):
        errors.append("PROVENIENCIA_INCOMPLETA")
    if any(value.status != RagFeedbackStatus.APROVADO for value in feedbacks):
        errors.append("FEEDBACK_NAO_APROVADO_OU_INELEGIVEL")
    run = db.session.scalar(
        select(RagLearningRun).where(
            RagLearningRun.tenant_id == item.tenant_id,
            RagLearningRun.id == item.run_id,
        )
    )
    if run is None or (
        len(feedbacks) < int((run.configuration or {}).get("minimumSignals", 1))
        and not (run.configuration or {}).get("smallSampleExplicitlyApproved")
    ):
        errors.append("QUANTIDADE_MINIMA_NAO_ATINGIDA")
    if item.payload_hash != _hash(item.payload):
        errors.append("CHECKSUM_DO_ARTEFATO_INVALIDO")
    references = _artifact_source_references(item)
    private_refs = {
        (reference["documentoId"], reference["versaoId"])
        for reference in references
        if reference["escopo"] == "PRIVADO"
    }
    if private_refs:
        available_private = {
            (str(version.document_id), str(version.id))
            for version in db.session.scalars(
                select(RagDocumentVersion)
                .join(RagDocument)
                .where(
                    RagDocumentVersion.tenant_id == item.tenant_id,
                    RagDocumentVersion.id.in_(
                        [uuid.UUID(version_id) for _, version_id in private_refs]
                    ),
                    RagDocument.active.is_(True),
                )
            )
        }
        if not private_refs.issubset(available_private):
            errors.append("FONTE_PRIVADA_INDISPONIVEL")
    global_refs = {
        (reference["documentoId"], reference["versaoId"])
        for reference in references
        if reference["escopo"] == "GLOBAL"
    }
    if global_refs:
        from app.rag.distribution import global_versions_for_tenant

        available_global = {
            (str(version.document_id), str(version.id))
            for version in global_versions_for_tenant(item.tenant_id)
        }
        if not global_refs.issubset(available_global):
            errors.append("FONTE_GLOBAL_INDISPONIVEL")
    if item.artifact_type == RagLearningArtifactType.ANSWER_EXEMPLARS:
        from app.rag.content_security import has_prompt_injection

        if any(
            has_prompt_injection(str(exemplar.get("respostaExemplar") or ""))
            for exemplar in item.payload.get("exemplares", [])
        ):
            errors.append("PROMPT_INJECTION_DETECTADO")
        if any(
            exemplar.get("evidenciaFactual") is not False
            for exemplar in item.payload.get("exemplares", [])
        ):
            errors.append("EXEMPLAR_MARCADO_COMO_EVIDENCIA_FACTUAL")
    return sorted(set(errors))


def _artifact_source_references(item):
    references = []
    if item.artifact_type == RagLearningArtifactType.RERANK_PROFILE:
        raw = item.payload.get("entradas", [])
    elif item.artifact_type == RagLearningArtifactType.ANSWER_EXEMPLARS:
        raw = [
            source
            for exemplar in item.payload.get("exemplares", [])
            for source in exemplar.get("fontes", [])
        ]
    elif item.artifact_type == RagLearningArtifactType.EVALUATION_CASES:
        raw = [
            source
            for case in item.payload.get("casos", [])
            for source in (
                list(case.get("fontesEsperadas") or [])
                + list(case.get("hardNegatives") or [])
            )
        ]
    else:
        raw = []
    for value in raw:
        try:
            references.append(
                {
                    "documentoId": str(uuid.UUID(str(value.get("documentoId")))),
                    "versaoId": str(uuid.UUID(str(value.get("versaoId")))),
                    "escopo": str(value.get("escopo") or "PRIVADO").upper(),
                }
            )
        except (AttributeError, TypeError, ValueError):
            continue
    return references


def _reject_evaluation(item, user_id, errors, k):
    item.status = RagLearningArtifactStatus.REJEITADO
    item.evaluation_details = {
        "k": k,
        "decision": "REJEITADO",
        "reasons": errors,
        "evaluatedAt": utc_now().isoformat(),
    }
    add_audit(
        item.tenant_id,
        user_id,
        "rag_learning.artifact_evaluated",
        "rag_learning_artifact",
        item.id,
        after={
            "tipo": item.artifact_type.value,
            "versao": item.version,
            "decisao": "REJEITADO",
            "motivos": errors,
        },
    )
    return False, errors


def _quality_gate(artifact_type, before, after):
    higher_is_better = {
        "precisionAtK",
        "recallAtK",
        "groundedness",
        "citationPrecision",
        "refusalAccuracy",
        "routingAccuracy",
        "filterAccuracy",
    }
    lower_is_better = {"disconnectedSourceRate", "hardNegativeRate"}
    target_metrics = {
        RagLearningArtifactType.RERANK_PROFILE: {
            "precisionAtK",
            "recallAtK",
            "disconnectedSourceRate",
            "hardNegativeRate",
        },
        RagLearningArtifactType.ROUTING_EXAMPLES: {
            "routingAccuracy",
            "filterAccuracy",
        },
        RagLearningArtifactType.EVALUATION_CASES: set(),
        RagLearningArtifactType.ANSWER_EXEMPLARS: set(),
    }[artifact_type]
    tolerance = max(
        0.0,
        min(1.0, float(current_app.config["RAG_LEARNING_MAX_REGRESSION"])),
    )
    comparisons = {}
    regressions = []
    improved = False
    for metric in sorted(higher_is_better | lower_is_better):
        old = float(before.get(metric) or 0)
        new = float(after.get(metric) or 0)
        delta = new - old
        regression = -delta if metric in higher_is_better else delta
        improvement = delta if metric in higher_is_better else -delta
        comparisons[metric] = {
            "baseline": old,
            "candidate": new,
            "delta": round(delta, 6),
            "regression": round(max(0.0, regression), 6),
            "tolerance": tolerance,
        }
        if regression > tolerance:
            regressions.append(f"REGRESSAO_{metric.upper()}")
        if metric in target_metrics and improvement > 0.000001:
            improved = True
    return {
        "comparisons": comparisons,
        "regressions": regressions,
        "improved": improved,
        "targetMetrics": sorted(target_metrics),
    }


def _optional_reason(value):
    if value is None:
        return None
    if not isinstance(value, str):
        raise LearningValidationError("A justificativa deve ser textual.")
    normalized = " ".join(value.split())
    if len(normalized) > 2000:
        raise LearningValidationError("A justificativa excede 2000 caracteres.")
    return normalized or None


def _restore_previous_eligible(item, actor_id):
    candidates = db.session.scalars(
        select(RagLearningArtifact)
        .where(
            RagLearningArtifact.tenant_id == item.tenant_id,
            RagLearningArtifact.artifact_type == item.artifact_type,
            RagLearningArtifact.status == RagLearningArtifactStatus.SUBSTITUIDO,
            RagLearningArtifact.replaced_by_id == item.id,
        )
        .order_by(RagLearningArtifact.version.desc())
    )
    for previous in candidates:
        if _artifact_eligibility_errors(previous):
            continue
        previous.status = RagLearningArtifactStatus.ATIVO
        previous.activated_by_id = actor_id
        previous.activated_at = utc_now()
        previous.activation_mode = previous.activation_mode or "TOTAL"
        previous.rollout_percentage = previous.rollout_percentage or 100
        return previous
    return None


def _schedule_recompilation(item, actor_id, feedback_id, reason):
    source_run = db.session.scalar(
        select(RagLearningRun).where(
            RagLearningRun.tenant_id == item.tenant_id,
            RagLearningRun.id == item.run_id,
        )
    )
    if source_run is None:
        return None
    configuration = dict(source_run.configuration or {})
    configuration["recompilationTrigger"] = {
        "artifactId": str(item.id),
        "feedbackId": str(feedback_id),
        "reason": reason[:120],
    }
    configuration_hash = _hash(configuration)
    existing = db.session.scalar(
        select(RagLearningRun).where(
            RagLearningRun.tenant_id == item.tenant_id,
            RagLearningRun.window_start == source_run.window_start,
            RagLearningRun.window_end == source_run.window_end,
            RagLearningRun.configuration_hash == configuration_hash,
        )
    )
    if existing is not None:
        return existing
    run = RagLearningRun(
        tenant_id=item.tenant_id,
        window_start=source_run.window_start,
        window_end=source_run.window_end,
        configuration=configuration,
        configuration_hash=configuration_hash,
        baseline=_baseline_snapshot(item.tenant_id),
        status=RagLearningRunStatus.PENDENTE,
        initiated_by_id=actor_id,
    )
    db.session.add(run)
    db.session.flush()
    db.session.add(
        OutboxEvent(
            tenant_id=item.tenant_id,
            event_type=LEARNING_COMPILATION_EVENT,
            aggregate_type="ExecucaoAprendizadoRag",
            aggregate_id=str(run.id),
            payload={"runId": str(run.id)},
        )
    )
    return run
