import hashlib
import math
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
from app.models import (
    NormativeSource,
    RagChunk,
    RagDocument,
    RagDocumentLifecycle,
    RagDocumentVersion,
    RagIngestionStatus,
    RagKnowledgeSource,
    RagKnowledgeSourceStatus,
)
from app.rag.operational_memory import NORMATIVE_SOURCE_ENTITY
from app.rag.service import rag_embedding_provider

SOURCE_TYPES = {
    "CONSTITUICAO",
    "LEI_ORGANICA",
    "REGIMENTO_INTERNO",
    "LEI_FEDERAL",
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
        if not candidates:
            return _recovery_response(
                query,
                limit,
                candidates,
                [],
                model=_foundation_provider().model,
                used_fallback=False,
                fallback_error=None,
                retrieval_origin="RAG_PRIVADO",
                indexed_count=0,
            )
        indexed = _indexed_normative_texts(
            tenant_id,
            {item.id for item in candidates},
        )
        if indexed:
            return self._retrieve_from_private_rag(query, limit, candidates, indexed)
        return self._retrieve_from_catalog_fallback(query, limit, candidates)

    def _retrieve_from_private_rag(
        self,
        query: str,
        limit: int,
        candidates: list[NormativeSource],
        indexed: dict[uuid.UUID, list[RagChunk]],
    ) -> dict:
        provider = rag_embedding_provider()
        used_fallback = False
        fallback_error = None
        query_vector: list[float] | None = None
        try:
            query_vector = provider.embeddings([query])[0]
        except (EmbeddingProviderError, IndexError) as error:
            current_app.logger.warning(
                "Falha no embedding da recuperacao normativa; "
                "usando os chunks do RAG em modo lexical: %s",
                error,
            )
            provider = LocalSimilarityProvider()
            used_fallback = True
            fallback_error = str(error)

        ranked = []
        unindexed = []
        for item in candidates:
            chunks = indexed.get(item.id)
            if not chunks:
                unindexed.append(item)
                continue
            text = "\n".join(chunk.content for chunk in chunks)
            lexical_score = LocalSimilarityProvider().similarities(query, [text])[0]
            compatible = [
                chunk
                for chunk in chunks
                if query_vector
                and chunk.embedding_model == getattr(provider, "model", None)
                and len(chunk.embedding) == len(query_vector)
            ]
            semantic_score = (
                max(_cosine(query_vector, chunk.embedding) for chunk in compatible)
                if compatible and query_vector
                else lexical_score
            )
            _append_ranked(ranked, item, semantic_score, lexical_score)
        if unindexed:
            local = LocalSimilarityProvider()
            texts = [_source_text(item) for item in unindexed]
            scores = local.similarities(query, texts)
            for item, score in zip(unindexed, scores, strict=True):
                _append_ranked(ranked, item, score, score)
            used_fallback = True
            lag_message = (
                f"{len(unindexed)} fonte(s) vigente(s) ainda aguardam indexacao no RAG privado."
            )
            fallback_error = "; ".join(
                value for value in (fallback_error, lag_message) if value
            )
        return _recovery_response(
            query,
            limit,
            candidates,
            ranked,
            model=provider.model,
            used_fallback=used_fallback,
            fallback_error=fallback_error,
            retrieval_origin=(
                "RAG_PRIVADO_COM_FALLBACK_PARCIAL"
                if unindexed
                else "RAG_PRIVADO"
            ),
            indexed_count=len(indexed),
        )

    def _retrieve_from_catalog_fallback(
        self,
        query: str,
        limit: int,
        candidates: list[NormativeSource],
    ) -> dict:
        texts = [_source_text(item) for item in candidates]
        provider = _foundation_provider()
        fallback_error = "Indice normativo do RAG privado ainda indisponivel."
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
                fallback_error = f"{fallback_error} {error}"

        lexical_scores = LocalSimilarityProvider().similarities(query, texts)
        ranked = []
        for item, semantic_score, lexical_score in zip(
            candidates, similarities, lexical_scores, strict=True
        ):
            _append_ranked(ranked, item, semantic_score, lexical_score)
        return _recovery_response(
            query,
            limit,
            candidates,
            ranked,
            model=provider.model,
            used_fallback=True,
            fallback_error=fallback_error,
            retrieval_origin="CATALOGO_RELACIONAL_FALLBACK",
            indexed_count=0,
        )


def _indexed_normative_texts(
    tenant_id: uuid.UUID,
    source_ids: set[uuid.UUID],
) -> dict[uuid.UUID, list[RagChunk]]:
    if not source_ids:
        return {}
    rows = db.session.execute(
        select(RagKnowledgeSource.entity_id, RagChunk)
        .join(
            RagDocumentVersion,
            RagDocumentVersion.id == RagKnowledgeSource.latest_version_id,
        )
        .join(
            RagDocument,
            RagDocument.id == RagDocumentVersion.document_id,
        )
        .join(RagChunk, RagChunk.version_id == RagDocumentVersion.id)
        .where(
            RagKnowledgeSource.tenant_id == tenant_id,
            RagKnowledgeSource.entity_type == NORMATIVE_SOURCE_ENTITY,
            RagKnowledgeSource.entity_id.in_(source_ids),
            RagKnowledgeSource.status == RagKnowledgeSourceStatus.ATIVA,
            RagDocumentVersion.tenant_id == tenant_id,
            RagDocument.tenant_id == tenant_id,
            RagDocument.active.is_(True),
            RagDocumentVersion.ingestion_status == RagIngestionStatus.INDEXADO,
            RagDocumentVersion.lifecycle_status == RagDocumentLifecycle.VIGENTE,
            RagChunk.tenant_id == tenant_id,
        )
        .order_by(RagKnowledgeSource.entity_id, RagChunk.position)
    ).all()
    indexed: dict[uuid.UUID, list[RagChunk]] = {}
    for entity_id, chunk in rows:
        indexed.setdefault(entity_id, []).append(chunk)
    return indexed


def _append_ranked(
    ranked: list[dict],
    item: NormativeSource,
    semantic_score: float,
    lexical_score: float,
) -> None:
    score = semantic_score * 0.9 + lexical_score * 0.1
    if score < current_app.config["AI_FOUNDATION_SCORE_THRESHOLD"]:
        return
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


def _recovery_response(
    query: str,
    limit: int,
    candidates: list[NormativeSource],
    ranked: list[dict],
    *,
    model: str,
    used_fallback: bool,
    fallback_error: str | None,
    retrieval_origin: str,
    indexed_count: int,
) -> dict:
    ranked.sort(key=lambda item: item["pontuacao"], reverse=True)
    return {
        "consulta": query,
        "colecao": "legislacao",
        "origemRecuperacao": retrieval_origin,
        "catalogoAutoritativo": True,
        "revalidacaoCatalogo": True,
        "modelo": model,
        "fallbackUtilizado": used_fallback,
        "erroFallback": fallback_error,
        "limiar": current_app.config["AI_FOUNDATION_SCORE_THRESHOLD"],
        "totalCandidatos": len(candidates),
        "totalCandidatosIndexados": indexed_count,
        "fontes": ranked[:limit],
        "grounded": bool(ranked),
        "revisaoHumanaObrigatoria": True,
        "aplicacaoAutomatica": False,
        "conteudoTratadoComoDado": True,
    }


def _cosine(first: list[float], second: list[float]) -> float:
    first_norm = math.sqrt(sum(value * value for value in first))
    second_norm = math.sqrt(sum(value * value for value in second))
    if not first_norm or not second_norm:
        return 0.0
    dot_product = sum(a * b for a, b in zip(first, second, strict=True))
    return max(0.0, min(1.0, dot_product / (first_norm * second_norm)))


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
        "origem": item.origin,
        "provedor": item.provider,
        "idExterno": item.external_id,
        "urlOficial": item.official_source_url,
        "importadaEm": item.imported_at.isoformat() if item.imported_at else None,
        "revisadaEm": item.reviewed_at.isoformat() if item.reviewed_at else None,
        "substituiFonteId": str(item.supersedes_source_id) if item.supersedes_source_id else None,
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
        current_app.config["AI_EMBEDDING_BATCH_SIZE"],
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
