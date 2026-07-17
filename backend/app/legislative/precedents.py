import re
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
    provider = _precedent_provider()
    used_fallback = False
    fallback_error = None
    similarities: list[float] = []
    if candidates:
        try:
            similarities = provider.similarities(query, candidate_texts)
        except EmbeddingProviderError as error:
            if not current_app.config["AI_LEGISLATIVE_FALLBACK_ENABLED"]:
                raise
            current_app.logger.warning(
                "Falha na busca semântica de precedentes; usando similaridade local: %s",
                error,
            )
            provider = LocalSimilarityProvider()
            similarities = provider.similarities(query, candidate_texts)
            used_fallback = True
            fallback_error = str(error)

    lexical_scores = LocalSimilarityProvider().similarities(query, candidate_texts)
    ranked = []
    for candidate, semantic_score, lexical_score in zip(
        candidates, similarities, lexical_scores, strict=True
    ):
        score = semantic_score * 0.9 + lexical_score * 0.1
        if score < threshold:
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
                "justificativas": _reasons(candidate, semantic_score, lexical_score),
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
        "limiar": threshold,
        "totalCandidatos": len(candidates),
        "content": ranked[:maximum],
    }


def _precedent_provider():
    if current_app.config["AI_PRECEDENT_PROVIDER"].lower() == "local":
        return LocalSimilarityProvider()
    return OllamaEmbeddingProvider(
        current_app.config["OLLAMA_BASE_URL"],
        current_app.config["AI_EMBEDDING_MODEL"],
        current_app.config["AI_LEGISLATIVE_TIMEOUT_SECONDS"],
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


def _excerpt(value: str) -> str:
    normalized = re.sub(r"\s+", " ", value).strip()
    return normalized[:277] + "..." if len(normalized) > 280 else normalized


def _reasons(
    item: LegislativeDraft, semantic_score: float, lexical_score: float
) -> list[str]:
    reasons = [f"Similaridade semântica de {round(semantic_score * 100)}%"]
    if lexical_score >= 0.25:
        reasons.append("Vocabulário relevante em comum")
    if item.status == LegislativeDraftStatus.APROVADA:
        reasons.append("Proposição aprovada")
    if item.protocol_number:
        reasons.append(f"Protocolada sob {item.protocol_number}")
    return reasons
