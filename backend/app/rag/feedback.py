import hashlib
import json
import re
import uuid
from dataclasses import dataclass

from sqlalchemy import select

from app.audit import add_audit
from app.extensions import db
from app.models import (
    RagAssistantQuery,
    RagDocument,
    RagDocumentAccess,
    RagDocumentVersion,
    RagFeedbackModerationMode,
    RagFeedbackReason,
    RagFeedbackSourceJudgment,
    RagFeedbackSourceJudgmentValue,
    RagFeedbackStatus,
    RagQueryFeedback,
    RagQueryFeedbackRating,
    utc_now,
)
from app.rag.content_security import (
    ContentSecurityDecision,
    ContentSecurityStatus,
    ContentSecuritySurface,
    apply_content_security_decision,
    assess_content_security,
    content_security_state,
)
from app.rag.distribution import global_versions_for_tenant

EXPECTED_METHODS = {"DOCUMENTAL", "ESTRUTURADO", "HIBRIDO"}
FILTER_KEYS = {
    "dataset",
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
CREATE_KEYS = {
    "idempotencyKey",
    "avaliacao",
    "motivos",
    "comentario",
    "respostaCorrigida",
    "metodoEsperado",
    "filtrosEsperados",
    "julgamentosFontes",
}
IDEMPOTENCY_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{8,120}$")
SOURCE_JUDGMENT_KEYS = {
    "documentoId",
    "versaoId",
    "chunkId",
    "escopo",
    "julgamento",
    "motivo",
}


class FeedbackValidationError(ValueError):
    pass


class FeedbackConflictError(ValueError):
    pass


class FeedbackNotFoundError(ValueError):
    pass


@dataclass(frozen=True)
class FeedbackCreation:
    feedback: RagQueryFeedback
    created: bool


def create_feedback_revision(
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    query_id: uuid.UUID,
    payload: dict,
    *,
    role: str,
    strict: bool = True,
) -> FeedbackCreation:
    if not isinstance(payload, dict):
        raise FeedbackValidationError("O corpo do feedback deve ser um objeto.")
    if strict:
        unknown = set(payload) - CREATE_KEYS
        if unknown:
            raise FeedbackValidationError(
                f"Campos de feedback não permitidos: {', '.join(sorted(unknown))}."
            )

    query = db.session.execute(
        select(RagAssistantQuery)
        .where(
            RagAssistantQuery.tenant_id == tenant_id,
            RagAssistantQuery.id == query_id,
        )
        .with_for_update()
    ).scalar_one_or_none()
    if query is None:
        raise FeedbackNotFoundError("Consulta RAG não encontrada.")

    values = _feedback_values(payload, query, tenant_id, role)
    content_hash = _content_hash(query_id, values)
    idempotency_key = values.pop("idempotency_key")
    if idempotency_key:
        existing = db.session.execute(
            select(RagQueryFeedback).where(
                RagQueryFeedback.tenant_id == tenant_id,
                RagQueryFeedback.query_id == query_id,
                RagQueryFeedback.idempotency_key == idempotency_key,
            )
        ).scalar_one_or_none()
        if existing:
            if existing.content_hash != content_hash:
                raise FeedbackConflictError(
                    "A chave de idempotência já foi usada com outro conteúdo."
                )
            return FeedbackCreation(existing, False)

    latest = db.session.execute(
        select(RagQueryFeedback)
        .where(
            RagQueryFeedback.tenant_id == tenant_id,
            RagQueryFeedback.query_id == query_id,
        )
        .order_by(RagQueryFeedback.revision.desc())
        .limit(1)
    ).scalar_one_or_none()
    if latest is not None and latest.status != RagFeedbackStatus.REVOGADO:
        latest.status = RagFeedbackStatus.SUPERADO
        from app.rag.curation import deactivate_questions_for_feedback

        deactivate_questions_for_feedback(
            latest,
            user_id,
            "FEEDBACK_SUPERADO",
        )
        from app.rag.learning import invalidate_learning_for_feedback

        invalidate_learning_for_feedback(
            latest,
            user_id,
            "FEEDBACK_SUPERADO",
        )

    now = utc_now()
    status, moderation_mode, moderation_rule, security_decision = _initial_moderation(
        values
    )
    feedback = RagQueryFeedback(
        tenant_id=tenant_id,
        query_id=query_id,
        revision=(latest.revision + 1) if latest else 1,
        previous_feedback_id=latest.id if latest else None,
        idempotency_key=idempotency_key,
        rating=values["rating"],
        reasons=values["reasons"],
        comment=values["comment"],
        corrected_response=values["corrected_response"],
        expected_method=values["expected_method"],
        expected_filters=values["expected_filters"],
        status=status,
        content_hash=content_hash,
        created_by_id=user_id,
        moderation_mode=moderation_mode,
        moderation_rule=moderation_rule,
        moderated_at=now if moderation_mode else None,
    )
    apply_content_security_decision(feedback, security_decision)
    db.session.add(feedback)
    db.session.flush()
    for judgment in values["source_judgments"]:
        db.session.add(
            RagFeedbackSourceJudgment(
                tenant_id=tenant_id,
                feedback_id=feedback.id,
                **judgment,
            )
        )

    query.feedback_rating = feedback.rating
    query.feedback_comment = None if status == RagFeedbackStatus.QUARENTENA else feedback.comment
    query.corrected_response = (
        None if status == RagFeedbackStatus.QUARENTENA else feedback.corrected_response
    )
    query.reviewed_by_id = user_id
    query.reviewed_at = now
    add_audit(
        tenant_id,
        user_id,
        "rag_assistant.feedback_revision_created",
        "rag_query_feedback",
        feedback.id,
        after={
            "consultaId": str(query_id),
            "revisao": feedback.revision,
            "avaliacao": feedback.rating.value,
            "motivos": feedback.reasons,
            "estado": feedback.status.value,
            "julgamentosFontes": len(values["source_judgments"]),
            "possuiComentario": bool(feedback.comment),
            "possuiCorrecao": bool(feedback.corrected_response),
            "modoModeracao": (
                feedback.moderation_mode.value if feedback.moderation_mode else None
            ),
        },
    )
    if feedback.status == RagFeedbackStatus.APROVADO:
        from app.rag.learning import record_learning_feedback

        record_learning_feedback(feedback)
    return FeedbackCreation(feedback, True)


def feedback_data(item: RagQueryFeedback) -> dict:
    judgments = list(
        db.session.scalars(
            select(RagFeedbackSourceJudgment)
            .where(
                RagFeedbackSourceJudgment.tenant_id == item.tenant_id,
                RagFeedbackSourceJudgment.feedback_id == item.id,
            )
            .order_by(RagFeedbackSourceJudgment.original_position)
        )
    )
    quarantined = item.status == RagFeedbackStatus.QUARENTENA
    return {
        "id": str(item.id),
        "tenantId": str(item.tenant_id),
        "consultaId": str(item.query_id),
        "revisao": item.revision,
        "revisaoAnteriorId": (
            str(item.previous_feedback_id) if item.previous_feedback_id else None
        ),
        "avaliacao": item.rating.value,
        "motivos": item.reasons,
        "comentario": None if quarantined else item.comment,
        "respostaCorrigida": None if quarantined else item.corrected_response,
        "conteudoRetido": quarantined,
        "metodoEsperado": item.expected_method,
        "filtrosEsperados": item.expected_filters,
        "julgamentosFontes": [_source_judgment_data(value) for value in judgments],
        "estado": item.status.value,
        "hashConteudo": item.content_hash,
        "criadoPorId": str(item.created_by_id),
        "criadoEm": item.created_at.isoformat(),
        "modoModeracao": (
            item.moderation_mode.value if item.moderation_mode else None
        ),
        "regraModeracao": item.moderation_rule,
        "moderadoPorId": str(item.moderated_by_id) if item.moderated_by_id else None,
        "moderadoEm": item.moderated_at.isoformat() if item.moderated_at else None,
        "justificativaModeracao": item.moderation_reason,
        "segurancaConteudo": content_security_state(item),
    }


def moderate_feedback(
    item: RagQueryFeedback,
    moderator_id: uuid.UUID,
    decision: str,
    reason: str | None,
) -> None:
    transitions = {
        "APROVAR": RagFeedbackStatus.APROVADO,
        "REJEITAR": RagFeedbackStatus.REJEITADO,
        "QUARENTENAR": RagFeedbackStatus.QUARENTENA,
        "REVOGAR": RagFeedbackStatus.REVOGADO,
    }
    target = transitions.get(str(decision or "").strip().upper())
    if target is None:
        raise FeedbackValidationError("Decisão de moderação inválida.")
    if item.status == RagFeedbackStatus.SUPERADO:
        raise FeedbackConflictError("Feedback superado não pode ser moderado.")
    allowed = {
        RagFeedbackStatus.PENDENTE_REVISAO: {
            RagFeedbackStatus.APROVADO,
            RagFeedbackStatus.REJEITADO,
            RagFeedbackStatus.QUARENTENA,
            RagFeedbackStatus.REVOGADO,
        },
        RagFeedbackStatus.QUARENTENA: {
            RagFeedbackStatus.APROVADO,
            RagFeedbackStatus.REJEITADO,
            RagFeedbackStatus.REVOGADO,
        },
        RagFeedbackStatus.APROVADO: {RagFeedbackStatus.REVOGADO},
        RagFeedbackStatus.REJEITADO: {RagFeedbackStatus.REVOGADO},
    }
    if target not in allowed.get(item.status, set()):
        raise FeedbackConflictError(
            f"Transição de {item.status.value} para {target.value} não permitida."
        )
    normalized_reason = _optional_text(reason, 2000, "Justificativa")
    if target in {
        RagFeedbackStatus.REJEITADO,
        RagFeedbackStatus.QUARENTENA,
        RagFeedbackStatus.REVOGADO,
    } and not normalized_reason:
        raise FeedbackValidationError("Informe a justificativa da moderação.")

    before = item.status
    item.status = target
    item.moderation_mode = RagFeedbackModerationMode.HUMANA
    item.moderation_rule = "manual-review-v1"
    item.moderated_by_id = moderator_id
    item.moderated_at = utc_now()
    item.moderation_reason = normalized_reason
    latest_revision = db.session.scalar(
        select(db.func.max(RagQueryFeedback.revision)).where(
            RagQueryFeedback.tenant_id == item.tenant_id,
            RagQueryFeedback.query_id == item.query_id,
        )
    )
    if latest_revision == item.revision:
        query = db.session.execute(
            select(RagAssistantQuery).where(
                RagAssistantQuery.tenant_id == item.tenant_id,
                RagAssistantQuery.id == item.query_id,
            )
        ).scalar_one()
        if target == RagFeedbackStatus.APROVADO:
            query.feedback_rating = item.rating
            query.feedback_comment = item.comment
            query.corrected_response = item.corrected_response
            query.reviewed_by_id = item.created_by_id
        elif target == RagFeedbackStatus.QUARENTENA:
            query.feedback_comment = None
            query.corrected_response = None
        else:
            query.feedback_rating = None
            query.feedback_comment = None
            query.corrected_response = None
            query.reviewed_by_id = None
        query.reviewed_at = item.moderated_at
    if target != RagFeedbackStatus.APROVADO:
        from app.rag.curation import deactivate_questions_for_feedback
        from app.rag.learning import invalidate_learning_for_feedback

        deactivate_questions_for_feedback(
            item,
            moderator_id,
            f"FEEDBACK_{target.value}",
        )
        invalidate_learning_for_feedback(
            item,
            moderator_id,
            f"FEEDBACK_{target.value}",
        )
    else:
        from app.rag.learning import record_learning_feedback

        record_learning_feedback(item)
    add_audit(
        item.tenant_id,
        moderator_id,
        "rag_assistant.feedback_moderated",
        "rag_query_feedback",
        item.id,
        before={"estado": before.value},
        after={
            "estado": target.value,
            "possuiJustificativa": bool(normalized_reason),
        },
    )


def _feedback_values(
    payload: dict,
    query: RagAssistantQuery,
    tenant_id: uuid.UUID,
    role: str,
) -> dict:
    try:
        rating = RagQueryFeedbackRating(str(payload.get("avaliacao", "")).upper())
    except ValueError as error:
        raise FeedbackValidationError("Avaliação inválida.") from error

    reasons_value = payload.get("motivos", [])
    if not isinstance(reasons_value, list) or len(reasons_value) > 8:
        raise FeedbackValidationError("Motivos deve ser uma lista com até 8 itens.")
    try:
        reasons = list(
            dict.fromkeys(
                RagFeedbackReason(str(value).upper()).value for value in reasons_value
            )
        )
    except ValueError as error:
        raise FeedbackValidationError("Motivo de feedback inválido.") from error

    comment = _minimize_text(
        _optional_text(payload.get("comentario"), 2000, "Comentário")
    )
    corrected_response = _minimize_text(
        _optional_text(
            payload.get("respostaCorrigida"),
            10000,
            "Resposta corrigida",
        )
    )
    if rating == RagQueryFeedbackRating.CORRIGIDA and not corrected_response:
        raise FeedbackValidationError(
            "Informe a resposta corrigida para uma avaliação corrigida."
        )
    if corrected_response and rating != RagQueryFeedbackRating.CORRIGIDA:
        raise FeedbackValidationError(
            "Resposta corrigida exige avaliação CORRIGIDA."
        )

    expected_method = _optional_text(
        payload.get("metodoEsperado"),
        20,
        "Método esperado",
    )
    if expected_method:
        expected_method = expected_method.upper()
        if expected_method not in EXPECTED_METHODS:
            raise FeedbackValidationError("Método esperado inválido.")
    expected_filters = _expected_filters(payload.get("filtrosEsperados"))
    source_judgments = _source_judgments(
        payload.get("julgamentosFontes"),
        query,
        tenant_id,
        role,
    )
    idempotency_key = _optional_text(
        payload.get("idempotencyKey"),
        120,
        "Chave de idempotência",
    )
    if idempotency_key and not IDEMPOTENCY_PATTERN.fullmatch(idempotency_key):
        raise FeedbackValidationError(
            "Chave de idempotência deve possuir entre 8 e 120 caracteres seguros."
        )
    return {
        "rating": rating,
        "reasons": reasons,
        "comment": comment,
        "corrected_response": corrected_response,
        "expected_method": expected_method,
        "expected_filters": expected_filters,
        "source_judgments": source_judgments,
        "idempotency_key": idempotency_key,
    }


def _source_judgments(
    value: object,
    query: RagAssistantQuery,
    tenant_id: uuid.UUID,
    role: str,
) -> list[dict]:
    if value is None:
        return []
    if not isinstance(value, list) or len(value) > 20:
        raise FeedbackValidationError(
            "Julgamentos de fontes deve ser uma lista com até 20 itens."
        )
    if not value:
        return []

    returned_sources = {}
    for position, source in enumerate(query.sources):
        try:
            document_id = uuid.UUID(str(source.get("documentoId")))
            version_id = uuid.UUID(str(source.get("versaoId")))
        except (AttributeError, TypeError, ValueError):
            continue
        returned_sources[(document_id, version_id)] = {
            "scope": str(source.get("escopo", "")).upper(),
            "chunk_id": _optional_uuid(source.get("chunkId")),
            "position": position,
        }

    private_versions = {
        (item.document_id, item.id): item.document
        for item in db.session.scalars(
            select(RagDocumentVersion).where(
                RagDocumentVersion.tenant_id == tenant_id
            )
        )
    }
    global_versions = {
        (item.document_id, item.id) for item in global_versions_for_tenant(tenant_id)
    }
    result = []
    seen = set()
    for raw in value:
        if not isinstance(raw, dict):
            raise FeedbackValidationError("Julgamento de fonte inválido.")
        unknown = set(raw) - SOURCE_JUDGMENT_KEYS
        if unknown:
            raise FeedbackValidationError(
                f"Campos de julgamento não permitidos: {', '.join(sorted(unknown))}."
            )
        try:
            document_id = uuid.UUID(str(raw.get("documentoId")))
            version_id = uuid.UUID(str(raw.get("versaoId")))
            judgment = RagFeedbackSourceJudgmentValue(
                str(raw.get("julgamento", "")).upper()
            )
            reason = RagFeedbackReason(str(raw.get("motivo", "")).upper())
        except (TypeError, ValueError) as error:
            raise FeedbackValidationError("Julgamento de fonte inválido.") from error
        key = (document_id, version_id)
        if key in seen:
            raise FeedbackValidationError("A mesma fonte foi julgada mais de uma vez.")
        seen.add(key)

        returned = returned_sources.get(key)
        source_scope = str(raw.get("escopo") or (returned or {}).get("scope") or "").upper()
        if source_scope not in {"GLOBAL", "PRIVADO"}:
            raise FeedbackValidationError("Escopo da fonte inválido.")
        _ensure_source_visible(
            key,
            source_scope,
            private_versions,
            global_versions,
            role,
        )
        if judgment == RagFeedbackSourceJudgmentValue.AUSENTE:
            if returned is not None:
                raise FeedbackValidationError(
                    "Fonte retornada deve ser julgada como relevante ou irrelevante."
                )
            original_position = None
        else:
            if returned is None or returned["scope"] != source_scope:
                raise FeedbackValidationError(
                    "Fonte julgada não pertence às fontes registradas na consulta."
                )
            original_position = returned["position"]

        chunk_id = _optional_uuid(raw.get("chunkId"))
        if chunk_id and returned and returned["chunk_id"] != chunk_id:
            raise FeedbackValidationError(
                "Chunk julgado não pertence à fonte registrada na consulta."
            )
        result.append(
            {
                "document_id": document_id,
                "version_id": version_id,
                "chunk_id": chunk_id,
                "source_scope": source_scope,
                "judgment": judgment,
                "reason": reason,
                "original_position": original_position,
            }
        )
    return result


def _ensure_source_visible(
    key: tuple[uuid.UUID, uuid.UUID],
    scope: str,
    private_versions: dict,
    global_versions: set,
    role: str,
) -> None:
    if scope == "GLOBAL":
        if key not in global_versions:
            raise FeedbackValidationError(
                "Fonte global não está disponível para o tenant."
            )
        return
    document: RagDocument | None = private_versions.get(key)
    if document is None:
        raise FeedbackValidationError("Fonte privada não pertence ao tenant.")
    if (
        document.access_level == RagDocumentAccess.RESTRITO
        and role not in {"admin", "manager"}
    ):
        raise FeedbackValidationError("Fonte privada não está disponível ao usuário.")


def _expected_filters(value: object) -> dict:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise FeedbackValidationError("Filtros esperados deve ser um objeto.")
    unknown = set(value) - FILTER_KEYS
    if unknown:
        raise FeedbackValidationError(
            f"Filtros esperados não permitidos: {', '.join(sorted(unknown))}."
        )
    normalized = {}
    for key, raw in value.items():
        if raw is None:
            continue
        if key in {"territorioId", "orgaoId"}:
            try:
                normalized[key] = str(uuid.UUID(str(raw)))
            except (TypeError, ValueError) as error:
                raise FeedbackValidationError(f"{key} inválido.") from error
            continue
        if not isinstance(raw, str):
            raise FeedbackValidationError(f"{key} deve ser texto.")
        text = raw.strip()
        if not text or len(text) > 160:
            raise FeedbackValidationError(f"{key} deve possuir entre 1 e 160 caracteres.")
        normalized[key] = _minimize_text(text)
    return normalized


def _initial_moderation(
    values: dict,
) -> tuple[
    RagFeedbackStatus,
    RagFeedbackModerationMode | None,
    str | None,
    ContentSecurityDecision,
]:
    security_decision = assess_content_security(
        "\n".join(
            (
                values["comment"] or "",
                values["corrected_response"] or "",
            )
        ),
        surface=ContentSecuritySurface.FEEDBACK,
        metadata=values["expected_filters"],
    )
    if security_decision.status != ContentSecurityStatus.CLEAN:
        return (
            RagFeedbackStatus.QUARENTENA,
            RagFeedbackModerationMode.AUTOMATICA,
            "prompt-injection-v1",
            security_decision,
        )
    if (
        values["comment"]
        or values["corrected_response"]
        or any(
            item["judgment"] == RagFeedbackSourceJudgmentValue.AUSENTE
            for item in values["source_judgments"]
        )
    ):
        return RagFeedbackStatus.PENDENTE_REVISAO, None, None, security_decision
    return (
        RagFeedbackStatus.APROVADO,
        RagFeedbackModerationMode.AUTOMATICA,
        "structured-low-risk-v1",
        security_decision,
    )


def _content_hash(query_id: uuid.UUID, values: dict) -> str:
    judgments = [
        {
            "document_id": str(item["document_id"]),
            "version_id": str(item["version_id"]),
            "chunk_id": str(item["chunk_id"]) if item["chunk_id"] else None,
            "source_scope": item["source_scope"],
            "judgment": item["judgment"].value,
            "reason": item["reason"].value,
            "original_position": item["original_position"],
        }
        for item in values["source_judgments"]
    ]
    canonical = {
        "query_id": str(query_id),
        "rating": values["rating"].value,
        "reasons": sorted(values["reasons"]),
        "comment": values["comment"],
        "corrected_response": values["corrected_response"],
        "expected_method": values["expected_method"],
        "expected_filters": values["expected_filters"],
        "source_judgments": sorted(
            judgments,
            key=lambda item: (
                item["document_id"],
                item["version_id"],
                item["judgment"],
            ),
        ),
    }
    payload = json.dumps(
        canonical,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _source_judgment_data(item: RagFeedbackSourceJudgment) -> dict:
    return {
        "id": str(item.id),
        "documentoId": str(item.document_id),
        "versaoId": str(item.version_id),
        "chunkId": str(item.chunk_id) if item.chunk_id else None,
        "escopo": item.source_scope,
        "julgamento": item.judgment.value,
        "motivo": item.reason.value,
        "posicaoOriginal": item.original_position,
    }


def _optional_uuid(value: object) -> uuid.UUID | None:
    if value in (None, ""):
        return None
    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError) as error:
        raise FeedbackValidationError("Identificador de chunk inválido.") from error


def _optional_text(value: object, max_length: int, label: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise FeedbackValidationError(f"{label} deve ser texto.")
    text = value.strip()
    if not text:
        return None
    if len(text) > max_length:
        raise FeedbackValidationError(
            f"{label} deve ter no máximo {max_length} caracteres."
        )
    return text


def _minimize_text(value: str | None) -> str | None:
    if value is None:
        return None
    patterns = (
        r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b",
        r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b",
        r"(?<!\d)(?:\+?55\s*)?(?:\(?\d{2}\)?\s*)?9?\d{4}[-\s]?\d{4}(?!\d)",
        r"\b\d{5}-?\d{3}\b",
    )
    minimized = value
    for pattern in patterns:
        minimized = re.sub(pattern, "[DADO_PESSOAL_REMOVIDO]", minimized)
    return re.sub(r"[ \t]+", " ", minimized)
