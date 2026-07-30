import uuid

from sqlalchemy import select

from app.extensions import db
from app.models import RagEvaluationQuestion, RagEvaluationRun
from app.rag.retrieval import answer_query
from app.rag.router import route_query


def execute_tenant_evaluation(
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    role: str | None,
    *,
    k: int,
) -> RagEvaluationRun:
    evaluation = evaluate_tenant_dataset(
        tenant_id,
        role,
        k=k,
    )
    metrics = evaluation["metrics"]
    run = RagEvaluationRun(
        tenant_id=tenant_id,
        created_by_id=user_id,
        k=evaluation["k"],
        question_count=evaluation["questionCount"],
        precision_at_k=metrics["precisionAtK"],
        recall_at_k=metrics["recallAtK"],
        groundedness=metrics["groundedness"],
        citation_precision=metrics["citationPrecision"],
        disconnected_source_rate=metrics["disconnectedSourceRate"],
        refusal_accuracy=metrics["refusalAccuracy"],
        routing_accuracy=metrics["routingAccuracy"],
        filter_accuracy=metrics["filterAccuracy"],
        hard_negative_rate=metrics["hardNegativeRate"],
        results=evaluation["results"],
    )
    db.session.add(run)
    db.session.flush()
    return run


def evaluate_tenant_dataset(
    tenant_id: uuid.UUID,
    role: str | None,
    *,
    k: int,
    learning_artifacts: dict | None = None,
) -> dict:
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
    routing_scores = []
    filter_scores = []
    hard_negative_rates = []

    for question in questions:
        if question.expected_method or question.expected_filters:
            if learning_artifacts is None:
                answer = route_query(
                    tenant_id,
                    role,
                    question.question,
                    limit=safe_k,
                )
            else:
                answer = route_query(
                    tenant_id,
                    role,
                    question.question,
                    limit=safe_k,
                    learning_artifacts=learning_artifacts,
                )
        else:
            if learning_artifacts is None:
                answer = answer_query(
                    tenant_id,
                    role,
                    question.question,
                    safe_k,
                )
            else:
                answer = route_query(
                    tenant_id,
                    role,
                    question.question,
                    limit=safe_k,
                    learning_artifacts=learning_artifacts,
                )
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
        generation_enabled = bool(
            (answer.get("geracao") or {}).get("habilitada")
        )
        cited = list(
            dict.fromkeys(
                str(citation.get("documentoId"))
                for citation in (answer.get("citacoes") or [])
                if citation.get("documentoId")
            )
        )
        cited_set = set(cited) if generation_enabled else retrieved_set
        cited_relevant = cited_set & expected
        hard_negative_ids = {
            str(value.get("documentoId"))
            for value in question.hard_negative_source_refs
            if value.get("documentoId")
        }
        hard_negative_hits = retrieved_set & hard_negative_ids
        precision = len(relevant) / len(retrieved_set) if retrieved_set else 0.0
        recall = len(relevant) / len(expected) if expected else None
        if expected:
            evidence_precisions.append(precision)
            evidence_recalls.append(recall)
            citation_precisions.append(
                len(cited_relevant) / len(cited_set) if cited_set else 0.0
            )
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
                and not hard_negative_hits
                and not answer["recusaConclusiva"]
            )
        )
        refusal_correct = bool(answer["recusaConclusiva"]) == question.expected_refusal
        refusal_scores.append(float(refusal_correct))
        hard_negative_rate = (
            len(hard_negative_hits) / len(hard_negative_ids)
            if hard_negative_ids
            else None
        )
        if hard_negative_rate is not None:
            hard_negative_rates.append(hard_negative_rate)
        actual_method = answer.get("metodo")
        route_correct = (
            actual_method == question.expected_method
            if question.expected_method
            else None
        )
        if route_correct is not None:
            routing_scores.append(float(route_correct))
        actual_filters = answer.get("filtrosAplicados") or {}
        filters_correct = (
            all(
                actual_filters.get(key) == value
                for key, value in question.expected_filters.items()
            )
            if question.expected_filters
            else None
        )
        if filters_correct is not None:
            filter_scores.append(float(filters_correct))
        results.append(
            {
                "perguntaId": str(question.id),
                "esperavaRecusa": question.expected_refusal,
                "recusou": bool(answer["recusaConclusiva"]),
                "documentosEsperados": sorted(expected),
                "documentosRecuperados": retrieved,
                "documentosRelevantes": sorted(relevant),
                "documentosCitados": cited,
                "documentosCitadosRelevantes": sorted(cited_relevant),
                "precisionAtK": round(precision, 6),
                "precisaoCitacoes": round(
                    len(cited_relevant) / len(cited_set) if cited_set else 0.0,
                    6,
                ),
                "recallAtK": round(recall, 6) if recall is not None else None,
                "fundamentada": bool(answer["fundamentada"]),
                "fontesDesconexas": len(retrieved_set - expected),
                "recusaCorreta": refusal_correct,
                "hardNegatives": sorted(hard_negative_ids),
                "hardNegativesRecuperados": sorted(hard_negative_hits),
                "taxaHardNegative": (
                    round(hard_negative_rate, 6)
                    if hard_negative_rate is not None
                    else None
                ),
                "metodoEsperado": question.expected_method,
                "metodoObtido": actual_method,
                "roteamentoCorreto": route_correct,
                "filtrosEsperados": question.expected_filters,
                "filtrosObtidos": actual_filters,
                "filtrosCorretos": filters_correct,
            }
        )

    return {
        "k": safe_k,
        "questionCount": len(questions),
        "metrics": {
            "precisionAtK": _average(evidence_precisions),
            "recallAtK": _average(evidence_recalls),
            "groundedness": _average(grounded_scores),
            "citationPrecision": _average(citation_precisions),
            "disconnectedSourceRate": _average(disconnected_rates),
            "refusalAccuracy": _average(refusal_scores),
            "routingAccuracy": _average(routing_scores),
            "filterAccuracy": _average(filter_scores),
            "hardNegativeRate": _average(hard_negative_rates),
        },
        "results": results,
    }


def evaluation_question_data(item: RagEvaluationQuestion) -> dict:
    return {
        "id": str(item.id),
        "pergunta": item.question,
        "documentosEsperados": item.expected_document_ids,
        "fontesEsperadas": item.expected_source_refs,
        "hardNegatives": item.hard_negative_source_refs,
        "esperaRecusa": item.expected_refusal,
        "metodoEsperado": item.expected_method,
        "filtrosEsperados": item.expected_filters,
        "observacoes": item.notes,
        "ativa": item.active,
        "origem": item.case_origin,
        "motivosFalha": item.failure_reasons,
        "severidade": item.severity,
        "tags": item.tags,
        "baseline": item.baseline_snapshot,
        "baselineCapturadoEm": (
            item.baseline_captured_at.isoformat()
            if item.baseline_captured_at
            else None
        ),
        "consultaOrigemId": (
            str(item.source_query_id) if item.source_query_id else None
        ),
        "feedbackOrigemId": (
            str(item.source_feedback_id) if item.source_feedback_id else None
        ),
        "curadaPorId": str(item.curated_by_id) if item.curated_by_id else None,
        "curadaEm": item.curated_at.isoformat() if item.curated_at else None,
        "motivoDesativacao": item.deactivation_reason,
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
        "acuraciaRoteamento": item.routing_accuracy,
        "acuraciaFiltros": item.filter_accuracy,
        "taxaHardNegatives": item.hard_negative_rate,
        "criadaEm": item.created_at.isoformat(),
    }
    if include_results:
        data["resultados"] = item.results
    return data


def _average(values: list[float]) -> float:
    return round(sum(values) / len(values), 6) if values else 0.0
