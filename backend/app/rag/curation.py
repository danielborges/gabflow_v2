import uuid

from sqlalchemy import select

from app.audit import add_audit
from app.extensions import db
from app.models import (
    RagAssistantQuery,
    RagDocument,
    RagDocumentVersion,
    RagEvaluationQuestion,
    RagFeedbackReason,
    RagFeedbackSourceJudgment,
    RagFeedbackSourceJudgmentValue,
    RagFeedbackStatus,
    RagQueryFeedback,
    utc_now,
)
from app.rag.distribution import global_versions_for_tenant


class CurationValidationError(ValueError):
    pass


class CurationConflictError(ValueError):
    pass


class CurationNotFoundError(ValueError):
    pass


def promote_feedback_to_evaluation(
    tenant_id: uuid.UUID,
    curator_id: uuid.UUID,
    feedback_id: uuid.UUID,
    *,
    notes: object = None,
) -> tuple[RagEvaluationQuestion, bool]:
    feedback = db.session.execute(
        select(RagQueryFeedback)
        .where(
            RagQueryFeedback.tenant_id == tenant_id,
            RagQueryFeedback.id == feedback_id,
        )
        .with_for_update()
    ).scalar_one_or_none()
    if feedback is None:
        raise CurationNotFoundError("Feedback não encontrado.")
    if feedback.status != RagFeedbackStatus.APROVADO:
        raise CurationConflictError(
            "Somente feedback aprovado e vigente pode ser promovido."
        )

    existing = db.session.execute(
        select(RagEvaluationQuestion).where(
            RagEvaluationQuestion.tenant_id == tenant_id,
            RagEvaluationQuestion.source_feedback_id == feedback.id,
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing, False

    latest_revision = db.session.scalar(
        select(db.func.max(RagQueryFeedback.revision)).where(
            RagQueryFeedback.tenant_id == tenant_id,
            RagQueryFeedback.query_id == feedback.query_id,
        )
    )
    if latest_revision != feedback.revision:
        raise CurationConflictError("Feedback superado não pode ser promovido.")

    query = db.session.execute(
        select(RagAssistantQuery).where(
            RagAssistantQuery.tenant_id == tenant_id,
            RagAssistantQuery.id == feedback.query_id,
        )
    ).scalar_one()
    judgments = list(
        db.session.scalars(
            select(RagFeedbackSourceJudgment)
            .where(
                RagFeedbackSourceJudgment.tenant_id == tenant_id,
                RagFeedbackSourceJudgment.feedback_id == feedback.id,
            )
            .order_by(RagFeedbackSourceJudgment.original_position)
        )
    )
    expected_refs = [
        _judgment_reference(item)
        for item in judgments
        if item.judgment
        in {
            RagFeedbackSourceJudgmentValue.RELEVANTE,
            RagFeedbackSourceJudgmentValue.AUSENTE,
        }
    ]
    hard_negatives = [
        _judgment_reference(item)
        for item in judgments
        if item.judgment == RagFeedbackSourceJudgmentValue.IRRELEVANTE
    ]
    reasons = {RagFeedbackReason(value) for value in feedback.reasons}
    if {
        RagFeedbackReason.DEVERIA_RECUSAR,
        RagFeedbackReason.RECUSA_INDEVIDA,
    }.issubset(reasons):
        raise CurationValidationError(
            "O feedback não pode exigir e rejeitar a recusa simultaneamente."
        )
    has_refusal_diagnosis = bool(
        reasons
        & {
            RagFeedbackReason.DEVERIA_RECUSAR,
            RagFeedbackReason.RECUSA_INDEVIDA,
        }
    )
    expected_refusal = RagFeedbackReason.DEVERIA_RECUSAR in reasons
    if expected_refusal and expected_refs:
        raise CurationValidationError(
            "Caso com expectativa de recusa não pode declarar fonte esperada."
        )

    expected_document_ids = list(
        dict.fromkeys(item["documentoId"] for item in expected_refs)
    )
    if not (
        expected_document_ids
        or has_refusal_diagnosis
        or feedback.expected_method
        or feedback.expected_filters
        or hard_negatives
    ):
        raise CurationValidationError(
            "Feedback sem diagnóstico não pode ser promovido ao dataset."
        )

    item = RagEvaluationQuestion(
        tenant_id=tenant_id,
        question=query.query_text,
        expected_document_ids=expected_document_ids,
        expected_source_refs=expected_refs,
        hard_negative_source_refs=hard_negatives,
        expected_refusal=expected_refusal,
        expected_method=feedback.expected_method,
        expected_filters=feedback.expected_filters,
        notes=_optional_text(notes, 2000, "Observações"),
        case_origin="FEEDBACK",
        active=True,
        source_feedback_id=feedback.id,
        curated_by_id=curator_id,
        curated_at=utc_now(),
        created_by_id=curator_id,
    )
    db.session.add(item)
    db.session.flush()
    add_audit(
        tenant_id,
        curator_id,
        "rag_evaluation.feedback_promoted",
        "rag_evaluation_question",
        item.id,
        after={
            "feedbackId": str(feedback.id),
            "feedbackRevisao": feedback.revision,
            "documentosEsperados": len(expected_document_ids),
            "hardNegatives": len(hard_negatives),
            "esperaRecusa": expected_refusal,
            "metodoEsperado": feedback.expected_method,
            "filtrosEsperados": sorted(feedback.expected_filters),
        },
    )
    return item, True


def deactivate_questions_for_feedback(
    feedback: RagQueryFeedback,
    actor_id: uuid.UUID,
    reason: str,
) -> int:
    items = list(
        db.session.scalars(
            select(RagEvaluationQuestion).where(
                RagEvaluationQuestion.tenant_id == feedback.tenant_id,
                RagEvaluationQuestion.source_feedback_id == feedback.id,
                RagEvaluationQuestion.active.is_(True),
            )
        )
    )
    for item in items:
        _deactivate(item, actor_id, reason)
    return len(items)


def reconcile_curated_questions(
    tenant_id: uuid.UUID,
    actor_id: uuid.UUID,
) -> int:
    items = list(
        db.session.scalars(
            select(RagEvaluationQuestion).where(
                RagEvaluationQuestion.tenant_id == tenant_id,
                RagEvaluationQuestion.source_feedback_id.is_not(None),
                RagEvaluationQuestion.active.is_(True),
            )
        )
    )
    if not items:
        return 0
    feedback_by_id = {
        item.id: item
        for item in db.session.scalars(
            select(RagQueryFeedback).where(
                RagQueryFeedback.tenant_id == tenant_id,
                RagQueryFeedback.id.in_(
                    [item.source_feedback_id for item in items]
                ),
            )
        )
    }
    references = [
        reference
        for item in items
        for reference in item.expected_source_refs + item.hard_negative_source_refs
    ]
    private_keys = set()
    for reference in references:
        if reference.get("escopo") == "GLOBAL":
            continue
        try:
            private_keys.add(
                (
                    uuid.UUID(str(reference.get("documentoId"))),
                    uuid.UUID(str(reference.get("versaoId"))),
                )
            )
        except (TypeError, ValueError):
            continue
    private_versions = (
        {
            (str(item.document_id), str(item.id))
            for item in db.session.scalars(
                select(RagDocumentVersion)
                .join(RagDocument)
                .where(
                    RagDocumentVersion.tenant_id == tenant_id,
                    RagDocumentVersion.id.in_(
                        [version_id for _, version_id in private_keys]
                    ),
                    RagDocument.active.is_(True),
                )
            )
        }
        if private_keys
        else set()
    )
    global_versions = (
        {
            (str(item.document_id), str(item.id))
            for item in global_versions_for_tenant(tenant_id)
        }
        if any(reference.get("escopo") == "GLOBAL" for reference in references)
        else set()
    )
    deactivated = 0
    for item in items:
        feedback = feedback_by_id.get(item.source_feedback_id)
        if feedback is None or feedback.status != RagFeedbackStatus.APROVADO:
            status = feedback.status.value if feedback else "AUSENTE"
            _deactivate(item, actor_id, f"FEEDBACK_{status}")
            deactivated += 1
            continue
        references = item.expected_source_refs + item.hard_negative_source_refs
        if any(
            not _reference_available(
                reference,
                private_versions,
                global_versions,
            )
            for reference in references
        ):
            _deactivate(item, actor_id, "FONTE_INDISPONIVEL")
            deactivated += 1
    return deactivated


def _reference_available(
    reference: dict,
    private_versions: set[tuple[str, str]],
    global_versions: set[tuple[str, str]],
) -> bool:
    key = (str(reference.get("documentoId")), str(reference.get("versaoId")))
    if reference.get("escopo") == "GLOBAL":
        return key in global_versions
    return key in private_versions


def _deactivate(
    item: RagEvaluationQuestion,
    actor_id: uuid.UUID,
    reason: str,
) -> None:
    item.active = False
    item.deactivation_reason = reason[:120]
    add_audit(
        item.tenant_id,
        actor_id,
        "rag_evaluation.curated_question_deactivated",
        "rag_evaluation_question",
        item.id,
        before={"ativa": True},
        after={
            "ativa": False,
            "motivo": item.deactivation_reason,
            "feedbackId": (
                str(item.source_feedback_id) if item.source_feedback_id else None
            ),
        },
    )


def _judgment_reference(item: RagFeedbackSourceJudgment) -> dict:
    return {
        "documentoId": str(item.document_id),
        "versaoId": str(item.version_id),
        "chunkId": str(item.chunk_id) if item.chunk_id else None,
        "escopo": item.source_scope,
        "julgamento": item.judgment.value,
        "motivo": item.reason.value,
    }


def _optional_text(value: object, max_length: int, label: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise CurationValidationError(f"{label} deve ser texto.")
    text = value.strip()
    if not text:
        return None
    if len(text) > max_length:
        raise CurationValidationError(
            f"{label} deve ter no máximo {max_length} caracteres."
        )
    return text
