import re
import unicodedata
import uuid

from flask import current_app
from sqlalchemy import select

from app.ai.duplicates import (
    EmbeddingProviderError,
    LocalSimilarityProvider,
    OllamaEmbeddingProvider,
)
from app.extensions import db
from app.models import (
    LegislativeDocumentType,
    LegislativeDraft,
    LegislativeDraftStatus,
    LegislativeGenerationStatus,
)


def semantic_precedent_search(
    tenant_id: uuid.UUID,
    query: str,
    *,
    document_type: LegislativeDocumentType | None = None,
    status: LegislativeDraftStatus | None = None,
    exclude_id: uuid.UUID | None = None,
    limit: int | None = None,
) -> dict:
    threshold = current_app.config["AI_PRECEDENT_SCORE_THRESHOLD"]
    fallback_threshold = current_app.config["AI_PRECEDENT_FALLBACK_SCORE_THRESHOLD"]
    maximum = min(limit or current_app.config["AI_PRECEDENT_MAX_RESULTS"], 20)
    candidate_limit = current_app.config["AI_PRECEDENT_CANDIDATE_LIMIT"]
    statement = select(LegislativeDraft).where(
        LegislativeDraft.tenant_id == tenant_id,
        LegislativeDraft.generation_status == LegislativeGenerationStatus.CONCLUIDA,
    )
    if document_type:
        statement = statement.where(LegislativeDraft.document_type == document_type)
    if status:
        statement = statement.where(LegislativeDraft.status == status)
    if exclude_id:
        statement = statement.where(LegislativeDraft.id != exclude_id)
    candidates = list(
        db.session.execute(
            statement.order_by(LegislativeDraft.updated_at.desc()).limit(candidate_limit)
        ).scalars()
    )
    candidate_texts = [_draft_text(item) for item in candidates]
    lexical_scores, exact_title_matches = _lexical_scores(query, candidates, candidate_texts)
    semantic_candidate_limit = min(
        current_app.config["AI_PRECEDENT_SEMANTIC_CANDIDATE_LIMIT"],
        len(candidates),
    )
    semantic_indexes = sorted(
        range(len(candidates)),
        key=lambda index: (lexical_scores[index], -index),
        reverse=True,
    )[:semantic_candidate_limit]
    provider = _precedent_provider()
    used_fallback = False
    fallback_error = None
    similarities = [0.0] * len(candidates)
    if candidates:
        try:
            semantic_scores = provider.similarities(
                query,
                [candidate_texts[index] for index in semantic_indexes],
            )
            for index, score in zip(semantic_indexes, semantic_scores, strict=True):
                similarities[index] = score
        except EmbeddingProviderError as error:
            if not current_app.config["AI_LEGISLATIVE_FALLBACK_ENABLED"]:
                raise
            current_app.logger.warning(
                "Falha na busca semântica de precedentes; usando similaridade local: %s",
                error,
            )
            provider = LocalSimilarityProvider()
            similarities = lexical_scores
            used_fallback = True
            fallback_error = str(error)

    applied_threshold = fallback_threshold if used_fallback else threshold
    ranked = []
    for candidate, semantic_score, lexical_score, exact_title_match in zip(
        candidates, similarities, lexical_scores, exact_title_matches, strict=True
    ):
        score = lexical_score if used_fallback else max(
            semantic_score * 0.9 + lexical_score * 0.1,
            lexical_score,
        )
        if score < applied_threshold:
            continue
        ranked.append(
            {
                "id": str(candidate.id),
                "titulo": candidate.title,
                "tipo": candidate.document_type.value,
                "status": candidate.status.value,
                "protocolo": candidate.protocol_number,
                "resumo": _excerpt(candidate.content or candidate.justification or ""),
                "similaridade": round(score, 4),
                "similaridadeSemantica": round(semantic_score, 4),
                "similaridadeLexical": round(lexical_score, 4),
                "criadaEm": candidate.created_at.isoformat(),
                "atualizadaEm": candidate.updated_at.isoformat(),
                "aprovadaEm": (
                    candidate.approved_at.isoformat() if candidate.approved_at else None
                ),
                "justificativas": _reasons(
                    candidate,
                    semantic_score,
                    lexical_score,
                    used_fallback=used_fallback,
                    exact_title_match=exact_title_match,
                ),
            }
        )
    ranked.sort(
        key=lambda item: (item["similaridade"], item["atualizadaEm"]), reverse=True
    )
    return {
        "consulta": query,
        "modelo": provider.model,
        "fallbackUtilizado": used_fallback,
        "erroFallback": fallback_error,
        "limiar": applied_threshold,
        "totalCandidatos": len(candidates),
        "candidatosSemanticos": len(semantic_indexes),
        "content": ranked[:maximum],
    }


def _precedent_provider():
    if current_app.config["AI_PRECEDENT_PROVIDER"].lower() == "local":
        return LocalSimilarityProvider()
    return OllamaEmbeddingProvider(
        current_app.config["OLLAMA_BASE_URL"],
        current_app.config["AI_EMBEDDING_MODEL"],
        current_app.config["AI_LEGISLATIVE_TIMEOUT_SECONDS"],
        current_app.config["AI_EMBEDDING_BATCH_SIZE"],
    )


def _draft_text(item: LegislativeDraft) -> str:
    legal_basis = "\n".join(
        " ".join(
            str(source.get(field, "")).strip()
            for field in ("titulo", "referencia", "trecho")
        ).strip()
        for source in (item.legal_basis or [])
        if isinstance(source, dict)
    )
    return "\n".join(
        value
        for value in (
            item.title.strip(),
            (item.content or "").strip(),
            (item.justification or "").strip(),
            legal_basis,
        )
        if value
    )


def _lexical_scores(
    query: str,
    candidates: list[LegislativeDraft],
    candidate_texts: list[str],
) -> tuple[list[float], list[bool]]:
    provider = LocalSimilarityProvider()
    title_scores = provider.similarities(query, [item.title for item in candidates])
    document_scores = provider.similarities(query, candidate_texts)
    normalized_query = _normalize_text(query)
    query_tokens = set(normalized_query.split())
    scores: list[float] = []
    exact_matches: list[bool] = []
    for candidate, title_score, document_score in zip(
        candidates, title_scores, document_scores, strict=True
    ):
        normalized_title = _normalize_text(candidate.title)
        title_tokens = set(normalized_title.split())
        exact_match = bool(
            normalized_query
            and f" {normalized_query} " in f" {normalized_title} "
        )
        score = max(document_score, title_score * 0.9)
        if exact_match:
            score = max(score, 0.95)
        elif query_tokens and query_tokens.issubset(title_tokens):
            score = max(score, 0.8)
        scores.append(min(score, 1.0))
        exact_matches.append(exact_match)
    return scores, exact_matches


def _normalize_text(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value.casefold())
    without_accents = "".join(char for char in decomposed if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", " ", without_accents).strip()


def _excerpt(value: str) -> str:
    normalized = re.sub(r"\s+", " ", value).strip()
    return normalized[:277] + "..." if len(normalized) > 280 else normalized


def _reasons(
    item: LegislativeDraft,
    semantic_score: float,
    lexical_score: float,
    *,
    used_fallback: bool,
    exact_title_match: bool,
) -> list[str]:
    reasons = [
        (
            f"Correspondência lexical de {round(lexical_score * 100)}%"
            if used_fallback
            else f"Similaridade semântica de {round(semantic_score * 100)}%"
        )
    ]
    if exact_title_match:
        reasons.append("Expressão exata encontrada no título")
    if lexical_score >= 0.25:
        reasons.append("Vocabulário relevante em comum")
    if item.status == LegislativeDraftStatus.APROVADA:
        reasons.append("Proposição aprovada")
    if item.protocol_number:
        reasons.append(f"Protocolada sob {item.protocol_number}")
    return reasons
