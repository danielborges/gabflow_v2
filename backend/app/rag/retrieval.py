import hashlib
import heapq
import math
import re
import unicodedata
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from itertools import chain
from uuid import UUID

from flask import current_app
from sqlalchemy import exists, or_, select, text
from sqlalchemy.orm import joinedload

from app.ai.duplicates import EmbeddingProviderError
from app.extensions import db
from app.models import (
    GlobalKnowledgeChunk,
    GlobalKnowledgeDocument,
    GlobalKnowledgeDocumentVersion,
    RagChunk,
    RagDocument,
    RagDocumentAccess,
    RagDocumentLifecycle,
    RagDocumentVersion,
    RagIngestionStatus,
    RagKnowledgeSource,
    RagKnowledgeSourceStatus,
)
from app.rag.content_security import has_prompt_injection
from app.rag.distribution import global_versions_for_tenant
from app.rag.service import LocalHashEmbeddingProvider, rag_embedding_provider

REFUSAL_MESSAGE = (
    "Nao encontrei evidencia suficiente na base documental acessivel para responder de forma "
    "conclusiva. Cadastre, publique ou revise fontes vigentes relacionadas ao tema antes de usar "
    "o assistente para uma resposta oficial."
)

@dataclass(frozen=True)
class RankedChunk:
    chunk: RagChunk | GlobalKnowledgeChunk
    scope: str
    score: float
    ranking_score: float
    semantic_score: float
    lexical_score: float
    authority_score: float
    freshness_score: float
    retrieval_mode: str
    sanitized: dict
    reasons: list[str]


def answer_query(tenant_id: UUID, role: str | None, query: str, limit: int | None = None) -> dict:
    normalized_query = _validate_query(query)
    max_results = _safe_limit(limit)
    ranked, provider_model, fallback_used, fallback_error = retrieve_chunks(
        tenant_id,
        role,
        normalized_query,
        max_results,
    )
    min_evidence = current_app.config["RAG_RETRIEVAL_MIN_EVIDENCE_SCORE"]
    grounded = bool(ranked)
    sources = [_source_data(item) for item in ranked]
    safety_flags = _safety_summary(sources)

    if not grounded:
        return {
            "consulta": normalized_query,
            "resposta": REFUSAL_MESSAGE,
            "fundamentada": False,
            "recusaConclusiva": True,
            "conteudoTratadoComoDado": True,
            "limiarEvidencia": min_evidence,
            "modeloEmbedding": provider_model,
            "fallbackUtilizado": fallback_used,
            "erroFallback": fallback_error,
            "seguranca": safety_flags,
            "fontes": sources,
            "escoposConsultados": ["GLOBAL", "PRIVADO"],
            "recuperacao": _retrieval_summary(sources),
        }

    return {
        "consulta": normalized_query,
        "resposta": _grounded_answer(sources),
        "fundamentada": True,
        "recusaConclusiva": False,
        "conteudoTratadoComoDado": True,
        "limiarEvidencia": min_evidence,
        "modeloEmbedding": provider_model,
        "fallbackUtilizado": fallback_used,
        "erroFallback": fallback_error,
        "seguranca": safety_flags,
        "fontes": sources,
        "escoposConsultados": ["GLOBAL", "PRIVADO"],
        "recuperacao": _retrieval_summary(sources),
    }


def retrieve_chunks(
    tenant_id: UUID, role: str | None, query: str, limit: int
) -> tuple[list[RankedChunk], str, bool, str | None]:
    candidate_iterator = _candidate_chunks(tenant_id, role)
    first_candidate = next(candidate_iterator, None)
    if first_candidate is None:
        return [], LocalHashEmbeddingProvider.model, False, None
    candidates = chain((first_candidate,), candidate_iterator)

    fallback_used = False
    fallback_error = None
    query_vector = None
    try:
        provider = rag_embedding_provider()
        query_vector = provider.embeddings([query])[0]
    except EmbeddingProviderError as error:
        current_app.logger.warning(
            "Falha no embedding RAG; usando busca lexical sem comparar modelos: %s",
            error,
        )
        provider = None
        fallback_used = True
        fallback_error = str(error)

    provider_model = provider.model if provider is not None else "gabflow-lexical-retrieval-v2"
    threshold = max(
        current_app.config["RAG_RETRIEVAL_SCORE_THRESHOLD"],
        current_app.config["RAG_RETRIEVAL_MIN_EVIDENCE_SCORE"],
    )
    pool_limit = max(limit, current_app.config["RAG_RETRIEVAL_CANDIDATE_LIMIT"])
    per_document_limit = current_app.config["RAG_RETRIEVAL_MAX_CHUNKS_PER_DOCUMENT"]
    document_heaps: dict[
        UUID, list[tuple[tuple[float, float, float, float, int], RankedChunk]]
    ] = {}
    sequence = 0
    for scope, chunk in candidates:
        sanitized = _sanitize_source_content(chunk.content)
        if not sanitized["usable"]:
            continue
        metadata = _chunk_metadata(scope, chunk)
        content_lexical = _lexical_score(query, sanitized["content"])
        metadata_lexical = _lexical_score(query, metadata)
        lexical_score = max(
            content_lexical,
            (content_lexical * 0.82) + (metadata_lexical * 0.18),
        )
        semantic_compatible = bool(
            query_vector is not None
            and provider is not None
            and chunk.embedding_model == provider.model
            and len(query_vector) == len(chunk.embedding)
            and not sanitized["sanitized"]
        )
        semantic_score = _cosine(query_vector, chunk.embedding) if semantic_compatible else 0.0
        retrieval_mode = "HIBRIDO" if semantic_compatible else "LEXICAL"
        if semantic_compatible:
            score = max(
                (semantic_score * 0.62) + (lexical_score * 0.38),
                lexical_score * 0.9,
            )
        elif provider is None:
            score = lexical_score
        else:
            score = lexical_score * 0.9
        if score < threshold:
            continue
        authority_score = _authority_score(scope, chunk)
        freshness_score = _freshness_score(scope, chunk)
        ranking_score = (
            score
            + (authority_score * current_app.config["RAG_RETRIEVAL_AUTHORITY_RERANK_WEIGHT"])
            + (freshness_score * current_app.config["RAG_RETRIEVAL_FRESHNESS_RERANK_WEIGHT"])
        )
        ranked_item = RankedChunk(
            chunk=chunk,
            scope=scope,
            score=score,
            ranking_score=ranking_score,
            semantic_score=semantic_score,
            lexical_score=lexical_score,
            authority_score=authority_score,
            freshness_score=freshness_score,
            retrieval_mode=retrieval_mode,
            sanitized=sanitized,
            reasons=_reasons(
                semantic_score,
                lexical_score,
                authority_score,
                freshness_score,
                retrieval_mode,
                sanitized["sanitized"],
            ),
        )
        sequence += 1
        document_id = chunk.version.document_id
        document_heap = document_heaps.setdefault(document_id, [])
        _keep_best_candidate(document_heap, ranked_item, per_document_limit, sequence)
    ranked_entries = sorted(
        chain.from_iterable(document_heaps.values()),
        key=lambda entry: entry[0],
        reverse=True,
    )
    ranked = []
    seen_checksums = set()
    for _, item in ranked_entries:
        if item.chunk.content_checksum in seen_checksums:
            continue
        seen_checksums.add(item.chunk.content_checksum)
        ranked.append(item)
        if len(ranked) >= pool_limit:
            break
    ranked = _deduplicate_and_limit(ranked, limit)
    return ranked, provider_model, fallback_used, fallback_error


def _candidate_chunks(
    tenant_id: UUID, role: str | None
) -> Iterable[tuple[str, RagChunk | GlobalKnowledgeChunk]]:
    for chunk in _private_candidate_chunks(tenant_id, role):
        yield "PRIVADO", chunk
    for chunk in _global_candidate_chunks(tenant_id):
        yield "GLOBAL", chunk


def _private_candidate_chunks(tenant_id: UUID, role: str | None) -> Iterable[RagChunk]:
    today = datetime.now(UTC).date()
    has_operational_source = exists(
        select(RagKnowledgeSource.id).where(
            RagKnowledgeSource.tenant_id == tenant_id,
            RagKnowledgeSource.document_id == RagDocument.id,
        )
    )
    has_eligible_operational_source = exists(
        select(RagKnowledgeSource.id).where(
            RagKnowledgeSource.tenant_id == tenant_id,
            RagKnowledgeSource.document_id == RagDocument.id,
            RagKnowledgeSource.status.in_(
                {
                    RagKnowledgeSourceStatus.ATIVA,
                    RagKnowledgeSourceStatus.PENDENTE,
                    RagKnowledgeSourceStatus.QUARENTENA,
                    RagKnowledgeSourceStatus.ERRO,
                }
            ),
            or_(
                RagKnowledgeSource.retention_until.is_(None),
                RagKnowledgeSource.retention_until >= today,
            ),
        )
    )
    statement = (
        select(RagChunk)
        .join(RagDocumentVersion, RagChunk.version_id == RagDocumentVersion.id)
        .join(RagDocument, RagDocumentVersion.document_id == RagDocument.id)
        .options(joinedload(RagChunk.version).joinedload(RagDocumentVersion.document))
        .where(
            RagChunk.tenant_id == tenant_id,
            RagDocumentVersion.tenant_id == tenant_id,
            RagDocument.tenant_id == tenant_id,
            RagDocument.active.is_(True),
            RagDocumentVersion.ingestion_status == RagIngestionStatus.INDEXADO,
            RagDocumentVersion.lifecycle_status == RagDocumentLifecycle.VIGENTE,
            or_(RagDocumentVersion.valid_from.is_(None), RagDocumentVersion.valid_from <= today),
            or_(RagDocumentVersion.valid_until.is_(None), RagDocumentVersion.valid_until >= today),
            or_(~has_operational_source, has_eligible_operational_source),
        )
        .order_by(RagChunk.id)
    )
    if role not in {"admin", "manager"}:
        statement = statement.where(RagDocument.access_level == RagDocumentAccess.INTERNO)
    return db.session.execute(
        statement.execution_options(yield_per=current_app.config["RAG_RETRIEVAL_SCAN_BATCH_SIZE"])
    ).scalars()


def _global_candidate_chunks(tenant_id: UUID) -> Iterable[GlobalKnowledgeChunk]:
    versions = global_versions_for_tenant(tenant_id)
    version_ids = [version.id for version in versions]
    if not version_ids:
        return []
    statement = (
        select(GlobalKnowledgeChunk)
        .where(GlobalKnowledgeChunk.version_id.in_(version_ids))
        .options(
            joinedload(GlobalKnowledgeChunk.version)
            .joinedload(GlobalKnowledgeDocumentVersion.document)
            .joinedload(GlobalKnowledgeDocument.collection)
        )
        .order_by(GlobalKnowledgeChunk.id)
    )
    if db.engine.dialect.name == "postgresql":
        permitted_chunk_ids = list(
            db.session.execute(
                text(
                    "SELECT chunk_id "
                    "FROM rag_global.tenant_published_chunks "
                    "WHERE tenant_id = :tenant_id"
                ),
                {"tenant_id": tenant_id},
            ).scalars()
        )
        if not permitted_chunk_ids:
            return []
        statement = statement.where(GlobalKnowledgeChunk.id.in_(permitted_chunk_ids))
    return db.session.execute(
        statement.execution_options(yield_per=current_app.config["RAG_RETRIEVAL_SCAN_BATCH_SIZE"])
    ).scalars()


def _source_data(item: RankedChunk) -> dict:
    if item.scope == "GLOBAL":
        return _global_source_data(item)
    return _private_source_data(item)


def _private_source_data(item: RankedChunk) -> dict:
    version = item.chunk.version
    document = version.document
    sanitized = item.sanitized
    operational = db.session.execute(
        select(RagKnowledgeSource).where(
            RagKnowledgeSource.tenant_id == document.tenant_id,
            RagKnowledgeSource.document_id == document.id,
        )
    ).scalar_one_or_none()
    return {
        "escopo": "PRIVADO",
        "origem": "GABINETE",
        "rotuloFonte": "Fonte do Gabinete",
        "colecao": "Base do Gabinete",
        "colecaoId": None,
        "documentoId": str(document.id),
        "titulo": document.title,
        "tipo": document.document_type,
        "orgao": document.agency,
        "nivelAcesso": document.access_level.value,
        "fonteModulo": operational.source_module if operational else None,
        "entidadeOrigemTipo": operational.entity_type if operational else None,
        "entidadeOrigemId": str(operational.entity_id) if operational else None,
        "versaoProjetor": operational.projector_version if operational else None,
        "revisaoOrigem": operational.source_revision if operational else None,
        "estadoFonteOperacional": (
            operational.status.value if operational else None
        ),
        "codigoErroFonte": operational.error_code if operational else None,
        "finalidade": operational.purpose if operational else None,
        "baseLegal": operational.legal_basis if operational else None,
        "retencaoAte": (
            operational.retention_until.isoformat()
            if operational and operational.retention_until
            else None
        ),
        "versaoId": str(version.id),
        "versao": version.version_label,
        "estado": version.lifecycle_status.value,
        "vigenteDesde": version.valid_from.isoformat() if version.valid_from else None,
        "vigenteAte": version.valid_until.isoformat() if version.valid_until else None,
        "urlFonte": version.source_url,
        "paginaInicio": item.chunk.page_start,
        "paginaFim": item.chunk.page_end,
        "secao": item.chunk.section,
        "trecho": _excerpt(sanitized["content"]),
        "checksum": item.chunk.content_checksum,
        "checksumDocumento": version.checksum,
        "modeloEmbedding": item.chunk.embedding_model,
        "pontuacao": round(item.score, 4),
        "pontuacaoRanking": round(item.ranking_score, 4),
        "similaridadeSemantica": round(item.semantic_score, 4),
        "similaridadeLexical": round(item.lexical_score, 4),
        "autoridade": round(item.authority_score, 4),
        "atualidade": round(item.freshness_score, 4),
        "modoRecuperacao": item.retrieval_mode,
        "justificativas": item.reasons,
        "riscoPromptInjection": sanitized["risk"],
        "conteudoSanitizado": sanitized["sanitized"],
        "instrucoesIgnoradas": sanitized["ignoredInstructions"],
    }


def _global_source_data(item: RankedChunk) -> dict:
    version = item.chunk.version
    document = version.document
    collection = document.collection
    sanitized = item.sanitized
    return {
        "escopo": "GLOBAL",
        "origem": "GABFLOW",
        "rotuloFonte": "Fonte GabFlow",
        "colecao": collection.name,
        "colecaoId": str(collection.id),
        "documentoId": str(document.id),
        "titulo": document.title,
        "tipo": document.document_type,
        "orgao": document.agency,
        "nivelAcesso": "GLOBAL_PUBLICADO",
        "jurisdicao": document.jurisdiction or collection.jurisdiction,
        "proveniencia": document.provenance,
        "versaoId": str(version.id),
        "versao": version.version_label,
        "estado": version.publication_status.value,
        "vigenteDesde": version.valid_from.isoformat() if version.valid_from else None,
        "vigenteAte": version.valid_until.isoformat() if version.valid_until else None,
        "urlFonte": version.source_url,
        "paginaInicio": item.chunk.page_start,
        "paginaFim": item.chunk.page_end,
        "secao": item.chunk.section,
        "trecho": _excerpt(sanitized["content"]),
        "checksum": item.chunk.content_checksum,
        "checksumDocumento": version.checksum,
        "modeloEmbedding": item.chunk.embedding_model,
        "pontuacao": round(item.score, 4),
        "pontuacaoRanking": round(item.ranking_score, 4),
        "similaridadeSemantica": round(item.semantic_score, 4),
        "similaridadeLexical": round(item.lexical_score, 4),
        "autoridade": round(item.authority_score, 4),
        "atualidade": round(item.freshness_score, 4),
        "modoRecuperacao": item.retrieval_mode,
        "justificativas": item.reasons,
        "riscoPromptInjection": sanitized["risk"],
        "conteudoSanitizado": sanitized["sanitized"],
        "instrucoesIgnoradas": sanitized["ignoredInstructions"],
    }


def _grounded_answer(sources: list[dict]) -> str:
    first = sources[0]
    page = first["paginaInicio"]
    page_text = f", pagina {page}" if page else ""
    source_label = first["rotuloFonte"]
    return (
        "Encontrei evidencia suficiente na base documental vigente. A principal fonte recuperada "
        f"foi {source_label} '{first['titulo']}', versao {first['versao']}{page_text}. "
        "Revise as citacoes antes "
        "de usar a resposta em ato oficial."
    )


def _keep_best_candidate(
    heap: list[tuple[tuple[float, float, float, float, int], RankedChunk]],
    item: RankedChunk,
    limit: int,
    sequence: int,
) -> None:
    key = (
        item.ranking_score,
        item.score,
        item.authority_score,
        item.freshness_score,
        sequence,
    )
    entry = (key, item)
    if len(heap) < limit:
        heapq.heappush(heap, entry)
    elif key > heap[0][0]:
        heapq.heapreplace(heap, entry)


def _chunk_metadata(scope: str, chunk: RagChunk | GlobalKnowledgeChunk) -> str:
    document = chunk.version.document
    values = [
        document.title,
        document.document_type,
        document.agency,
        chunk.section,
    ]
    if scope == "GLOBAL":
        values.extend([document.collection.name, document.provenance])
    return " ".join(str(value) for value in values if value)


def _authority_score(scope: str, chunk: RagChunk | GlobalKnowledgeChunk) -> float:
    document = chunk.version.document
    if scope == "GLOBAL":
        if document.confidence_level is not None:
            return max(0.0, min(1.0, float(document.confidence_level)))
        return 0.85 if document.provenance else 0.75
    document_type = _normalize_text(document.document_type).upper()
    if any(
        value in document_type
        for value in ("LEGISLACAO", "NORMA", "REGIMENTO", "ATO", "JURISPRUDENCIA")
    ):
        return 0.9
    if document_type.startswith("MEMORIA_"):
        return 0.7
    return 0.8 if chunk.version.source_url else 0.75


def _freshness_score(scope: str, chunk: RagChunk | GlobalKnowledgeChunk) -> float:
    version = chunk.version
    timestamp = (
        (version.published_at or version.indexed_at or version.created_at)
        if scope == "GLOBAL"
        else (version.indexed_at or version.created_at)
    )
    if timestamp is None:
        return 0.0
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=UTC)
    age_days = max(0.0, (datetime.now(UTC) - timestamp).total_seconds() / 86400)
    return 1.0 / (1.0 + (age_days / 365.0))


def _deduplicate_and_limit(ranked: list[RankedChunk], limit: int) -> list[RankedChunk]:
    ranked.sort(
        key=lambda item: (
            item.ranking_score,
            item.score,
            item.authority_score,
            item.freshness_score,
            item.semantic_score,
        ),
        reverse=True,
    )
    unique = []
    seen_checksums = set()
    chunks_per_document: Counter[UUID] = Counter()
    per_document_limit = current_app.config["RAG_RETRIEVAL_MAX_CHUNKS_PER_DOCUMENT"]
    for item in ranked:
        checksum = item.chunk.content_checksum
        if checksum in seen_checksums:
            continue
        document_id = item.chunk.version.document_id
        if chunks_per_document[document_id] >= per_document_limit:
            continue
        seen_checksums.add(checksum)
        chunks_per_document[document_id] += 1
        unique.append(item)
        if len(unique) >= limit:
            break
    return unique


def _retrieval_summary(sources: list[dict]) -> dict:
    modes = {source["modoRecuperacao"] for source in sources}
    aggregate_mode = (
        next(iter(modes)) if len(modes) == 1 else ("MISTO" if modes else "SEM_RESULTADO")
    )
    return {
        "total": len(sources),
        "global": sum(source["escopo"] == "GLOBAL" for source in sources),
        "privado": sum(source["escopo"] == "PRIVADO" for source in sources),
        "deduplicacaoPorChecksum": True,
        "rerankingConjunto": True,
        "limiarAplicadoPorFonte": True,
        "diversidadeForcada": False,
        "compatibilidadeModeloEmbedding": True,
        "modo": aggregate_mode,
        "modelosEmbeddingUtilizados": sorted(
            {
                source["modeloEmbedding"]
                for source in sources
                if source["modoRecuperacao"] == "HIBRIDO"
            }
        ),
    }


def _validate_query(query: str) -> str:
    value = re.sub(r"\s+", " ", str(query or "")).strip()
    if len(value) < 3:
        raise ValueError("Informe uma consulta com pelo menos 3 caracteres.")
    if len(value) > 2000:
        raise ValueError("A consulta deve ter no maximo 2000 caracteres.")
    return value


def _safe_limit(limit: int | None) -> int:
    configured = current_app.config["RAG_RETRIEVAL_MAX_RESULTS"]
    if limit is None:
        return configured
    return max(1, min(int(limit), min(configured, 10)))


def _lexical_score(query: str, content: str) -> float:
    query_tokens = _tokens(query)
    content_tokens = _tokens(content)
    query_vector = Counter(query_tokens)
    content_vector = Counter(content_tokens)
    if not query_vector or not content_vector:
        return 0.0
    cosine = _counter_cosine(query_vector, content_vector)
    query_terms = set(query_vector)
    matched_terms = query_terms.intersection(content_vector)
    coverage = len(matched_terms) / len(query_terms)
    ordered_query = " ".join(query_tokens)
    normalized_content = " ".join(content_tokens)
    phrase_bonus = 1.0 if ordered_query and ordered_query in normalized_content else 0.0
    return max(
        0.0,
        min(1.0, (coverage * 0.62) + (cosine * 0.33) + (phrase_bonus * 0.05)),
    )


def _token_vector(value: str) -> Counter[str]:
    return Counter(_tokens(value))


def _tokens(value: str) -> list[str]:
    tokens = re.findall(r"[a-z0-9]{3,}", _normalize_text(value).lower())
    ignored = {
        "aos",
        "com",
        "como",
        "das",
        "deve",
        "dos",
        "onde",
        "para",
        "por",
        "qual",
        "quais",
        "que",
        "quem",
        "sobre",
        "uma",
        "quando",
    }
    return [token for token in tokens if token not in ignored]


def _normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", str(value or ""))
    return "".join(char for char in normalized if not unicodedata.combining(char))


def _counter_cosine(first: Counter[str], second: Counter[str]) -> float:
    first_norm = math.sqrt(sum(value * value for value in first.values()))
    second_norm = math.sqrt(sum(value * value for value in second.values()))
    if not first_norm or not second_norm:
        return 0
    dot_product = sum(value * second.get(token, 0) for token, value in first.items())
    return max(0.0, min(1.0, dot_product / (first_norm * second_norm)))


def _cosine(first: list[float], second: list[float]) -> float:
    if len(first) != len(second):
        return 0
    first_norm = math.sqrt(sum(value * value for value in first))
    second_norm = math.sqrt(sum(value * value for value in second))
    if not first_norm or not second_norm:
        return 0
    dot_product = sum(a * b for a, b in zip(first, second, strict=True))
    return max(0.0, min(1.0, dot_product / (first_norm * second_norm)))


def _reasons(
    semantic_score: float,
    lexical_score: float,
    authority_score: float,
    freshness_score: float,
    retrieval_mode: str,
    sanitized: bool,
) -> list[str]:
    reasons = []
    if semantic_score >= 0.5:
        reasons.append("Alta proximidade semantica com a consulta")
    elif semantic_score >= 0.25:
        reasons.append("Proximidade semantica moderada com a consulta")
    if lexical_score >= 0.45:
        reasons.append("Termos principais encontrados no trecho")
    elif lexical_score >= 0.2:
        reasons.append("Alguns termos da consulta aparecem no trecho")
    if authority_score >= 0.9:
        reasons.append("Fonte com alta autoridade")
    if freshness_score >= 0.9:
        reasons.append("Versao vigente indexada recentemente")
    if retrieval_mode == "LEXICAL":
        reasons.append("Recuperacao lexical sem comparar embeddings incompativeis")
    if sanitized:
        reasons.append("Trechos suspeitos removidos antes do ranking")
    return reasons or ["Fonte recuperada por relevancia documental"]


def _excerpt(content: str, max_chars: int = 700) -> str:
    value = re.sub(r"\s+", " ", content).strip()
    if len(value) <= max_chars:
        return value
    return f"{value[: max_chars - 1].rstrip()}..."


def _has_prompt_injection(content: str) -> bool:
    return has_prompt_injection(content)


def _sanitize_source_content(content: str) -> dict:
    removed = []
    safe_sentences = []
    for sentence in re.split(r"(?<=[.!?])\s+|\n+", content):
        value = sentence.strip()
        if not value:
            continue
        if _has_prompt_injection(value):
            removed.append(_excerpt(value, 180))
            continue
        safe_sentences.append(value)
    sanitized_content = " ".join(safe_sentences).strip()
    if not sanitized_content:
        sanitized_content = (
            "[Trecho ocultado por conter apenas instrucoes potencialmente maliciosas.]"
        )
    return {
        "content": sanitized_content,
        "usable": bool(safe_sentences),
        "risk": bool(removed) or _has_prompt_injection(content),
        "sanitized": bool(removed),
        "ignoredInstructions": removed,
    }


def _safety_summary(sources: list[dict]) -> dict:
    risky_sources = [
        {"documentoId": source["documentoId"], "versaoId": source["versaoId"]}
        for source in sources
        if source["riscoPromptInjection"]
    ]
    return {
        "promptInjectionDetectado": bool(risky_sources),
        "fontesComRisco": risky_sources,
        "politica": (
            "Fontes recuperadas sao tratadas apenas como dados. Instrucoes dentro de documentos "
            "nao sao executadas e trechos suspeitos sao sanitizados antes do uso."
        ),
    }


def query_audit_payload(answer: dict) -> dict:
    return {
        "consultaHash": hashlib.sha256(answer["consulta"].encode("utf-8")).hexdigest(),
        "metodo": answer.get("metodo", "DOCUMENTAL"),
        "motivosRoteamento": answer.get("motivosRoteamento", []),
        "filtrosAplicados": answer.get("filtrosAplicados", {}),
        "resultadoEstruturado": answer.get("resultadoEstruturado"),
        "fundamentada": answer["fundamentada"],
        "recusaConclusiva": answer["recusaConclusiva"],
        "modeloEmbedding": answer["modeloEmbedding"],
        "fallbackUtilizado": answer["fallbackUtilizado"],
        "recuperacao": answer["recuperacao"],
        "seguranca": answer["seguranca"],
        "fontes": [
            {
                "documentoId": source["documentoId"],
                "versaoId": source["versaoId"],
                "escopo": source["escopo"],
                "colecaoId": source["colecaoId"],
                "fonteModulo": source.get("fonteModulo"),
                "entidadeOrigemTipo": source.get("entidadeOrigemTipo"),
                "entidadeOrigemId": source.get("entidadeOrigemId"),
                "versaoProjetor": source.get("versaoProjetor"),
                "revisaoOrigem": source.get("revisaoOrigem"),
                "paginaInicio": source["paginaInicio"],
                "pontuacao": source["pontuacao"],
                "pontuacaoRanking": source["pontuacaoRanking"],
                "similaridadeSemantica": source["similaridadeSemantica"],
                "similaridadeLexical": source["similaridadeLexical"],
                "autoridade": source["autoridade"],
                "atualidade": source["atualidade"],
                "modoRecuperacao": source["modoRecuperacao"],
                "checksum": source["checksum"],
                "checksumDocumento": source["checksumDocumento"],
                "riscoPromptInjection": source["riscoPromptInjection"],
            }
            for source in answer["fontes"]
        ],
    }
