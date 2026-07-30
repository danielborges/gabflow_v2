import math
from dataclasses import dataclass
from uuid import UUID

from flask import current_app
from sqlalchemy import select, text
from sqlalchemy.orm import joinedload

from app.extensions import db
from app.models import (
    GlobalKnowledgeChunk,
    GlobalKnowledgeDocument,
    GlobalKnowledgeDocumentVersion,
    RagChunk,
    RagDocumentVersion,
)


@dataclass(frozen=True)
class HybridCandidate:
    scope: str
    chunk: RagChunk | GlobalKnowledgeChunk
    database_lexical_score: float | None
    database_semantic_score: float | None
    fusion_score: float
    channels: tuple[str, ...]


_PRIVATE_ELIGIBILITY = """
FROM rag_chunks c
JOIN rag_document_versions v
  ON v.id = c.version_id
 AND v.tenant_id = c.tenant_id
JOIN rag_documents d
  ON d.id = v.document_id
 AND d.tenant_id = c.tenant_id
WHERE c.tenant_id = CAST(:tenant_id AS uuid)
  AND d.active IS TRUE
  AND v.ingestion_status = 'INDEXADO'
  AND v.lifecycle_status = 'VIGENTE'
  AND (v.valid_from IS NULL OR v.valid_from <= CURRENT_DATE)
  AND (v.valid_until IS NULL OR v.valid_until >= CURRENT_DATE)
  AND (:privileged OR d.access_level = 'INTERNO')
  AND (
    NOT EXISTS (
      SELECT 1
      FROM rag_knowledge_sources source_any
      WHERE source_any.tenant_id = c.tenant_id
        AND source_any.document_id = d.id
    )
    OR EXISTS (
      SELECT 1
      FROM rag_knowledge_sources source_ok
      WHERE source_ok.tenant_id = c.tenant_id
        AND source_ok.document_id = d.id
        AND source_ok.status IN ('ATIVA', 'PENDENTE', 'QUARENTENA', 'ERRO')
        AND (
          source_ok.retention_until IS NULL
          OR source_ok.retention_until >= CURRENT_DATE
        )
    )
  )
"""

_GLOBAL_ELIGIBILITY = """
FROM rag_global.chunks c
JOIN rag_global.document_versions v
  ON v.id = c.version_id
JOIN rag_global.documents d
  ON d.id = v.document_id
JOIN rag_global.tenant_published_chunks published
  ON published.chunk_id = c.id
 AND published.tenant_id = CAST(:tenant_id AS uuid)
"""


def postgres_hybrid_candidates(
    tenant_id: UUID,
    role: str | None,
    query: str,
    query_vector: list[float] | None,
    embedding_model: str | None,
    *,
    limit: int,
    filters: dict | None = None,
) -> list[HybridCandidate] | None:
    if (
        db.engine.dialect.name != "postgresql"
        or not current_app.config["RAG_HYBRID_DATABASE_ENABLED"]
    ):
        return None

    safe_limit = max(1, min(int(limit), 1000))
    parameters = {
        "tenant_id": str(tenant_id),
        "query": query,
        "limit": safe_limit,
        "privileged": role in {"admin", "manager"},
    }
    channels: dict[tuple[str, UUID], dict] = {}
    if _valid_vector(query_vector) is not None:
        db.session.execute(
            text("SELECT set_config('hnsw.iterative_scan', 'strict_order', true)")
        )
        db.session.execute(
            text("SELECT set_config('hnsw.ef_search', :value, true)"),
            {
                "value": str(
                    max(1, current_app.config["RAG_HYBRID_HNSW_EF_SEARCH"])
                )
            },
        )
    for scope, eligibility in (
        ("PRIVADO", _PRIVATE_ELIGIBILITY),
        ("GLOBAL", _GLOBAL_ELIGIBILITY),
    ):
        filter_sql, filter_parameters = _documentary_filter_sql(
            scope,
            filters or {},
        )
        scoped_parameters = {**parameters, **filter_parameters}
        lexical_rows = db.session.execute(
            text(
                f"""
                SELECT
                    c.id,
                    ts_rank_cd(
                        (
                            c.search_vector
                            || to_tsvector(
                                'portuguese',
                                coalesce(d.title, '') || ' '
                                || coalesce(d.document_type, '') || ' '
                                || coalesce(d.agency, '')
                            )
                        ),
                        websearch_to_tsquery('portuguese', :query),
                        32
                    ) AS channel_score
                {eligibility}
                  {filter_sql}
                  AND (
                    c.search_vector
                    || to_tsvector(
                        'portuguese',
                        coalesce(d.title, '') || ' '
                        || coalesce(d.document_type, '') || ' '
                        || coalesce(d.agency, '')
                    )
                  ) @@ websearch_to_tsquery('portuguese', :query)
                ORDER BY channel_score DESC, c.id
                LIMIT :limit
                """
            ),
            scoped_parameters,
        ).all()
        _merge_channel(channels, scope, "FTS", lexical_rows)

        vector = _valid_vector(query_vector)
        if vector is None or not embedding_model:
            continue
        dimensions = len(vector)
        vector_literal = "[" + ",".join(f"{value:.9g}" for value in vector) + "]"
        semantic_rows = db.session.execute(
            text(
                f"""
                SELECT
                    c.id,
                    GREATEST(
                        0.0,
                        LEAST(
                            1.0,
                            1.0 - (
                                (c.embedding_vector::vector({dimensions}))
                                <=>
                                CAST(:query_vector AS vector({dimensions}))
                            )
                        )
                    ) AS channel_score
                {eligibility}
                  {filter_sql}
                  AND c.embedding_vector IS NOT NULL
                  AND c.embedding_model = :embedding_model
                  AND vector_dims(c.embedding_vector) = :dimensions
                ORDER BY
                    (c.embedding_vector::vector({dimensions}))
                    <=>
                    CAST(:query_vector AS vector({dimensions}))
                LIMIT :limit
                """
            ),
            {
                **scoped_parameters,
                "query_vector": vector_literal,
                "embedding_model": embedding_model,
                "dimensions": dimensions,
            },
        ).all()
        _merge_channel(channels, scope, "PGVECTOR", semantic_rows)

    if not channels:
        return []

    rrf_k = max(1, int(current_app.config["RAG_HYBRID_RRF_K"]))
    fused = []
    for (scope, chunk_id), values in channels.items():
        score = sum(
            1.0 / (rrf_k + rank)
            for rank in (values.get("FTS_rank"), values.get("PGVECTOR_rank"))
            if rank is not None
        )
        fused.append((score, scope, chunk_id, values))
    fused.sort(
        key=lambda item: (
            item[0],
            item[3].get("PGVECTOR_score") or 0.0,
            item[3].get("FTS_score") or 0.0,
            str(item[2]),
        ),
        reverse=True,
    )
    fused = fused[:safe_limit]

    private_ids = [item[2] for item in fused if item[1] == "PRIVADO"]
    global_ids = [item[2] for item in fused if item[1] == "GLOBAL"]
    chunks: dict[tuple[str, UUID], RagChunk | GlobalKnowledgeChunk] = {}
    if private_ids:
        private_chunks = db.session.scalars(
            select(RagChunk)
            .where(
                RagChunk.tenant_id == tenant_id,
                RagChunk.id.in_(private_ids),
            )
            .options(
                joinedload(RagChunk.version).joinedload(RagDocumentVersion.document)
            )
        )
        chunks.update({("PRIVADO", item.id): item for item in private_chunks})
    if global_ids:
        global_chunks = db.session.scalars(
            select(GlobalKnowledgeChunk)
            .where(GlobalKnowledgeChunk.id.in_(global_ids))
            .options(
                joinedload(GlobalKnowledgeChunk.version)
                .joinedload(GlobalKnowledgeDocumentVersion.document)
                .joinedload(GlobalKnowledgeDocument.collection)
            )
        )
        chunks.update({("GLOBAL", item.id): item for item in global_chunks})

    result = []
    for fusion_score, scope, chunk_id, values in fused:
        chunk = chunks.get((scope, chunk_id))
        if chunk is None:
            continue
        result.append(
            HybridCandidate(
                scope=scope,
                chunk=chunk,
                database_lexical_score=values.get("FTS_score"),
                database_semantic_score=values.get("PGVECTOR_score"),
                fusion_score=fusion_score,
                channels=tuple(
                    channel
                    for channel in ("FTS", "PGVECTOR")
                    if values.get(f"{channel}_rank") is not None
                ),
            )
        )
    return result


def _documentary_filter_sql(scope: str, filters: dict) -> tuple[str, dict]:
    clauses = []
    parameters = {}
    document_type = filters.get("tipoDocumento")
    if document_type:
        type_query = str(document_type).replace("_", " ")
        clauses.append(
            """
            AND (
              LOWER(d.document_type) LIKE LOWER(:document_type)
              OR LOWER(d.title) LIKE LOWER(:document_type)
              OR c.search_vector @@ plainto_tsquery('portuguese', :document_type_query)
            )
            """
        )
        type_fragment = type_query[:5] if len(type_query) > 5 else type_query
        parameters["document_type"] = f"%{type_fragment}%"
        parameters["document_type_query"] = type_query
    agency = filters.get("orgao")
    if agency:
        clauses.append("AND d.agency ILIKE :document_agency")
        parameters["document_agency"] = f"%{agency}%"
    theme = filters.get("temaBusca")
    if theme:
        clauses.append(
            """
            AND (
              c.search_vector
              || to_tsvector(
                  'portuguese',
                  coalesce(d.title, '') || ' '
                  || coalesce(d.document_type, '') || ' '
                  || coalesce(d.agency, '')
              )
            ) @@ websearch_to_tsquery('portuguese', :document_theme)
            """
        )
        parameters["document_theme"] = str(theme)
    if filters.get("inicio"):
        clauses.append("AND (v.valid_until IS NULL OR v.valid_until >= :document_start)")
        parameters["document_start"] = filters["inicio"]
    if filters.get("fim"):
        clauses.append("AND (v.valid_from IS NULL OR v.valid_from <= :document_end)")
        parameters["document_end"] = filters["fim"]
    jurisdiction = filters.get("jurisdicao")
    if jurisdiction and scope == "GLOBAL":
        clauses.append("AND CAST(d.jurisdiction AS text) ILIKE :document_jurisdiction")
        parameters["document_jurisdiction"] = f"%{jurisdiction}%"
    return "\n".join(clauses), parameters


def _merge_channel(channels, scope, channel, rows):
    for rank, row in enumerate(rows, start=1):
        values = channels.setdefault((scope, row.id), {})
        values[f"{channel}_rank"] = rank
        values[f"{channel}_score"] = float(row.channel_score or 0.0)


def _valid_vector(vector):
    if not vector or len(vector) > 2000:
        return None
    normalized = []
    for raw in vector:
        value = float(raw)
        if not math.isfinite(value):
            return None
        normalized.append(value)
    return normalized
