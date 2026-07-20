import hashlib
import math
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from flask import current_app
from sqlalchemy import or_, select

from app.ai.duplicates import EmbeddingProviderError
from app.extensions import db
from app.models import (
    RagChunk,
    RagDocument,
    RagDocumentAccess,
    RagDocumentLifecycle,
    RagDocumentVersion,
    RagIngestionStatus,
)
from app.rag.service import LocalHashEmbeddingProvider, rag_embedding_provider

REFUSAL_MESSAGE = (
    "Nao encontrei evidencia suficiente na base documental acessivel para responder de forma "
    "conclusiva. Cadastre, publique ou revise fontes vigentes relacionadas ao tema antes de usar "
    "o assistente para uma resposta oficial."
)

PROMPT_INJECTION_PATTERNS = (
    "ignore as instrucoes",
    "ignorar instrucoes",
    "desconsidere as instrucoes",
    "desconsiderar instrucoes",
    "system prompt",
    "developer message",
    "revele o prompt",
    "execute este comando",
    "obedeca apenas",
)


@dataclass(frozen=True)
class RankedChunk:
    chunk: RagChunk
    score: float
    semantic_score: float
    lexical_score: float
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
    grounded = bool(ranked and ranked[0].score >= min_evidence)
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
    }


def retrieve_chunks(
    tenant_id: UUID, role: str | None, query: str, limit: int
) -> tuple[list[RankedChunk], str, bool, str | None]:
    candidates = _candidate_chunks(tenant_id, role)
    if not candidates:
        return [], LocalHashEmbeddingProvider.model, False, None

    fallback_used = False
    fallback_error = None
    try:
        provider = rag_embedding_provider()
        query_vector = provider.embeddings([query])[0]
    except EmbeddingProviderError as error:
        current_app.logger.warning("Falha no embedding RAG; usando busca lexical: %s", error)
        provider = LocalHashEmbeddingProvider()
        query_vector = provider.embeddings([query])[0]
        fallback_used = True
        fallback_error = str(error)

    threshold = current_app.config["RAG_RETRIEVAL_SCORE_THRESHOLD"]
    ranked = []
    for chunk in candidates:
        semantic_score = _cosine(query_vector, chunk.embedding)
        lexical_score = _lexical_score(query, chunk.content)
        score = (semantic_score * 0.65) + (lexical_score * 0.35)
        if score < threshold:
            continue
        ranked.append(
            RankedChunk(
                chunk=chunk,
                score=score,
                semantic_score=semantic_score,
                lexical_score=lexical_score,
                reasons=_reasons(semantic_score, lexical_score),
            )
        )
    ranked.sort(key=lambda item: item.score, reverse=True)
    return ranked[:limit], provider.model, fallback_used, fallback_error


def _candidate_chunks(tenant_id: UUID, role: str | None) -> list[RagChunk]:
    today = datetime.now(UTC).date()
    statement = (
        select(RagChunk)
        .join(RagDocumentVersion, RagChunk.version_id == RagDocumentVersion.id)
        .join(RagDocument, RagDocumentVersion.document_id == RagDocument.id)
        .where(
            RagChunk.tenant_id == tenant_id,
            RagDocumentVersion.tenant_id == tenant_id,
            RagDocument.tenant_id == tenant_id,
            RagDocument.active.is_(True),
            RagDocumentVersion.ingestion_status == RagIngestionStatus.INDEXADO,
            RagDocumentVersion.lifecycle_status == RagDocumentLifecycle.VIGENTE,
            or_(RagDocumentVersion.valid_from.is_(None), RagDocumentVersion.valid_from <= today),
            or_(RagDocumentVersion.valid_until.is_(None), RagDocumentVersion.valid_until >= today),
        )
        .order_by(RagDocumentVersion.indexed_at.desc(), RagChunk.position.asc())
        .limit(current_app.config["RAG_RETRIEVAL_CANDIDATE_LIMIT"])
    )
    if role not in {"admin", "manager"}:
        statement = statement.where(RagDocument.access_level == RagDocumentAccess.INTERNO)
    return list(db.session.execute(statement).scalars())


def _source_data(item: RankedChunk) -> dict:
    version = item.chunk.version
    document = version.document
    sanitized = _sanitize_source_content(item.chunk.content)
    return {
        "documentoId": str(document.id),
        "titulo": document.title,
        "tipo": document.document_type,
        "orgao": document.agency,
        "nivelAcesso": document.access_level.value,
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
        "similaridadeSemantica": round(item.semantic_score, 4),
        "similaridadeLexical": round(item.lexical_score, 4),
        "justificativas": item.reasons,
        "riscoPromptInjection": sanitized["risk"],
        "conteudoSanitizado": sanitized["sanitized"],
        "instrucoesIgnoradas": sanitized["ignoredInstructions"],
    }


def _grounded_answer(sources: list[dict]) -> str:
    first = sources[0]
    page = first["paginaInicio"]
    page_text = f", pagina {page}" if page else ""
    return (
        "Encontrei evidencia suficiente na base documental vigente. A principal fonte recuperada "
        f"foi '{first['titulo']}', versao {first['versao']}{page_text}. Revise as citacoes antes "
        "de usar a resposta em ato oficial."
    )


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
    return _counter_cosine(_token_vector(query), _token_vector(content))


def _token_vector(value: str) -> Counter[str]:
    normalized = unicodedata.normalize("NFKD", value.lower())
    ascii_text = "".join(char for char in normalized if not unicodedata.combining(char))
    tokens = re.findall(r"[a-z0-9]{3,}", ascii_text)
    ignored = {
        "aos",
        "com",
        "como",
        "das",
        "deve",
        "dos",
        "para",
        "por",
        "que",
        "sobre",
        "uma",
    }
    return Counter(token for token in tokens if token not in ignored)


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


def _reasons(semantic_score: float, lexical_score: float) -> list[str]:
    reasons = []
    if semantic_score >= 0.5:
        reasons.append("Alta proximidade semantica com a consulta")
    elif semantic_score >= 0.25:
        reasons.append("Proximidade semantica moderada com a consulta")
    if lexical_score >= 0.45:
        reasons.append("Termos principais encontrados no trecho")
    elif lexical_score >= 0.2:
        reasons.append("Alguns termos da consulta aparecem no trecho")
    return reasons or ["Fonte recuperada por similaridade hibrida"]


def _excerpt(content: str, max_chars: int = 700) -> str:
    value = re.sub(r"\s+", " ", content).strip()
    if len(value) <= max_chars:
        return value
    return f"{value[: max_chars - 1].rstrip()}..."


def _has_prompt_injection(content: str) -> bool:
    normalized = unicodedata.normalize("NFKD", content.lower())
    ascii_text = "".join(char for char in normalized if not unicodedata.combining(char))
    return any(pattern in ascii_text for pattern in PROMPT_INJECTION_PATTERNS)


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
        "fundamentada": answer["fundamentada"],
        "recusaConclusiva": answer["recusaConclusiva"],
        "modeloEmbedding": answer["modeloEmbedding"],
        "fallbackUtilizado": answer["fallbackUtilizado"],
        "seguranca": answer["seguranca"],
        "fontes": [
            {
                "documentoId": source["documentoId"],
                "versaoId": source["versaoId"],
                "paginaInicio": source["paginaInicio"],
                "pontuacao": source["pontuacao"],
                "riscoPromptInjection": source["riscoPromptInjection"],
            }
            for source in answer["fontes"]
        ],
    }
