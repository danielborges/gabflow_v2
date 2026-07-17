import hashlib
import uuid
from datetime import date
from typing import Protocol
from urllib.parse import urlsplit

from flask import current_app
from sqlalchemy import or_, select

from app.ai.duplicates import (
    EmbeddingProviderError,
    LocalSimilarityProvider,
    OllamaEmbeddingProvider,
)
from app.extensions import db
from app.models import NormativeSource

SOURCE_TYPES = {
    "LEI_ORGANICA",
    "REGIMENTO_INTERNO",
    "LEI_MUNICIPAL",
    "DECRETO",
    "PLANO_DIRETOR",
    "CODIGO_OBRAS",
    "CODIGO_POSTURAS",
    "OUTRO",
}


class FoundationRetriever(Protocol):
    def retrieve(self, tenant_id: uuid.UUID, query: str, limit: int) -> dict: ...


class HybridNormativeRetriever:
    def retrieve(self, tenant_id: uuid.UUID, query: str, limit: int) -> dict:
        today = date.today()
        candidate_limit = current_app.config["AI_FOUNDATION_CANDIDATE_LIMIT"]
        candidates = list(
            db.session.execute(
                select(NormativeSource)
                .where(
                    NormativeSource.tenant_id == tenant_id,
                    NormativeSource.active.is_(True),
                    or_(NormativeSource.valid_from.is_(None), NormativeSource.valid_from <= today),
                    or_(
                        NormativeSource.valid_until.is_(None),
                        NormativeSource.valid_until >= today,
                    ),
                )
                .order_by(NormativeSource.updated_at.desc())
                .limit(candidate_limit)
            ).scalars()
        )
        texts = [_source_text(item) for item in candidates]
        provider = _foundation_provider()
        used_fallback = False
        fallback_error = None
        similarities: list[float] = []
        if candidates:
            try:
                similarities = provider.similarities(query, texts)
            except EmbeddingProviderError as error:
                if not current_app.config["AI_LEGISLATIVE_FALLBACK_ENABLED"]:
                    raise
                current_app.logger.warning(
                    "Falha na recuperação normativa; usando similaridade local: %s", error
                )
                provider = LocalSimilarityProvider()
                similarities = provider.similarities(query, texts)
                used_fallback = True
                fallback_error = str(error)

        lexical_scores = LocalSimilarityProvider().similarities(query, texts)
        threshold = current_app.config["AI_FOUNDATION_SCORE_THRESHOLD"]
        ranked = []
        for item, semantic_score, lexical_score in zip(
            candidates, similarities, lexical_scores, strict=True
        ):
            score = semantic_score * 0.9 + lexical_score * 0.1
            if score < threshold:
                continue
            citation = normative_source_data(item)
            citation.update(
                {
                    "pontuacao": round(score, 4),
                    "similaridadeSemantica": round(semantic_score, 4),
                    "similaridadeLexical": round(lexical_score, 4),
                    "justificativas": _reasons(item, semantic_score, lexical_score),
                }
            )
            ranked.append(citation)
        ranked.sort(key=lambda item: item["pontuacao"], reverse=True)
        return {
            "consulta": query,
            "colecao": "legislacao",
            "modelo": provider.model,
            "fallbackUtilizado": used_fallback,
            "erroFallback": fallback_error,
            "limiar": threshold,
            "totalCandidatos": len(candidates),
            "fontes": ranked[:limit],
            "grounded": bool(ranked),
            "revisaoHumanaObrigatoria": True,
            "aplicacaoAutomatica": False,
            "conteudoTratadoComoDado": True,
        }


def foundation_retriever() -> FoundationRetriever:
    return HybridNormativeRetriever()


def normative_source_values(payload: dict) -> dict:
    source_type = str(payload.get("tipo", "")).strip().upper()
    title = str(payload.get("titulo", "")).strip()
    reference = str(payload.get("referencia", "")).strip()
    excerpt = str(payload.get("trecho", "")).strip()
    version = str(payload.get("versao", "1")).strip() or "1"
    jurisdiction = str(payload.get("jurisdicao", "")).strip() or None
    source_url = str(payload.get("url", "")).strip() or None
    if source_type not in SOURCE_TYPES:
        raise ValueError("Tipo de fonte normativa inválido.")
    if not title or len(title) > 240:
        raise ValueError("Informe um título válido para a fonte normativa.")
    if not reference or len(reference) > 240:
        raise ValueError("Informe uma referência normativa válida.")
    if len(excerpt) < 20 or len(excerpt) > 20000:
        raise ValueError("O trecho normativo deve possuir entre 20 e 20.000 caracteres.")
    if len(version) > 80 or (jurisdiction and len(jurisdiction) > 120):
        raise ValueError("Versão ou jurisdição inválida.")
    if source_url:
        parsed = urlsplit(source_url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("A URL da fonte deve utilizar HTTP ou HTTPS.")
    try:
        valid_from = (
            date.fromisoformat(str(payload["vigenteDesde"]))
            if payload.get("vigenteDesde")
            else None
        )
        valid_until = (
            date.fromisoformat(str(payload["vigenteAte"]))
            if payload.get("vigenteAte")
            else None
        )
    except ValueError as error:
        raise ValueError("Período de vigência inválido.") from error
    if valid_from and valid_until and valid_until < valid_from:
        raise ValueError("A vigência final não pode anteceder a inicial.")
    return {
        "source_type": source_type,
        "title": title,
        "reference": reference,
        "excerpt": excerpt,
        "jurisdiction": jurisdiction,
        "source_url": source_url,
        "version": version,
        "checksum": hashlib.sha256(excerpt.encode("utf-8")).hexdigest(),
        "valid_from": valid_from,
        "valid_until": valid_until,
    }


def normative_source_data(item: NormativeSource) -> dict:
    return {
        "id": str(item.id),
        "tipo": item.source_type,
        "titulo": item.title,
        "referencia": item.reference,
        "trecho": item.excerpt,
        "jurisdicao": item.jurisdiction,
        "url": item.source_url,
        "versao": item.version,
        "checksum": item.checksum,
        "vigenteDesde": item.valid_from.isoformat() if item.valid_from else None,
        "vigenteAte": item.valid_until.isoformat() if item.valid_until else None,
        "colecaoRag": item.rag_collection,
        "ativo": item.active,
        "criadaEm": item.created_at.isoformat(),
        "atualizadaEm": item.updated_at.isoformat(),
    }


def _foundation_provider():
    if current_app.config["AI_FOUNDATION_PROVIDER"].lower() == "local":
        return LocalSimilarityProvider()
    return OllamaEmbeddingProvider(
        current_app.config["OLLAMA_BASE_URL"],
        current_app.config["AI_EMBEDDING_MODEL"],
        current_app.config["AI_LEGISLATIVE_TIMEOUT_SECONDS"],
    )


def _source_text(item: NormativeSource) -> str:
    return "\n".join(
        value
        for value in (item.title, item.reference, item.jurisdiction, item.excerpt)
        if value
    )


def _reasons(
    item: NormativeSource, semantic_score: float, lexical_score: float
) -> list[str]:
    reasons = [f"Similaridade semântica de {round(semantic_score * 100)}%"]
    if lexical_score >= 0.2:
        reasons.append("Termos jurídicos e temáticos em comum")
    if item.valid_until:
        reasons.append(f"Vigente até {item.valid_until.strftime('%d/%m/%Y')}")
    else:
        reasons.append("Sem término de vigência cadastrado")
    return reasons
