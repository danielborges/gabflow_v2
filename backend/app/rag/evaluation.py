import uuid

from sqlalchemy import select

from app.extensions import db
from app.models import RagEvaluationQuestion, RagEvaluationRun
from app.rag.retrieval import answer_query


def execute_tenant_evaluation(
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    role: str | None,
    *,
    k: int,
) -> RagEvaluationRun:
    questions = list(
        db.session.scalars(
            select(RagEvaluationQuestion)
            .where(
                RagEvaluationQuestion.tenant_id == tenant_id,
                RagEvaluationQuestion.active.is_(True),
            )
            .order_by(RagEvaluationQuestion.created_at)
        )
    )
    if not questions:
        raise ValueError("Cadastre ao menos uma pergunta ativa para executar a avaliação.")
    safe_k = max(1, min(int(k), 10))
    results = []
    evidence_precisions = []
    evidence_recalls = []
    citation_precisions = []
    disconnected_rates = []
    grounded_scores = []
    refusal_scores = []

    for question in questions:
        answer = answer_query(tenant_id, role, question.question, safe_k)
        retrieved = list(
            dict.fromkeys(
                str(source.get("documentoId"))
                for source in answer["fontes"]
                if source.get("documentoId")
            )
        )
        expected = {str(value) for value in question.expected_document_ids}
        retrieved_set = set(retrieved)
        relevant = retrieved_set & expected
        precision = len(relevant) / len(retrieved_set) if retrieved_set else 0.0
        recall = len(relevant) / len(expected) if expected else None
        if expected:
            evidence_precisions.append(precision)
            evidence_recalls.append(recall)
            citation_precisions.append(precision)
        disconnected = (
            len(retrieved_set - expected) / len(retrieved_set)
            if retrieved_set
            else 0.0
        )
        disconnected_rates.append(disconnected)
        grounded_scores.append(
            float(
                bool(answer["fundamentada"])
                and (not expected or bool(relevant))
                and not answer["recusaConclusiva"]
            )
        )
        refusal_correct = bool(answer["recusaConclusiva"]) == question.expected_refusal
        refusal_scores.append(float(refusal_correct))
        results.append(
            {
                "perguntaId": str(question.id),
                "esperavaRecusa": question.expected_refusal,
                "recusou": bool(answer["recusaConclusiva"]),
                "documentosEsperados": sorted(expected),
                "documentosRecuperados": retrieved,
                "documentosRelevantes": sorted(relevant),
                "precisionAtK": round(precision, 6),
                "recallAtK": round(recall, 6) if recall is not None else None,
                "fundamentada": bool(answer["fundamentada"]),
                "fontesDesconexas": len(retrieved_set - expected),
                "recusaCorreta": refusal_correct,
            }
        )

    run = RagEvaluationRun(
        tenant_id=tenant_id,
        created_by_id=user_id,
        k=safe_k,
        question_count=len(questions),
        precision_at_k=_average(evidence_precisions),
        recall_at_k=_average(evidence_recalls),
        groundedness=_average(grounded_scores),
        citation_precision=_average(citation_precisions),
        disconnected_source_rate=_average(disconnected_rates),
        refusal_accuracy=_average(refusal_scores),
        results=results,
    )
    db.session.add(run)
    db.session.flush()
    return run


def evaluation_question_data(item: RagEvaluationQuestion) -> dict:
    return {
        "id": str(item.id),
        "pergunta": item.question,
        "documentosEsperados": item.expected_document_ids,
        "esperaRecusa": item.expected_refusal,
        "observacoes": item.notes,
        "ativa": item.active,
        "criadaEm": item.created_at.isoformat(),
        "atualizadaEm": item.updated_at.isoformat(),
    }


def evaluation_run_data(item: RagEvaluationRun, *, include_results: bool = True) -> dict:
    data = {
        "id": str(item.id),
        "k": item.k,
        "perguntas": item.question_count,
        "precisionAtK": item.precision_at_k,
        "recallAtK": item.recall_at_k,
        "groundedness": item.groundedness,
        "precisaoCitacoes": item.citation_precision,
        "taxaFontesDesconexas": item.disconnected_source_rate,
        "acuraciaRecusa": item.refusal_accuracy,
        "criadaEm": item.created_at.isoformat(),
    }
    if include_results:
        data["resultados"] = item.results
    return data


def _average(values: list[float]) -> float:
    return round(sum(values) / len(values), 6) if values else 0.0
