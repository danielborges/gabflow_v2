import hashlib
import heapq
import math
import re
import time
import unicodedata
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, replace
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
from app.rag.content_security import (
    ContentSecurityAction,
    ContentSecurityStatus,
    ContentSecuritySurface,
    assess_content_security,
)
from app.rag.distribution import global_versions_for_tenant
from app.rag.grounded_generation import (
    GroundingSource,
    generate_grounded_answer,
)
from app.rag.hybrid_search import HybridCandidate, postgres_hybrid_candidates
from app.rag.neural_reranker import NeuralCandidate, run_neural_rerank
from app.rag.service import rag_embedding_provider

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
    base_ranking_score: float
    semantic_score: float
    lexical_score: float
    authority_score: float
    freshness_score: float
    retrieval_mode: str
    candidate_channels: tuple[str, ...]
    fusion_score: float
    database_lexical_score: float | None
    sanitized: dict
    reasons: list[str]
    neural_rerank_score: float | None = None
    neural_rerank_model: str | None = None
    neural_rerank_prompt_version: str | None = None
    neural_rerank_reason: str | None = None
    neural_rerank_applied: bool = False
    neural_rerank_fallback: bool = False
    neural_rerank_error: str | None = None
    neural_rerank_candidate_count: int = 0


def answer_query(
    tenant_id: UUID,
    role: str | None,
    query: str,
    limit: int | None = None,
    *,
    rerank_artifact=None,
    applied_artifacts: list | None = None,
    retrieval_plan=None,
    quality_profile: dict | None = None,
) -> dict:
    started = time.perf_counter()
    normalized_query = _validate_query(query)
    query_security = assess_content_security(
        normalized_query,
        surface=ContentSecuritySurface.USER_QUERY,
    )
    max_results = _safe_limit(limit)
    (
        ranked,
        provider_model,
        fallback_used,
        fallback_error,
        neural_rerank,
        candidate_mechanism,
    ) = retrieve_chunks(
        tenant_id,
        role,
        normalized_query,
        max_results,
        rerank_artifact=rerank_artifact,
        applied_artifacts=applied_artifacts,
        retrieval_plan=retrieval_plan,
        quality_profile=quality_profile,
    )
    retrieval_ms = _duration_ms(started)
    min_evidence = _profile_float(
        quality_profile,
        "minEvidenceScore",
        "RAG_RETRIEVAL_MIN_EVIDENCE_SCORE",
    )
    grounded = bool(ranked)
    sources = [_source_data(item) for item in ranked]
    safety_flags = _safety_summary(sources)
    safety_flags["consulta"] = query_security.as_dict()
    generation_sources = tuple(
        GroundingSource(
            id=str(item.chunk.id),
            title=str(item.chunk.version.document.title),
            document_type=str(item.chunk.version.document.document_type),
            section=item.chunk.section,
            content=_focused_rerank_excerpt(
                item.sanitized["content"],
                (normalized_query,),
                max(300, current_app.config["RAG_ANSWER_SOURCE_CHARS"]),
            ),
        )
        for item in ranked[: max(1, current_app.config["RAG_ANSWER_MAX_SOURCES"])]
    )
    generation = generate_grounded_answer(
        normalized_query,
        generation_sources,
        quality_profile=quality_profile,
    )
    generation_summary = _generation_summary(generation)
    total_ms = _duration_ms(started)
    budget_ms = max(
        1000,
        int(current_app.config["RAG_QUERY_LATENCY_BUDGET_MS"]),
    )
    latency = {
        "recuperacaoMs": retrieval_ms,
        **(generation.timings or {}),
        "totalMs": total_ms,
        "orcamentoMs": budget_ms,
        "orcamentoExcedido": total_ms > budget_ms,
    }
    citations = _citation_data(generation, sources)

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
            "geracao": generation_summary,
            "citacoes": [],
            "fontes": sources,
            "escoposConsultados": ["GLOBAL", "PRIVADO"],
            "recuperacao": _retrieval_summary(
                sources,
                neural_rerank,
                candidate_mechanism,
                retrieval_plan,
            ),
            "latenciaEtapas": latency,
        }

    if current_app.config["RAG_ANSWER_GENERATION_ENABLED"] and not generation.applied:
        fallback_used = fallback_used or generation.fallback_used
        fallback_error = "; ".join(
            error
            for error in (fallback_error, generation.fallback_error)
            if error
        ) or None
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
            "geracao": generation_summary,
            "citacoes": [],
            "fontes": sources,
            "escoposConsultados": ["GLOBAL", "PRIVADO"],
            "recuperacao": _retrieval_summary(
                sources,
                neural_rerank,
                candidate_mechanism,
                retrieval_plan,
            ),
            "latenciaEtapas": latency,
        }

    return {
        "consulta": normalized_query,
        "resposta": generation.answer or _grounded_answer(sources),
        "fundamentada": True,
        "recusaConclusiva": False,
        "conteudoTratadoComoDado": True,
        "limiarEvidencia": min_evidence,
        "modeloEmbedding": provider_model,
        "fallbackUtilizado": fallback_used,
        "erroFallback": fallback_error,
        "seguranca": safety_flags,
        "geracao": generation_summary,
        "citacoes": citations,
        "fontes": sources,
        "escoposConsultados": ["GLOBAL", "PRIVADO"],
        "recuperacao": _retrieval_summary(
            sources,
            neural_rerank,
            candidate_mechanism,
            retrieval_plan,
        ),
        "latenciaEtapas": latency,
    }


def retrieve_chunks(
    tenant_id: UUID,
    role: str | None,
    query: str,
    limit: int,
    *,
    rerank_artifact=None,
    applied_artifacts: list | None = None,
    retrieval_plan=None,
    quality_profile: dict | None = None,
) -> tuple[list[RankedChunk], str, bool, str | None, dict, str]:
    fallback_used = False
    fallback_error = None
    search_queries = (
        retrieval_plan.search_queries if retrieval_plan is not None else (query,)
    )
    query_vectors = []
    try:
        provider = rag_embedding_provider()
        query_vectors = provider.embeddings(list(search_queries))
    except EmbeddingProviderError as error:
        current_app.logger.warning(
            "Falha no embedding RAG; usando busca lexical sem comparar modelos: %s",
            error,
        )
        provider = None
        fallback_used = True
        fallback_error = str(error)

    provider_model = provider.model if provider is not None else "gabflow-lexical-retrieval-v2"
    pool_limit = max(limit, current_app.config["RAG_RETRIEVAL_CANDIDATE_LIMIT"])
    database_candidates = postgres_hybrid_candidates(
        tenant_id,
        role,
        search_queries[0],
        query_vectors[0] if query_vectors else None,
        provider.model if provider is not None else None,
        limit=pool_limit,
        filters=(
            retrieval_plan.retrieval_filters
            if retrieval_plan is not None
            else None
        ),
    )
    if database_candidates is not None and len(search_queries) > 1:
        database_candidates = _expanded_database_candidates(
            tenant_id,
            role,
            search_queries,
            query_vectors,
            provider.model if provider is not None else None,
            pool_limit,
            retrieval_plan.retrieval_filters,
            first=database_candidates,
        )
    candidates = (
        database_candidates
        if database_candidates is not None
        else list(_candidate_chunks(tenant_id, role))
    )
    candidate_mechanism = (
        "POSTGRES_FTS_PGVECTOR"
        if database_candidates is not None
        else "LOCAL_SCAN"
    )
    if not candidates:
        return (
            [],
            provider_model,
            fallback_used,
            fallback_error,
            _empty_neural_rerank_summary(quality_profile),
            candidate_mechanism,
        )

    threshold = max(
        _profile_float(
            quality_profile,
            "retrievalScoreThreshold",
            "RAG_RETRIEVAL_SCORE_THRESHOLD",
        ),
        _profile_float(
            quality_profile,
            "minEvidenceScore",
            "RAG_RETRIEVAL_MIN_EVIDENCE_SCORE",
        ),
    )
    per_document_limit = current_app.config["RAG_RETRIEVAL_MAX_CHUNKS_PER_DOCUMENT"]
    query_hash = hashlib.sha256(query.encode("utf-8")).hexdigest()
    rerank_entries = (
        {
            (
                item.get("queryHash"),
                item.get("escopo"),
                item.get("documentoId"),
                item.get("versaoId"),
            ): float(item.get("ajuste") or 0)
            for item in rerank_artifact.payload.get("entradas", [])
            if item.get("queryHash") == query_hash
        }
        if rerank_artifact is not None
        else {}
    )
    rerank_applied = False
    document_heaps: dict[
        UUID, list[tuple[tuple[float, float, float, float, int], RankedChunk]]
    ] = {}
    sequence = 0
    for candidate in candidates:
        scope = candidate.scope
        chunk = candidate.chunk
        if retrieval_plan is not None and not _matches_documentary_filters(
            scope,
            chunk,
            retrieval_plan.retrieval_filters,
        ):
            continue
        sanitized = _sanitize_source_content(chunk.content)
        if not sanitized["usable"]:
            continue
        metadata = _chunk_metadata(scope, chunk)
        content_lexical = max(
            _lexical_score(search_query, sanitized["content"])
            for search_query in search_queries
        )
        metadata_lexical = max(
            _lexical_score(search_query, metadata)
            for search_query in search_queries
        )
        metadata_weight = (
            0.9
            if retrieval_plan is not None and retrieval_plan.references
            else 0.5
        )
        lexical_score = max(
            content_lexical,
            (content_lexical * 0.82) + (metadata_lexical * 0.18),
            metadata_lexical * metadata_weight,
        )
        compatible_vectors = [
            vector
            for vector in query_vectors
            if (
                vector
                and provider is not None
                and chunk.embedding_model == provider.model
                and len(vector) == len(chunk.embedding)
            )
        ]
        semantic_compatible = bool(
            compatible_vectors
            and provider is not None
            and not sanitized["sanitized"]
        )
        semantic_score = (
            (
                candidate.database_semantic_score
                if candidate.database_semantic_score is not None
                else max(
                    _cosine(vector, chunk.embedding)
                    for vector in compatible_vectors
                )
            )
            if semantic_compatible
            else 0.0
        )
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
        feedback_adjustment = rerank_entries.get(
            (
                query_hash,
                scope,
                str(chunk.version.document_id),
                str(chunk.version.id),
            ),
            0.0,
        )
        rerank_applied = rerank_applied or bool(feedback_adjustment)
        ranking_score = (
            score
            + (authority_score * current_app.config["RAG_RETRIEVAL_AUTHORITY_RERANK_WEIGHT"])
            + (freshness_score * current_app.config["RAG_RETRIEVAL_FRESHNESS_RERANK_WEIGHT"])
            + feedback_adjustment
        )
        ranked_item = RankedChunk(
            chunk=chunk,
            scope=scope,
            score=score,
            ranking_score=ranking_score,
            base_ranking_score=ranking_score,
            semantic_score=semantic_score,
            lexical_score=lexical_score,
            authority_score=authority_score,
            freshness_score=freshness_score,
            retrieval_mode=retrieval_mode,
            candidate_channels=candidate.channels,
            fusion_score=candidate.fusion_score,
            database_lexical_score=candidate.database_lexical_score,
            sanitized=sanitized,
            reasons=_reasons(
                semantic_score,
                lexical_score,
                authority_score,
                freshness_score,
                retrieval_mode,
                sanitized["sanitized"],
            )
            + [f"CANDIDATO_{channel}" for channel in candidate.channels]
            + (
                [f"AJUSTE_FEEDBACK:{feedback_adjustment:+.6f}"]
                if feedback_adjustment
                else []
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
    ranked, neural_fallback, neural_error, neural_rerank = _apply_neural_reranking(
        query,
        ranked,
        context_queries=search_queries,
        quality_profile=quality_profile,
    )
    if neural_fallback:
        fallback_used = True
        fallback_error = "; ".join(
            error for error in (fallback_error, neural_error) if error
        )
    ranked = _deduplicate_and_limit(ranked, limit)
    if rerank_applied and applied_artifacts is not None:
        descriptor = {
            "id": str(rerank_artifact.id),
            "tipo": rerank_artifact.artifact_type.value,
            "versao": rerank_artifact.version,
            "modoAtivacao": rerank_artifact.activation_mode,
            "percentualCanario": rerank_artifact.rollout_percentage,
        }
        if descriptor not in applied_artifacts:
            applied_artifacts.append(descriptor)
    return (
        ranked,
        provider_model,
        fallback_used,
        fallback_error,
        neural_rerank,
        candidate_mechanism,
    )


def _expanded_database_candidates(
    tenant_id: UUID,
    role: str | None,
    search_queries: tuple[str, ...],
    query_vectors: list[list[float]],
    embedding_model: str | None,
    limit: int,
    filters: dict,
    *,
    first: list[HybridCandidate],
) -> list[HybridCandidate]:
    result_sets = [first]
    for position, search_query in enumerate(search_queries[1:], start=1):
        vector = query_vectors[position] if position < len(query_vectors) else None
        result = postgres_hybrid_candidates(
            tenant_id,
            role,
            search_query,
            vector,
            embedding_model,
            limit=limit,
            filters=filters,
        )
        if result is not None:
            result_sets.append(result)
    rrf_k = max(1, int(current_app.config["RAG_HYBRID_RRF_K"]))
    merged = {}
    for query_position, result in enumerate(result_sets):
        query_channel = (
            "CONSULTA_ORIGINAL" if query_position == 0 else "CONSULTA_EXPANDIDA"
        )
        for rank, candidate in enumerate(result, start=1):
            key = (candidate.scope, candidate.chunk.id)
            values = merged.setdefault(
                key,
                {
                    "candidate": candidate,
                    "fusion": 0.0,
                    "lexical": None,
                    "semantic": None,
                    "channels": set(),
                },
            )
            values["fusion"] += 1.0 / (rrf_k + rank)
            values["channels"].update(candidate.channels)
            values["channels"].add(query_channel)
            if candidate.database_lexical_score is not None:
                values["lexical"] = max(
                    values["lexical"] or 0.0,
                    candidate.database_lexical_score,
                )
            if candidate.database_semantic_score is not None:
                values["semantic"] = max(
                    values["semantic"] or 0.0,
                    candidate.database_semantic_score,
                )
    ordered = sorted(
        merged.values(),
        key=lambda values: (
            values["fusion"],
            values["semantic"] or 0.0,
            values["lexical"] or 0.0,
            str(values["candidate"].chunk.id),
        ),
        reverse=True,
    )
    return [
        HybridCandidate(
            scope=values["candidate"].scope,
            chunk=values["candidate"].chunk,
            database_lexical_score=values["lexical"],
            database_semantic_score=values["semantic"],
            fusion_score=values["fusion"],
            channels=tuple(
                channel
                for channel in (
                    "FTS",
                    "PGVECTOR",
                    "CONSULTA_ORIGINAL",
                    "CONSULTA_EXPANDIDA",
                )
                if channel in values["channels"]
            ),
        )
        for values in ordered[:limit]
    ]


def _matches_documentary_filters(
    scope: str,
    chunk: RagChunk | GlobalKnowledgeChunk,
    filters: dict,
) -> bool:
    if not filters:
        return True
    document = chunk.version.document
    document_type = filters.get("tipoDocumento")
    if document_type:
        expected = _normalize_text(str(document_type).replace("_", " "))
        actual = _normalize_text(
            " ".join(
                str(value)
                for value in (
                    document.document_type,
                    document.title,
                    chunk.content,
                )
                if value
            ).replace("_", " ")
        )
        type_fragment = expected[:5] if len(expected) > 5 else expected
        if type_fragment not in actual:
            return False
    agency = filters.get("orgao")
    if agency and _normalize_text(str(agency)) not in _normalize_text(
        str(document.agency or "")
    ):
        return False
    theme = filters.get("temaBusca")
    if theme:
        searchable = _normalize_text(
            " ".join(
                str(value)
                for value in (
                    document.title,
                    document.document_type,
                    document.agency,
                    chunk.section,
                    chunk.content,
                )
                if value
            )
        )
        theme_tokens = {
            token
            for token in _tokens(str(theme))
            if len(token) > 3
        }
        if theme_tokens and not theme_tokens.intersection(_tokens(searchable)):
            return False
    jurisdiction = filters.get("jurisdicao")
    if jurisdiction and scope == "GLOBAL":
        if _normalize_text(str(jurisdiction)) not in _normalize_text(
            str(document.jurisdiction or {})
        ):
            return False
    start = filters.get("inicio")
    end = filters.get("fim")
    valid_from = chunk.version.valid_from
    valid_until = chunk.version.valid_until
    if start and valid_until is not None:
        if valid_until < datetime.fromisoformat(str(start)).date():
            return False
    if end and valid_from is not None:
        if valid_from > datetime.fromisoformat(str(end)).date():
            return False
    return True


def _candidate_chunks(
    tenant_id: UUID, role: str | None
) -> Iterable[HybridCandidate]:
    for chunk in _private_candidate_chunks(tenant_id, role):
        yield HybridCandidate(
            scope="PRIVADO",
            chunk=chunk,
            database_lexical_score=None,
            database_semantic_score=None,
            fusion_score=0.0,
            channels=("LOCAL_SCAN",),
        )
    for chunk in _global_candidate_chunks(tenant_id):
        yield HybridCandidate(
            scope="GLOBAL",
            chunk=chunk,
            database_lexical_score=None,
            database_semantic_score=None,
            fusion_score=0.0,
            channels=("LOCAL_SCAN",),
        )


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
            RagDocumentVersion.security_status == ContentSecurityStatus.CLEAN,
            RagDocumentVersion.security_action == ContentSecurityAction.ALLOW,
            RagDocumentVersion.malware_scan_status == "CLEAN",
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
        "chunkId": str(item.chunk.id),
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
        "pontuacaoRankingBase": round(item.base_ranking_score, 4),
        "pontuacaoRerankerNeural": (
            round(item.neural_rerank_score, 4)
            if item.neural_rerank_score is not None
            else None
        ),
        "modeloRerankerNeural": item.neural_rerank_model,
        "versaoPromptRerankerNeural": item.neural_rerank_prompt_version,
        "justificativaRerankerNeural": item.neural_rerank_reason,
        "rerankingNeuralAplicado": item.neural_rerank_applied,
        "fallbackRerankerNeural": item.neural_rerank_fallback,
        "erroFallbackRerankerNeural": item.neural_rerank_error,
        "candidatosRerankerNeural": item.neural_rerank_candidate_count,
        "similaridadeSemantica": round(item.semantic_score, 4),
        "similaridadeLexical": round(item.lexical_score, 4),
        "autoridade": round(item.authority_score, 4),
        "atualidade": round(item.freshness_score, 4),
        "modoRecuperacao": item.retrieval_mode,
        "canaisCandidatura": list(item.candidate_channels),
        "pontuacaoFusao": round(item.fusion_score, 6),
        "rankingTextualBanco": (
            round(item.database_lexical_score, 6)
            if item.database_lexical_score is not None
            else None
        ),
        "justificativas": item.reasons,
        "riscoPromptInjection": sanitized["risk"],
        "conteudoSanitizado": sanitized["sanitized"],
        "instrucoesIgnoradas": sanitized["ignoredInstructions"],
        "segurancaConteudo": sanitized["securityDecision"],
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
        "chunkId": str(item.chunk.id),
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
        "pontuacaoRankingBase": round(item.base_ranking_score, 4),
        "pontuacaoRerankerNeural": (
            round(item.neural_rerank_score, 4)
            if item.neural_rerank_score is not None
            else None
        ),
        "modeloRerankerNeural": item.neural_rerank_model,
        "versaoPromptRerankerNeural": item.neural_rerank_prompt_version,
        "justificativaRerankerNeural": item.neural_rerank_reason,
        "rerankingNeuralAplicado": item.neural_rerank_applied,
        "fallbackRerankerNeural": item.neural_rerank_fallback,
        "erroFallbackRerankerNeural": item.neural_rerank_error,
        "candidatosRerankerNeural": item.neural_rerank_candidate_count,
        "similaridadeSemantica": round(item.semantic_score, 4),
        "similaridadeLexical": round(item.lexical_score, 4),
        "autoridade": round(item.authority_score, 4),
        "atualidade": round(item.freshness_score, 4),
        "modoRecuperacao": item.retrieval_mode,
        "canaisCandidatura": list(item.candidate_channels),
        "pontuacaoFusao": round(item.fusion_score, 6),
        "rankingTextualBanco": (
            round(item.database_lexical_score, 6)
            if item.database_lexical_score is not None
            else None
        ),
        "justificativas": item.reasons,
        "riscoPromptInjection": sanitized["risk"],
        "conteudoSanitizado": sanitized["sanitized"],
        "instrucoesIgnoradas": sanitized["ignoredInstructions"],
        "segurancaConteudo": sanitized["securityDecision"],
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


def _generation_summary(generation) -> dict:
    return {
        "habilitada": current_app.config["RAG_ANSWER_GENERATION_ENABLED"],
        "aplicada": generation.applied,
        "modelo": generation.model,
        "versaoPrompt": generation.prompt_version,
        "fallbackUtilizado": generation.fallback_used,
        "erroFallback": generation.fallback_error,
        "afirmacoes": len(generation.claims),
        "citacoes": len(generation.citation_numbers),
        "validacaoCruzada": generation.validation,
        "latencia": generation.timings or {},
    }


def _citation_data(generation, sources: list[dict]) -> list[dict]:
    source_map = {source["chunkId"]: source for source in sources}
    citations = []
    for source_id, number in sorted(
        generation.citation_numbers.items(),
        key=lambda item: item[1],
    ):
        source = source_map.get(source_id)
        if source is None:
            continue
        claims = [
            position
            for position, claim in enumerate(generation.claims, start=1)
            if source_id in claim.source_ids
        ]
        citations.append(
            {
                "numero": number,
                "chunkId": source_id,
                "documentoId": source["documentoId"],
                "versaoId": source["versaoId"],
                "escopo": source["escopo"],
                "titulo": source["titulo"],
                "paginaInicio": source["paginaInicio"],
                "paginaFim": source["paginaFim"],
                "afirmacoes": claims,
            }
        )
    return citations


def _keep_best_candidate(
    heap: list[tuple[tuple[float, float, float, float, str], RankedChunk]],
    item: RankedChunk,
    limit: int,
    _sequence: int,
) -> None:
    key = (
        item.ranking_score,
        item.score,
        item.authority_score,
        item.freshness_score,
        str(item.chunk.id),
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


def _apply_neural_reranking(
    query: str,
    ranked: list[RankedChunk],
    *,
    context_queries: tuple[str, ...] | None = None,
    quality_profile: dict | None = None,
) -> tuple[list[RankedChunk], bool, str | None, dict]:
    ranked.sort(
        key=lambda item: (
            item.ranking_score,
            item.score,
            item.authority_score,
            item.freshness_score,
            str(item.chunk.id),
        ),
        reverse=True,
    )
    adaptive_reason = _adaptive_rerank_skip_reason(ranked)
    if adaptive_reason is not None:
        top_score = ranked[0].ranking_score if ranked else 0.0
        runner_up = ranked[1].ranking_score if len(ranked) > 1 else 0.0
        return ranked, False, None, {
            "habilitado": True,
            "aplicado": False,
            "modelo": None,
            "versaoPrompt": None,
            "peso": current_app.config["RAG_NEURAL_RERANK_WEIGHT"],
            "limiarRelevancia": _profile_float(
                quality_profile,
                "neuralMinScore",
                "RAG_NEURAL_RERANK_MIN_SCORE",
            ),
            "candidatosAvaliados": 0,
            "candidatosAceitos": len(ranked),
            "candidatosRejeitados": 0,
            "rejeicoes": [],
            "fallbackUtilizado": False,
            "erroFallback": None,
            "skipAdaptativo": True,
            "motivoSkip": adaptive_reason,
            "pontuacaoLider": round(top_score, 6),
            "margemLideranca": round(top_score - runner_up, 6),
            "latenciaMs": 0,
        }
    candidate_limit = max(
        1,
        current_app.config["RAG_NEURAL_RERANK_CANDIDATE_LIMIT"],
    )
    content_limit = max(100, current_app.config["RAG_NEURAL_RERANK_CONTENT_CHARS"])
    targets = ranked[:candidate_limit]
    candidates = tuple(
        NeuralCandidate(
            id=str(item.chunk.id),
            title=str(item.chunk.version.document.title),
            document_type=str(item.chunk.version.document.document_type),
            section=item.chunk.section,
            content=_focused_rerank_excerpt(
                item.sanitized["content"],
                context_queries or (query,),
                content_limit,
            ),
            base_score=item.base_ranking_score,
        )
        for item in targets
    )
    outcome = run_neural_rerank(query, candidates)
    weight = max(0.0, min(1.0, current_app.config["RAG_NEURAL_RERANK_WEIGHT"]))
    minimum_score = max(
        0.0,
        min(
            1.0,
            _profile_float(
                quality_profile,
                "neuralMinScore",
                "RAG_NEURAL_RERANK_MIN_SCORE",
            ),
        ),
    )
    updated = []
    rejected = []
    for item in ranked:
        judgment = outcome.judgments.get(str(item.chunk.id))
        if judgment is not None:
            ranking_score = (
                (item.base_ranking_score * (1.0 - weight))
                + (judgment.score * weight)
            )
            reranked_item = replace(
                item,
                ranking_score=ranking_score,
                neural_rerank_score=judgment.score,
                neural_rerank_model=outcome.model,
                neural_rerank_prompt_version=outcome.prompt_version,
                neural_rerank_reason=judgment.reason,
                neural_rerank_applied=True,
                neural_rerank_candidate_count=outcome.candidate_count,
                reasons=[
                    *item.reasons,
                    f"RERANK_NEURAL:{judgment.score:.6f}",
                ],
            )
            if judgment.score >= minimum_score:
                updated.append(reranked_item)
            else:
                rejected.append(
                    {
                        "chunkId": str(item.chunk.id),
                        "documentoId": str(item.chunk.version.document_id),
                        "pontuacao": round(judgment.score, 4),
                        "justificativa": judgment.reason,
                    }
                )
            continue
        if outcome.applied:
            # A execução bem-sucedida limita o resultado à janela efetivamente
            # avaliada; candidatos não avaliados não podem substituir os vetados.
            continue
        updated.append(
            replace(
                item,
                neural_rerank_model=outcome.model,
                neural_rerank_prompt_version=outcome.prompt_version,
                neural_rerank_fallback=outcome.fallback_used,
                neural_rerank_error=outcome.fallback_error,
                neural_rerank_candidate_count=outcome.candidate_count,
            )
        )
    accepted_count = len(updated) if outcome.applied else outcome.candidate_count
    summary = {
        "habilitado": current_app.config["RAG_NEURAL_RERANK_ENABLED"],
        "aplicado": outcome.applied,
        "modelo": outcome.model,
        "versaoPrompt": outcome.prompt_version,
        "peso": weight,
        "limiarRelevancia": minimum_score,
        "candidatosAvaliados": outcome.candidate_count,
        "candidatosAceitos": accepted_count,
        "candidatosRejeitados": (
            outcome.candidate_count - accepted_count if outcome.applied else 0
        ),
        "rejeicoes": rejected,
        "fallbackUtilizado": outcome.fallback_used,
        "erroFallback": outcome.fallback_error,
        "skipAdaptativo": False,
        "motivoSkip": None,
        "latenciaMs": outcome.duration_ms,
    }
    return updated, outcome.fallback_used, outcome.fallback_error, summary


def _adaptive_rerank_skip_reason(
    ranked: list[RankedChunk],
) -> str | None:
    if (
        not current_app.config["RAG_NEURAL_RERANK_ENABLED"]
        or not current_app.config["RAG_NEURAL_RERANK_ADAPTIVE_ENABLED"]
        or not ranked
    ):
        return None
    if len(ranked) == 1:
        return "CANDIDATO_UNICO"
    minimum_score = max(
        0.0,
        min(
            1.0,
            float(current_app.config["RAG_NEURAL_RERANK_SKIP_MIN_SCORE"]),
        ),
    )
    minimum_margin = max(
        0.0,
        min(
            1.0,
            float(current_app.config["RAG_NEURAL_RERANK_SKIP_MIN_MARGIN"]),
        ),
    )
    top_score = ranked[0].ranking_score
    margin = top_score - ranked[1].ranking_score
    if top_score >= minimum_score and margin >= minimum_margin:
        return "LIDER_HIBRIDO_INEQUIVOCO"
    return None


def _focused_rerank_excerpt(
    content: str,
    queries: tuple[str, ...],
    maximum: int,
) -> str:
    sentences = [
        value.strip()
        for value in re.split(r"(?<=[.!?;:])\s+|\n+", content)
        if value.strip()
    ]
    if not sentences:
        return content[:maximum]
    ranked = sorted(
        enumerate(sentences),
        key=lambda item: (
            max(_lexical_score(query, item[1]) for query in queries),
            -item[0],
        ),
        reverse=True,
    )
    selected = []
    size = 0
    for position, sentence in ranked:
        remaining = maximum - size
        if remaining <= 0:
            break
        value = sentence[:remaining]
        if value:
            selected.append((position, value))
            size += len(value) + 1
    return " ".join(value for _, value in selected)


def _empty_neural_rerank_summary(
    quality_profile: dict | None = None,
) -> dict:
    return {
        "habilitado": current_app.config["RAG_NEURAL_RERANK_ENABLED"],
        "aplicado": False,
        "modelo": None,
        "versaoPrompt": None,
        "peso": current_app.config["RAG_NEURAL_RERANK_WEIGHT"],
        "limiarRelevancia": _profile_float(
            quality_profile,
            "neuralMinScore",
            "RAG_NEURAL_RERANK_MIN_SCORE",
        ),
        "candidatosAvaliados": 0,
        "candidatosAceitos": 0,
        "candidatosRejeitados": 0,
        "rejeicoes": [],
        "fallbackUtilizado": False,
        "erroFallback": None,
    }


def _deduplicate_and_limit(ranked: list[RankedChunk], limit: int) -> list[RankedChunk]:
    ranked.sort(
        key=lambda item: (
            item.ranking_score,
            item.score,
            item.authority_score,
            item.freshness_score,
            item.semantic_score,
            str(item.chunk.id),
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


def _retrieval_summary(
    sources: list[dict],
    neural_rerank: dict,
    candidate_mechanism: str,
    retrieval_plan=None,
) -> dict:
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
        "mecanismoCandidatura": candidate_mechanism,
        "fusaoRRF": any(
            len(
                {"FTS", "PGVECTOR"}.intersection(source["canaisCandidatura"])
            )
            > 1
            for source in sources
        ),
        "rerankingNeural": neural_rerank,
        "entendimentoConsulta": (
            retrieval_plan.audit_data() if retrieval_plan is not None else None
        ),
        "expansaoConsultaAplicada": bool(
            retrieval_plan is not None and retrieval_plan.expansions
        ),
        "fusaoMultiConsultaRRF": bool(
            candidate_mechanism == "POSTGRES_FTS_PGVECTOR"
            and retrieval_plan is not None
            and retrieval_plan.expansions
        ),
        "quantidadeConsultasBusca": (
            len(retrieval_plan.search_queries) if retrieval_plan is not None else 1
        ),
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


def _duration_ms(started: float) -> int:
    return max(1, round((time.perf_counter() - started) * 1000))


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


def _sanitize_source_content(content: str) -> dict:
    content_decision = assess_content_security(
        content,
        surface=ContentSecuritySurface.CHUNK_SEQUENCE,
    )
    removed = []
    safe_sentences = []
    for sentence in re.split(r"(?<=[.!?])\s+|\n+", content):
        value = sentence.strip()
        if not value:
            continue
        if assess_content_security(
            value,
            surface=ContentSecuritySurface.CHUNK_SEQUENCE,
        ).risky:
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
        "risk": bool(removed) or content_decision.risky,
        "sanitized": bool(removed),
        "ignoredInstructions": removed,
        "securityDecision": content_decision.as_dict(),
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


def _profile_float(
    profile: dict | None,
    key: str,
    config_key: str,
) -> float:
    value = (profile or {}).get(key)
    return float(current_app.config[config_key] if value is None else value)


def query_audit_payload(answer: dict) -> dict:
    return {
        "consultaHash": hashlib.sha256(answer["consulta"].encode("utf-8")).hexdigest(),
        "metodo": answer.get("metodo", "DOCUMENTAL"),
        "motivosRoteamento": answer.get("motivosRoteamento", []),
        "filtrosAplicados": answer.get("filtrosAplicados", {}),
        "entendimentoConsulta": answer.get("entendimentoConsulta"),
        "resultadoEstruturado": answer.get("resultadoEstruturado"),
        "fundamentada": answer["fundamentada"],
        "recusaConclusiva": answer["recusaConclusiva"],
        "modeloEmbedding": answer["modeloEmbedding"],
        "fallbackUtilizado": answer["fallbackUtilizado"],
        "recuperacao": answer["recuperacao"],
        "geracao": answer.get("geracao"),
        "citacoes": answer.get("citacoes", []),
        "seguranca": answer["seguranca"],
        "artefatosAprendizado": answer.get("artefatosAprendizado", []),
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
