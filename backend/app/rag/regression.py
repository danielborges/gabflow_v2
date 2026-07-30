import hashlib
import re
import uuid

from sqlalchemy import select

from app.audit import add_audit
from app.extensions import db
from app.models import (
    RagAssistantQuery,
    RagDocument,
    RagDocumentVersion,
    RagEvaluationQuestion,
    utc_now,
)
from app.rag.distribution import global_versions_for_tenant

FAILURE_REASONS = {
    "DOCUMENTOS_DESCONEXOS",
    "FONTE_RELEVANTE_AUSENTE",
    "RECUSA_INDEVIDA",
    "DEVERIA_RECUSAR",
    "ROTEAMENTO_INCORRETO",
    "FILTROS_INCORRETOS",
    "RESPOSTA_NAO_FUNDAMENTADA",
    "CITACAO_INCORRETA",
}
SEVERITIES = {"BAIXA", "MEDIA", "ALTA", "CRITICA"}
METHODS = {"DOCUMENTAL", "ESTRUTURADO", "HIBRIDO"}
FILTER_KEYS = {
    "dataset",
    "metrica",
    "agruparPor",
    "inicio",
    "fim",
    "status",
    "tema",
    "territorioId",
    "orgaoId",
    "tipoDocumento",
    "orgao",
    "jurisdicao",
}
REQUEST_KEYS = {
    "consultaId",
    "motivos",
    "severidade",
    "tags",
    "fontesEsperadas",
    "fontesIrrelevantes",
    "esperaRecusa",
    "metodoEsperado",
    "filtrosEsperados",
    "observacoes",
}
REFERENCE_KEYS = {"documentoId", "versaoId", "chunkId", "escopo"}


class RegressionValidationError(ValueError):
    pass


class RegressionNotFoundError(ValueError):
    pass


def capture_regression_case(
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    payload: dict,
) -> tuple[RagEvaluationQuestion, bool]:
    if not isinstance(payload, dict):
        raise RegressionValidationError("O corpo do caso deve ser um objeto.")
    unknown = set(payload) - REQUEST_KEYS
    if unknown:
        raise RegressionValidationError(
            f"Campos não permitidos: {', '.join(sorted(unknown))}."
        )
    query_id = _uuid(payload.get("consultaId"), "Consulta")
    query = db.session.scalar(
        select(RagAssistantQuery).where(
            RagAssistantQuery.tenant_id == tenant_id,
            RagAssistantQuery.id == query_id,
        )
    )
    if query is None:
        raise RegressionNotFoundError("Consulta problemática não encontrada.")
    existing = db.session.scalar(
        select(RagEvaluationQuestion).where(
            RagEvaluationQuestion.tenant_id == tenant_id,
            RagEvaluationQuestion.source_query_id == query.id,
        )
    )
    if existing is not None:
        return existing, False

    reasons = _reasons(payload.get("motivos"))
    severity = str(payload.get("severidade") or "MEDIA").strip().upper()
    if severity not in SEVERITIES:
        raise RegressionValidationError("Severidade inválida.")
    tags = _tags(payload.get("tags", []))
    expected_refs = _references(
        payload.get("fontesEsperadas", []),
        "Fontes esperadas",
    )
    hard_negatives = _references(
        payload.get("fontesIrrelevantes", []),
        "Fontes irrelevantes",
    )
    _validate_expected_references(tenant_id, expected_refs)
    _validate_hard_negatives(query, hard_negatives)
    expected_keys = {_reference_key(value) for value in expected_refs}
    hard_negative_keys = {_reference_key(value) for value in hard_negatives}
    if expected_keys & hard_negative_keys:
        raise RegressionValidationError(
            "A mesma fonte não pode ser esperada e irrelevante."
        )

    expected_refusal = payload.get("esperaRecusa", False)
    if not isinstance(expected_refusal, bool):
        raise RegressionValidationError("esperaRecusa deve ser booleano.")
    if expected_refusal and expected_refs:
        raise RegressionValidationError(
            "Caso de recusa não pode possuir fontes esperadas."
        )
    expected_method = payload.get("metodoEsperado")
    if expected_method is not None:
        expected_method = str(expected_method).strip().upper()
        if expected_method not in METHODS:
            raise RegressionValidationError("Método esperado inválido.")
    expected_filters = payload.get("filtrosEsperados", {})
    if not isinstance(expected_filters, dict):
        raise RegressionValidationError("filtrosEsperados deve ser um objeto.")
    unsupported_filters = set(expected_filters) - FILTER_KEYS
    if unsupported_filters:
        raise RegressionValidationError(
            "Filtros esperados não suportados: "
            f"{', '.join(sorted(unsupported_filters))}."
        )
    if not (
        expected_refs
        or hard_negatives
        or expected_refusal
        or expected_method
        or expected_filters
    ):
        raise RegressionValidationError(
            "Informe fontes esperadas/irrelevantes, recusa, rota ou filtros."
        )

    item = RagEvaluationQuestion(
        tenant_id=tenant_id,
        question=query.query_text,
        expected_document_ids=list(
            dict.fromkeys(value["documentoId"] for value in expected_refs)
        ),
        expected_source_refs=expected_refs,
        hard_negative_source_refs=hard_negatives,
        expected_refusal=expected_refusal,
        expected_method=expected_method,
        expected_filters=expected_filters,
        notes=_optional_text(payload.get("observacoes"), 2000),
        case_origin="REGRESSAO",
        failure_reasons=reasons,
        severity=severity,
        tags=tags,
        baseline_snapshot=_baseline_snapshot(query),
        baseline_captured_at=utc_now(),
        source_query_id=query.id,
        active=True,
        created_by_id=user_id,
    )
    db.session.add(item)
    db.session.flush()
    add_audit(
        tenant_id,
        user_id,
        "rag_evaluation.regression_case_created",
        "rag_evaluation_question",
        item.id,
        after={
            "consultaId": str(query.id),
            "motivos": reasons,
            "severidade": severity,
            "tags": tags,
            "fontesEsperadas": len(expected_refs),
            "hardNegatives": len(hard_negatives),
            "esperaRecusa": expected_refusal,
            "metodoEsperado": expected_method,
            "filtrosEsperados": sorted(expected_filters),
        },
    )
    return item, True


def _baseline_snapshot(query):
    sources = []
    for position, source in enumerate(query.sources or []):
        sources.append(
            {
                "posicao": position,
                "escopo": source.get("escopo"),
                "documentoId": source.get("documentoId"),
                "versaoId": source.get("versaoId"),
                "chunkId": source.get("chunkId"),
                "pontuacao": source.get("pontuacao"),
                "pontuacaoRanking": source.get("pontuacaoRanking"),
                "similaridadeSemantica": source.get("similaridadeSemantica"),
                "similaridadeLexical": source.get("similaridadeLexical"),
                "modeloEmbedding": source.get("modeloEmbedding"),
                "modoRecuperacao": source.get("modoRecuperacao"),
            }
        )
    return {
        "schemaVersion": "rag-regression-baseline-v1",
        "consultaId": str(query.id),
        "consultaHash": query.query_hash,
        "respostaHash": hashlib.sha256(query.response.encode("utf-8")).hexdigest(),
        "metodo": query.method,
        "motivosRoteamento": query.routing_reasons,
        "filtrosAplicados": query.applied_filters,
        "fundamentada": query.grounded,
        "recusaConclusiva": query.refused,
        "limiarEvidencia": query.evidence_threshold,
        "modeloEmbeddingConsulta": query.embedding_model,
        "fallbackUtilizado": query.fallback_used,
        "artefatosAprendizado": query.learning_artifacts,
        "fontes": sources,
        "criadaEm": query.created_at.isoformat(),
    }


def _validate_expected_references(tenant_id, references):
    private = [value for value in references if value["escopo"] == "PRIVADO"]
    if private:
        found = {
            (str(value.document_id), str(value.id))
            for value in db.session.scalars(
                select(RagDocumentVersion)
                .join(RagDocument)
                .where(
                    RagDocumentVersion.tenant_id == tenant_id,
                    RagDocumentVersion.id.in_(
                        [uuid.UUID(value["versaoId"]) for value in private]
                    ),
                    RagDocument.active.is_(True),
                )
            )
        }
        expected = {
            (value["documentoId"], value["versaoId"]) for value in private
        }
        if found != expected:
            raise RegressionValidationError(
                "Fonte privada esperada não pertence ao tenant ou está inativa."
            )
    global_refs = [value for value in references if value["escopo"] == "GLOBAL"]
    if global_refs:
        available = {
            (str(value.document_id), str(value.id))
            for value in global_versions_for_tenant(tenant_id)
        }
        expected = {
            (value["documentoId"], value["versaoId"]) for value in global_refs
        }
        if not expected.issubset(available):
            raise RegressionValidationError(
                "Fonte global esperada não está disponível ao tenant."
            )


def _validate_hard_negatives(query, references):
    returned = [_reference_key(value) for value in query.sources or []]

    def was_returned(reference):
        key = _reference_key(reference)
        if key[2] is not None:
            return key in returned
        return any(
            candidate[0] == key[0]
            and candidate[1] == key[1]
            and candidate[3] == key[3]
            for candidate in returned
        )

    if any(not was_returned(value) for value in references):
        raise RegressionValidationError(
            "Fonte irrelevante deve ter sido retornada na consulta original."
        )


def _references(value, label):
    if not isinstance(value, list) or len(value) > 20:
        raise RegressionValidationError(f"{label} deve ter até 20 itens.")
    result = []
    for raw in value:
        if not isinstance(raw, dict) or set(raw) - REFERENCE_KEYS:
            raise RegressionValidationError(f"{label} contém referência inválida.")
        scope = str(raw.get("escopo") or "PRIVADO").strip().upper()
        if scope not in {"PRIVADO", "GLOBAL"}:
            raise RegressionValidationError("Escopo de fonte inválido.")
        document_id = _uuid(raw.get("documentoId"), "Documento")
        version_id = _uuid(raw.get("versaoId"), "Versão")
        chunk_value = raw.get("chunkId")
        chunk_id = _uuid(chunk_value, "Chunk") if chunk_value else None
        reference = {
            "documentoId": str(document_id),
            "versaoId": str(version_id),
            "chunkId": str(chunk_id) if chunk_id else None,
            "escopo": scope,
        }
        if _reference_key(reference) not in {
            _reference_key(existing) for existing in result
        }:
            result.append(reference)
    return result


def _reference_key(value):
    return (
        str(value.get("documentoId")),
        str(value.get("versaoId")),
        str(value.get("chunkId")) if value.get("chunkId") else None,
        str(value.get("escopo") or "PRIVADO").upper(),
    )


def _reasons(value):
    if not isinstance(value, list) or not value or len(value) > 8:
        raise RegressionValidationError("motivos deve conter entre 1 e 8 itens.")
    reasons = list(dict.fromkeys(str(item).strip().upper() for item in value))
    if any(item not in FAILURE_REASONS for item in reasons):
        raise RegressionValidationError("Motivo de regressão inválido.")
    return reasons


def _tags(value):
    if not isinstance(value, list) or len(value) > 10:
        raise RegressionValidationError("tags deve ser uma lista com até 10 itens.")
    tags = []
    for raw in value:
        tag = " ".join(str(raw).split()).lower()
        if not tag or len(tag) > 40 or not re.fullmatch(r"[\wÀ-ÿ -]+", tag):
            raise RegressionValidationError("Tag de regressão inválida.")
        if tag not in tags:
            tags.append(tag)
    return tags


def _uuid(value, label):
    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError) as error:
        raise RegressionValidationError(f"{label} inválido.") from error


def _optional_text(value, maximum):
    if value is None:
        return None
    text = " ".join(str(value).split())
    if len(text) > maximum:
        raise RegressionValidationError(
            f"Observações deve ter no máximo {maximum} caracteres."
        )
    return text or None
