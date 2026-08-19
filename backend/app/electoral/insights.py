import hashlib
import json
import re
import uuid
from datetime import UTC, datetime

from flask import current_app
from sqlalchemy import select

from app.audit import add_audit
from app.electoral.ai_generation import (
    ElectoralEvidence,
    generate_electoral_content,
)
from app.electoral.analytics import candidate_results, compare_candidates
from app.electoral.mandate_intelligence import latest_snapshot
from app.electoral.web_research import research_electoral_context
from app.extensions import db
from app.models import ElectoralInsight, ElectoralInsightFeedback, OutboxEvent
from app.rag.retrieval import answer_query

INSIGHT_EVENT = "electoral.insight.requested"
INSIGHT_COMPLETED_EVENT = "electoral.insight.completed"
MODEL_PROVIDER = "GABFLOW_RULES"
MODEL_NAME = "electoral-explainable-v1"
PROMPT_VERSION = "facts-calculations-hypotheses-v1"
QUESTION_MODEL_NAME = "electoral-grounded-question-v1"
QUESTION_PROMPT_VERSION = "electoral-grounded-question-v1"
OUTPUT_VALIDATOR_VERSION = "electoral-claim-validator-v1"


class NonRetryableInsightError(RuntimeError):
    pass


def execute_insight(insight: ElectoralInsight) -> None:
    if insight.status == "REFUSED":
        raise NonRetryableInsightError("Insight recusado pela politica eleitoral.")
    insight.status = "PROCESSING"
    insight.started_at = datetime.now(UTC)
    insight.error = None
    db.session.flush()

    payload = insight.request_payload
    try:
        election_id = uuid.UUID(payload["election_id"])
        candidate_ids = [uuid.UUID(value) for value in payload["candidate_ids"]]
    except (KeyError, TypeError, ValueError) as error:
        raise NonRetryableInsightError("Parametros auditaveis do insight sao invalidos.") from error
    level = payload["level"]
    municipality_code = payload.get("municipality_code")

    effective_type = (
        "candidate"
        if insight.analysis_type == "question" and len(candidate_ids) == 1
        else "comparison"
        if insight.analysis_type == "question"
        else insight.analysis_type
    )
    if effective_type == "candidate":
        analysis = candidate_results(
            candidate_ids[0],
            election_id,
            level,
            municipality_code=municipality_code,
            page=1,
            per_page=100,
            sort="votes",
            order="desc",
        )
        if analysis is None:
            raise NonRetryableInsightError("Candidatura publicada nao encontrada.")
        output = _candidate_output(analysis, payload)
    else:
        analysis, error = compare_candidates(
            candidate_ids,
            election_id,
            level,
            municipality_code=municipality_code,
        )
        if error or analysis is None:
            raise NonRetryableInsightError(error or "Comparacao nao disponivel.")
        output = _comparison_output(analysis, payload)

    if insight.analysis_type == "question":
        output = _question_output(insight, analysis, output)

    output = _ai_output(insight, output)

    validation_evidence = output.pop("_validation_evidence", {})
    validation = validate_insight_output(output, analysis, validation_evidence)
    insight.output_validation = validation
    if not validation["valid"]:
        insight.facts = []
        insight.calculations = []
        insight.hypotheses = []
        insight.limitations = [
            "A resposta foi recusada porque a validacao automatica nao confirmou "
            "citacoes e valores quantitativos."
        ]
        insight.citations = output["citations"]
        insight.status = "REFUSED"
        insight.review_status = "NOT_REQUIRED"
        insight.refusal_reason = "OUTPUT_VALIDATION_FAILED"
        insight.completed_at = datetime.now(UTC)
        add_audit(
            insight.tenant_id,
            insight.requested_by_id,
            "electoral.insight.output_refused",
            "electoral_insight",
            insight.id,
            after={
                "validatorVersion": OUTPUT_VALIDATOR_VERSION,
                "signals": validation["signals"],
                "questionHash": payload.get("question_hash"),
            },
        )
        return

    insight.input_snapshot = output["input_snapshot"]
    insight.facts = output["facts"]
    insight.calculations = output["calculations"]
    insight.hypotheses = output["hypotheses"]
    insight.limitations = output["limitations"]
    insight.citations = output["citations"]
    insight.status = "COMPLETED"
    insight.review_status = "PENDING"
    insight.completed_at = datetime.now(UTC)
    db.session.add(
        OutboxEvent(
            tenant_id=insight.tenant_id,
            event_type=INSIGHT_COMPLETED_EVENT,
            aggregate_type="electoral_insight",
            aggregate_id=str(insight.id),
            payload={
                "insightId": str(insight.id),
                "requestedById": str(insight.requested_by_id),
                "modelVersion": insight.model_name,
                "schemaVersion": 1,
                "idempotencyKey": f"{insight.id}:completed",
            },
        )
    )
    add_audit(
        insight.tenant_id,
        insight.requested_by_id,
        "electoral.insight.completed",
        "electoral_insight",
        insight.id,
        after={
            "analysisType": insight.analysis_type,
            "datasetVersion": output["input_snapshot"]["dataset_version"],
            "modelVersion": insight.model_name,
            "modelProvider": insight.model_provider,
            "draft": True,
            "validatorVersion": OUTPUT_VALIDATOR_VERSION,
            "questionHash": payload.get("question_hash"),
            "generationApplied": bool(
                output["input_snapshot"].get("generation", {}).get("applied")
            ),
            "fallbackUsed": bool(
                output["input_snapshot"].get("generation", {}).get("fallbackUsed")
            ),
        },
    )


def fail_insight(insight: ElectoralInsight, error_message: str) -> None:
    if insight.status != "REFUSED":
        insight.status = "FAILED"
        insight.error = error_message[:2000]
        insight.completed_at = datetime.now(UTC)


def insight_data(insight: ElectoralInsight) -> dict:
    return {
        "id": str(insight.id),
        "analysis_type": insight.analysis_type,
        "status": insight.status,
        "request": insight.request_payload,
        "input_snapshot": insight.input_snapshot,
        "facts": insight.facts,
        "calculations": insight.calculations,
        "hypotheses": insight.hypotheses,
        "limitations": insight.limitations,
        "citations": insight.citations,
        "model": {
            "provider": insight.model_provider,
            "name": insight.model_name,
            "prompt_version": insight.prompt_version,
        },
        "draft": insight.draft,
        "review_required": True,
        "safety": insight.safety_classification,
        "validation": insight.output_validation,
        "generation": insight.input_snapshot.get("generation", {}),
        "review": {
            "status": insight.review_status,
            "reviewed_by_id": str(insight.reviewed_by_id) if insight.reviewed_by_id else None,
            "reviewed_at": insight.reviewed_at.isoformat() if insight.reviewed_at else None,
            "notes": insight.review_notes,
            "revision": insight.review_revision,
        },
        "refusal_reason": insight.refusal_reason,
        "error": insight.error,
        "requested_by_id": str(insight.requested_by_id),
        "requested_at": insight.requested_at.isoformat(),
        "started_at": insight.started_at.isoformat() if insight.started_at else None,
        "completed_at": insight.completed_at.isoformat() if insight.completed_at else None,
    }


def record_feedback(
    insight: ElectoralInsight,
    user_id: uuid.UUID,
    rating: str,
    reason: str | None,
    comment: str | None,
) -> ElectoralInsightFeedback:
    feedback = ElectoralInsightFeedback(
        tenant_id=insight.tenant_id,
        insight_id=insight.id,
        user_id=user_id,
        rating=rating,
        reason=reason,
        comment=comment,
        model_version=insight.model_name,
    )
    db.session.add(feedback)
    if rating in {"DISCARDED", "CONTESTED"}:
        insight.status = "HIDDEN"
        insight.review_status = "PENDING"
    add_audit(
        insight.tenant_id,
        user_id,
        "electoral.insight.feedback_recorded",
        "electoral_insight",
        insight.id,
        after={"rating": rating, "reason": reason, "modelVersion": insight.model_name},
    )
    return feedback


def accessible_insight(
    insight_id: uuid.UUID, tenant_id: uuid.UUID, user_id: uuid.UUID, *, representative: bool
) -> ElectoralInsight | None:
    statement = select(ElectoralInsight).where(
        ElectoralInsight.id == insight_id,
        ElectoralInsight.tenant_id == tenant_id,
    )
    if not representative:
        statement = statement.where(ElectoralInsight.requested_by_id == user_id)
    return db.session.execute(statement).scalar_one_or_none()


def review_insight(
    insight: ElectoralInsight,
    reviewer_id: uuid.UUID,
    decision: str,
    notes: str,
) -> None:
    now = datetime.now(UTC)
    original_hash = hashlib.sha256(
        json.dumps(insight.facts, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()
    if decision in {"APPROVE", "RESTORE"}:
        insight.status = "COMPLETED"
        insight.review_status = "APPROVED"
    elif decision == "REJECT":
        insight.status = "HIDDEN"
        insight.review_status = "REJECTED"
    else:
        raise ValueError("Decisao de revisao invalida.")
    insight.reviewed_by_id = reviewer_id
    insight.reviewed_at = now
    insight.review_notes = notes
    insight.review_revision = {
        "decision": decision,
        "originalFactsHash": original_hash,
        "modelVersion": insight.model_name,
        "reviewedAt": now.isoformat(),
    }
    add_audit(
        insight.tenant_id,
        reviewer_id,
        "electoral.insight.reviewed",
        "electoral_insight",
        insight.id,
        after={
            "decision": decision,
            "reviewStatus": insight.review_status,
            "modelVersion": insight.model_name,
            "originalFactsHash": original_hash,
        },
    )


def validate_insight_output(
    output: dict,
    analysis: dict,
    evidence: dict[str, str] | None = None,
) -> dict:
    citation_ids = {str(item.get("id")) for item in output.get("citations", [])}
    evidence_map = {
        "dataset-1": json.dumps(analysis, ensure_ascii=False, sort_keys=True),
        **(evidence or {}),
    }
    signals = []
    checks = []
    for index, fact in enumerate(output.get("facts", []), start=1):
        text = str(fact.get("text") or "")
        cited = [str(value) for value in fact.get("citation_ids") or []]
        citations_valid = bool(cited) and set(cited).issubset(citation_ids)
        numbers = _numbers(text)
        evidence_text = " ".join(evidence_map.get(item, "") for item in cited)
        reproducible = all(number in _numbers(evidence_text) for number in numbers)
        causal = bool(re.search(r"\b(?:causou|provocou|devido a|por isso)\b", text.casefold()))
        if not citations_valid:
            signals.append("UNCITED_FACT")
        if numbers and not reproducible:
            signals.append("UNSUPPORTED_QUANTITATIVE_CLAIM")
        if causal:
            signals.append("UNSUPPORTED_CAUSAL_CLAIM")
        checks.append(
            {
                "claim": index,
                "citationsValid": citations_valid,
                "quantitative": bool(numbers),
                "numbersReproducible": reproducible,
                "causalLanguage": causal,
                "valid": citations_valid and reproducible and not causal,
            }
        )
    for calculation in output.get("calculations", []):
        cited = [str(value) for value in calculation.get("citation_ids") or []]
        if not cited or not set(cited).issubset(citation_ids):
            signals.append("UNCITED_CALCULATION")
        if not calculation.get("formula") or not isinstance(calculation.get("inputs"), dict):
            signals.append("UNREPRODUCIBLE_CALCULATION")
    signals = list(dict.fromkeys(signals))
    return {
        "valid": not signals and bool(output.get("facts")),
        "validatorVersion": OUTPUT_VALIDATOR_VERSION,
        "allFactsCited": not any(item == "UNCITED_FACT" for item in signals),
        "quantitativeClaimsReproducible": not any(
            item == "UNSUPPORTED_QUANTITATIVE_CLAIM" for item in signals
        ),
        "calculationsReproducible": not any(
            item in {"UNCITED_CALCULATION", "UNREPRODUCIBLE_CALCULATION"} for item in signals
        ),
        "causalClaimsBlocked": not any(item == "UNSUPPORTED_CAUSAL_CLAIM" for item in signals),
        "signals": signals,
        "checks": checks,
    }


def _question_output(insight: ElectoralInsight, analysis: dict, output: dict) -> dict:
    question = str(insight.request_payload["question"])
    rag_answer = answer_query(
        insight.tenant_id,
        insight.request_payload.get("requester_role"),
        question,
        limit=5,
    )
    document_citation_ids = []
    document_evidence = {}
    for source in rag_answer.get("fontes", []):
        citation_id = f"document-{source['chunkId']}"
        document_citation_ids.append(citation_id)
        document_evidence[citation_id] = str(source.get("trecho") or "")
        output["citations"].append(
            {
                "id": citation_id,
                "source_type": "AUTHORIZED_DOCUMENT",
                "title": source.get("titulo"),
                "source": source.get("urlFonte"),
                "document_id": source.get("documentoId"),
                "version_id": source.get("versaoId"),
                "source_hash": source.get("checksumDocumento"),
                "page_start": source.get("paginaInicio"),
                "scope": source.get("escopo"),
            }
        )
    generation = rag_answer.get("geracao") or {}
    if rag_answer.get("fundamentada") and generation.get("aplicada") and document_citation_ids:
        output["facts"].append(
            {
                "text": str(rag_answer["resposta"]),
                "citation_ids": document_citation_ids,
                "source_type": "AUTHORIZED_DOCUMENT",
            }
        )
    elif document_citation_ids:
        output["limitations"].append(
            "Foram recuperados documentos autorizados, mas nao houve geracao documental "
            "validada; consulte as citacoes antes de formular conclusoes adicionais."
        )
    else:
        output["limitations"].append(
            "Nenhuma evidencia documental autorizada relevante foi encontrada para complementar "
            "os resultados eleitorais oficiais."
        )
    web_sources, web_research = research_electoral_context(question, analysis)
    web_evidence = {}
    for index, source in enumerate(web_sources, start=1):
        citation_id = f"web-{index}"
        web_evidence[citation_id] = source.snippet
        output["citations"].append(
            {
                "id": citation_id,
                "source_type": "WEB_RESEARCH",
                "title": source.title,
                "source": source.url,
                "engine": source.engine,
                "published_at": source.published_at,
                "researched_at": web_research.get("researchedAt"),
            }
        )
    if web_research.get("enabled") and not web_sources:
        output["limitations"].append(
            "A pesquisa externa nao retornou fontes publicas utilizaveis nesta execucao."
        )
    output["input_snapshot"] = {
        **output["input_snapshot"],
        "question_hash": insight.request_payload.get("question_hash"),
        "document_retrieval": {
            "grounded": bool(rag_answer.get("fundamentada")),
            "refused": bool(rag_answer.get("recusaConclusiva")),
            "source_count": len(document_citation_ids),
            "embedding_model": rag_answer.get("modeloEmbedding"),
            "generation_model": generation.get("modelo"),
            "generation_prompt_version": generation.get("versaoPrompt"),
        },
        "web_research": web_research,
    }
    output["_validation_evidence"] = {
        **output.get("_validation_evidence", {}),
        **document_evidence,
        **web_evidence,
    }
    return output


def _ai_output(insight: ElectoralInsight, output: dict) -> dict:
    _attach_mandate_context(insight, output)
    evidence_map = output.get("_validation_evidence", {})
    citation_map = {str(item.get("id")): item for item in output.get("citations", [])}
    maximum = max(1000, int(current_app.config["ELECTORAL_AI_MAX_EVIDENCE_CHARS"]))
    available = max(500, maximum // max(1, len(evidence_map)))
    evidence = tuple(
        ElectoralEvidence(
            id=str(citation_id),
            title=_citation_title(citation_map.get(str(citation_id), {})),
            content=str(content)[:available],
        )
        for citation_id, content in evidence_map.items()
        if str(citation_id) in citation_map and str(content).strip()
    )
    question = str(insight.request_payload.get("question") or "").strip()
    task = question or (
        "Explique os principais destaques verificaveis da candidatura e proponha perguntas "
        "de investigacao."
        if insight.analysis_type == "candidate"
        else "Compare as candidaturas somente no recorte fornecido e proponha perguntas de "
        "investigacao."
    )
    candidate_context = output["input_snapshot"].get("candidate_context") or {}
    if question and candidate_context:
        task = (
            f"{question}\nContexto de comparacao: a candidatura de referencia do usuario e "
            f"{candidate_context.get('reference_name')}. As candidaturas analisadas sao "
            f"{', '.join(candidate_context.get('names') or [])}. O recorte territorial e "
            f"{output['input_snapshot'].get('filters', {}).get('level')}.\n"
            "Entregue uma resposta executiva direta e um plano pratico. Quando as evidencias "
            "permitirem, identifique territorios prioritarios e explique o criterio. Proponha "
            "acoes distribuídas entre agenda territorial, atuacao parlamentar, comunicacao "
            "publica e aprofundamento de dados, com prioridade e horizonte. Diferencie "
            "claramente atividade institucional de estrategia politico-eleitoral. Se o recorte "
            "nao permitir comparar territorios, nao improvise um ranking: explique a lacuna e "
            "indique qual granularidade ou snapshot precisa ser produzido."
        )
    generated, generation = generate_electoral_content(task, evidence)
    output["input_snapshot"] = {
        **output["input_snapshot"],
        "generation": generation,
    }
    if generated is None:
        if generation.get("fallbackUsed"):
            output["limitations"].append(
                "A geracao por IA ficou indisponivel; este resultado contem somente a camada "
                "deterministica reproduzivel."
            )
            insight.model_provider = "GABFLOW_RULES_FALLBACK"
            insight.model_name = MODEL_NAME
            insight.prompt_version = PROMPT_VERSION
        return output

    if generated.executive_summary is not None:
        output["hypotheses"].append(
            {
                "text": generated.executive_summary.text,
                "status": "EXECUTIVE_SUMMARY",
                "citation_ids": list(generated.executive_summary.citation_ids),
                "generated_by_ai": True,
            }
        )
    for claim in generated.claims:
        output["facts"].append(
            {
                "text": claim.text,
                "citation_ids": list(claim.citation_ids),
                "source_type": "ELECTORAL_AI_GROUNDED",
            }
        )
    output["hypotheses"].extend(
        {
            "text": item.text,
            "status": "CONTEXTUAL_HYPOTHESIS",
            "citation_ids": list(item.citation_ids),
            "generated_by_ai": True,
        }
        for item in generated.interpretations
    )
    output["hypotheses"].extend(
        {
            "title": item.title,
            "text": item.action,
            "rationale": item.rationale,
            "status": "STRATEGIC_RECOMMENDATION",
            "citation_ids": list(item.citation_ids),
            "generated_by_ai": True,
            "category": item.category,
            "priority": item.priority,
            "time_horizon": item.time_horizon,
            "territory": item.territory,
        }
        for item in generated.recommendations
    )
    output["hypotheses"].extend(
        {"text": text, "status": "INVESTIGATION_QUESTION", "generated_by_ai": True}
        for text in generated.hypotheses
    )
    output["limitations"].extend(generated.limitations)
    insight.model_provider = generation["provider"]
    insight.model_name = generation["model"]
    insight.prompt_version = generation["promptVersion"]
    return output


def _attach_mandate_context(insight: ElectoralInsight, output: dict) -> None:
    snapshot = latest_snapshot(insight.tenant_id, insight.mandate_id)
    if snapshot is None:
        output["input_snapshot"] = {
            **output["input_snapshot"],
            "mandate_context": {"available": False},
        }
        return

    territories = []
    for row in snapshot.payload.get("territories", []):
        if row.get("scope") != "territory":
            continue
        territories.append(
            {
                "territory_name": row.get("territory_name"),
                "suppressed": bool(row.get("suppressed")),
                "demand_count": row.get("demand_count"),
                "metrics": row.get("metrics"),
                "ict": row.get("ict"),
                "alerts": row.get("alerts") or [],
                "public_commitments": row.get("public_commitments"),
                "electoral_overlay": row.get("electoral_overlay"),
            }
        )
    mandate_summary = next(
        (
            row
            for row in snapshot.payload.get("territories", [])
            if row.get("scope") == "mandate"
        ),
        None,
    )
    evidence_payload = {
        "period_start": snapshot.period_start.isoformat(),
        "period_end": snapshot.period_end.isoformat(),
        "source_cutoff_at": snapshot.source_cutoff_at.isoformat(),
        "privacy_threshold": snapshot.privacy_threshold,
        "mandate_summary": mandate_summary,
        "territories": territories,
    }
    citation_id = f"mandate-snapshot-{snapshot.id}"
    output["citations"].append(
        {
            "id": citation_id,
            "source_type": "MANDATE_AGGREGATE",
            "title": (
                "Indicadores agregados do mandato de "
                f"{snapshot.period_start.isoformat()} a {snapshot.period_end.isoformat()}"
            ),
            "source": None,
            "snapshot_id": str(snapshot.id),
            "source_hash": snapshot.config_hash,
            "scope": "AGGREGATED_MANDATE",
        }
    )
    output["_validation_evidence"] = {
        **output.get("_validation_evidence", {}),
        citation_id: json.dumps(evidence_payload, ensure_ascii=False, sort_keys=True),
    }
    output["input_snapshot"] = {
        **output["input_snapshot"],
        "mandate_context": {
            "available": True,
            "snapshot_id": str(snapshot.id),
            "period_start": snapshot.period_start.isoformat(),
            "period_end": snapshot.period_end.isoformat(),
            "territory_count": len(territories),
            "privacy_threshold": snapshot.privacy_threshold,
        },
    }


def _citation_title(citation: dict) -> str:
    if citation.get("title"):
        return str(citation["title"])
    if citation.get("dataset_version"):
        return f"Resultado eleitoral oficial {citation['dataset_version']}"
    return "Evidencia eleitoral autorizada"


def _numbers(value: str) -> set[str]:
    without_citations = re.sub(r"\[\d+\]", "", str(value))
    return set(re.findall(r"(?<![\w-])\d+(?:[.,]\d+)?", without_citations))


def _candidate_output(analysis: dict, filters: dict) -> dict:
    candidate = analysis["candidate"]
    items = analysis["items"]
    citation_id = "dataset-1"
    facts = [
        {
            "text": (
                f"{candidate['ballot_name']} recebeu "
                f"{analysis['candidate_total_votes']} votos nominais no recorte publicado."
            ),
            "citation_ids": [citation_id],
        }
    ]
    for item in items[:3]:
        facts.append(
            {
                "text": (
                    f"Em {item['territory_name']}, foram {item['votes']} votos, "
                    f"posicao {item['rank']}."
                ),
                "citation_ids": [citation_id],
            }
        )
    calculations = [
        {
            "territory_id": item["territory_id"],
            "label": f"Participacao em {item['territory_name']}",
            "value": item["share"],
            "formula": analysis["denominator"]["formula"],
            "inputs": {"votes": item["votes"], "denominator": item["denominator_value"]},
            "citation_ids": [citation_id],
        }
        for item in items[:10]
    ]
    return _output_common(analysis, filters, facts, calculations)


def _comparison_output(analysis: dict, filters: dict) -> dict:
    citation_id = "dataset-1"
    names = {candidate["id"]: candidate["ballot_name"] for candidate in analysis["candidates"]}
    facts = [
        {
            "text": (
                f"Comparacao de {len(names)} candidaturas no mesmo cargo, eleicao e denominador."
            ),
            "citation_ids": [citation_id],
        }
    ]
    calculations = []
    reference_id = str(filters.get("reference_candidate_id") or next(iter(names)))
    reference_name = names.get(reference_id, "Candidatura de referencia")
    advantages = []
    for territory in analysis["items"]:
        ordered = sorted(territory["series"], key=lambda item: item["votes"], reverse=True)
        if not ordered:
            continue
        leader = ordered[0]
        facts.append(
            {
                "text": (
                    f"Em {territory['territory_name']}, "
                    f"{names[leader['candidate_id']]} teve o maior total entre as "
                    f"candidaturas comparadas: {leader['votes']} votos."
                ),
                "citation_ids": [citation_id],
            }
        )
        reference = next(
            (item for item in territory["series"] if item["candidate_id"] == reference_id),
            None,
        )
        opponents = [
            item for item in territory["series"]
            if item["candidate_id"] != reference_id
            and reference
            and item["votes"] > reference["votes"]
        ]
        for opponent in opponents:
            advantages.append(
                (opponent["votes"] - reference["votes"], territory, opponent, reference)
            )
        if len(ordered) > 1:
            calculations.append(
                {
                    "territory_id": territory["territory_id"],
                    "label": "Diferenca entre as duas maiores votacoes comparadas",
                    "value": ordered[0]["votes"] - ordered[1]["votes"],
                    "formula": "votos_maior - votos_segundo_maior",
                    "inputs": {"first": ordered[0]["votes"], "second": ordered[1]["votes"]},
                    "citation_ids": [citation_id],
                }
            )
    if advantages:
        facts = [
            {
                "text": (
                    f"Comparacao territorial usando {reference_name} "
                    "como candidatura de referencia."
                ),
                "citation_ids": [citation_id],
            }
        ]
        calculations = []
        for difference, territory, opponent, reference in sorted(
            advantages, key=lambda row: row[0], reverse=True
        )[:10]:
            opponent_name = names[opponent["candidate_id"]]
            facts.append(
                {
                    "text": (
                        f"Em {territory['territory_name']}, {opponent_name} obteve "
                        f"{opponent['votes']} votos contra {reference['votes']} de "
                        f"{reference_name}, vantagem de {difference} votos."
                    ),
                    "citation_ids": [citation_id],
                }
            )
            calculations.append(
                {
                    "territory_id": territory["territory_id"],
                    "label": f"Vantagem de {opponent_name} em {territory['territory_name']}",
                    "value": difference,
                    "formula": "votos_da_candidatura_comparada - votos_da_referencia",
                    "inputs": {"opponent": opponent["votes"], "reference": reference["votes"]},
                    "citation_ids": [citation_id],
                }
            )
    return _output_common(analysis, filters, facts, calculations)


def _output_common(
    analysis: dict, filters: dict, facts: list[dict], calculations: list[dict]
) -> dict:
    public_filters = {
        key: filters.get(key)
        for key in (
            "election_id",
            "candidate_ids",
            "level",
            "municipality_code",
            "dataset_version",
        )
        if key in filters
    }
    citation = {
        "id": "dataset-1",
        "source": analysis["source"],
        "source_hash": analysis.get("source_hash"),
        "dataset_version": analysis["dataset_version"],
        "filters": public_filters,
    }
    candidates = analysis.get("candidates") or [analysis.get("candidate") or {}]
    candidate_names = {
        str(item.get("id")): str(item.get("ballot_name") or item.get("full_name") or "")
        for item in candidates
        if item.get("id")
    }
    reference_id = str(filters.get("reference_candidate_id") or next(iter(candidate_names), ""))
    return {
        "input_snapshot": {
            "dataset_version": analysis["dataset_version"],
            "source_hash": analysis.get("source_hash"),
            "filters": public_filters,
            "item_count": len(analysis["items"]),
            "candidate_context": {
                "reference_id": reference_id or None,
                "reference_name": candidate_names.get(reference_id),
                "names": list(candidate_names.values()),
            },
        },
        "facts": facts,
        "calculations": calculations,
        "hypotheses": [
            {
                "text": (
                    "Diferencas territoriais podem orientar uma investigacao qualitativa, "
                    "mas estes dados nao demonstram causa."
                ),
                "status": "INVESTIGATION_QUESTION",
            }
        ],
        "limitations": [
            "A analise usa apenas resultados eleitorais agregados e publicados.",
            "Nao identifica voto individual, ideologia, intencao de voto ou relacao causal.",
            "O conteudo e um rascunho analitico e exige revisao humana.",
        ],
        "citations": [citation],
        "_validation_evidence": {
            "dataset-1": (
                json.dumps(analysis, ensure_ascii=False, sort_keys=True)
                + f" candidate_count {len(analysis.get('candidates', [])) or 1}"
            )
        },
    }
