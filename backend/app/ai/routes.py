import uuid
from datetime import UTC, datetime, timedelta

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt, get_jwt_identity, jwt_required
from sqlalchemy import select

from app.ai.service import (
    enqueue_triage_execution,
    execution_data,
    latest_triage_execution,
)
from app.audit import add_audit
from app.extensions import db
from app.models import (
    AIExecution,
    AIExecutionStatus,
    AIReviewStatus,
    RequestCategory,
    RequestHistory,
    RequestPriority,
    ServiceRequest,
)

ai_bp = Blueprint("ai", __name__)
REVIEW_ACTIONS = {
    "ACEITAR": AIReviewStatus.ACEITA,
    "EDITAR": AIReviewStatus.EDITADA,
    "REJEITAR": AIReviewStatus.REJEITADA,
}
LEVELS = {"BAIXO", "MEDIO", "ALTO", "CRITICO"}


def _context() -> tuple[uuid.UUID, uuid.UUID]:
    return uuid.UUID(get_jwt()["tenant_id"]), uuid.UUID(get_jwt_identity())


@ai_bp.post("/solicitacoes/<uuid:request_id>/classificacao-ia")
@jwt_required()
def request_triage(request_id: uuid.UUID):
    tenant_id, user_id = _context()
    service_request = _service_request(tenant_id, request_id)
    if service_request is None:
        return jsonify(error="resource_not_found", message="Solicitação não encontrada."), 404
    current = latest_triage_execution(tenant_id, request_id)
    if current is not None and current.status in {
        AIExecutionStatus.PENDENTE,
        AIExecutionStatus.PROCESSANDO,
    }:
        return jsonify(execution_data(current)), 202

    execution = enqueue_triage_execution(service_request, user_id)
    details = {
        "execucaoId": str(execution.id),
        "modelo": execution.model,
        "versaoPrompt": execution.prompt_version,
    }
    db.session.add(
        RequestHistory(
            tenant_id=tenant_id,
            request_id=request_id,
            user_id=user_id,
            action="request.ai_triage.requested",
            changes=details,
        )
    )
    add_audit(
        tenant_id,
        user_id,
        "request.ai_triage.requested",
        "service_request",
        request_id,
        after=details,
    )
    db.session.commit()
    return jsonify(execution_data(execution)), 202


@ai_bp.post("/classificacoes-ia/<uuid:execution_id>/revisao")
@jwt_required()
def review_triage(execution_id: uuid.UUID):
    tenant_id, user_id = _context()
    execution = db.session.execute(
        select(AIExecution).where(
            AIExecution.id == execution_id,
            AIExecution.tenant_id == tenant_id,
        )
    ).scalar_one_or_none()
    if execution is None:
        return jsonify(error="resource_not_found", message="Sugestão não encontrada."), 404
    if execution.status != AIExecutionStatus.CONCLUIDA:
        return jsonify(error="conflict", message="A triagem ainda não foi concluída."), 409
    if execution.review_status != AIReviewStatus.PENDENTE:
        return jsonify(error="conflict", message="A sugestão já foi revisada."), 409

    payload = request.get_json(silent=True) or {}
    action = str(payload.get("acao", "")).upper()
    review_status = REVIEW_ACTIONS.get(action)
    if review_status is None:
        return jsonify(error="validation_error", message="Ação de revisão inválida."), 422

    service_request = _service_request(tenant_id, execution.request_id)
    if service_request is None:
        return jsonify(error="resource_not_found", message="Solicitação não encontrada."), 404
    applied = {}
    if action != "REJEITAR":
        values = execution.output or {}
        if action == "EDITAR":
            values = {**values, **(payload.get("valores") or {})}
        try:
            applied = _apply_review(service_request, tenant_id, values)
        except ValueError as error:
            return jsonify(error="validation_error", message=str(error)), 422

    execution.review_status = review_status
    execution.reviewed_by_id = user_id
    execution.reviewed_at = datetime.now(UTC)
    details = {
        "execucaoId": str(execution.id),
        "decisao": review_status.value,
        "valoresAplicados": applied,
    }
    db.session.add(
        RequestHistory(
            tenant_id=tenant_id,
            request_id=service_request.id,
            user_id=user_id,
            action=f"request.ai_triage.{review_status.value.lower()}",
            changes=details,
        )
    )
    add_audit(
        tenant_id,
        user_id,
        f"request.ai_triage.{review_status.value.lower()}",
        "ai_execution",
        execution.id,
        after=details,
    )
    db.session.commit()
    return jsonify(execution_data(execution))


def _apply_review(service_request: ServiceRequest, tenant_id: uuid.UUID, values: dict) -> dict:
    category = None
    category_id = values.get("categoriaId")
    if category_id:
        try:
            category_uuid = uuid.UUID(str(category_id))
        except ValueError as error:
            raise ValueError("Categoria sugerida inválida.") from error
        category = db.session.execute(
            select(RequestCategory).where(
                RequestCategory.id == category_uuid,
                RequestCategory.tenant_id == tenant_id,
                RequestCategory.active.is_(True),
            )
        ).scalar_one_or_none()
        if category is None:
            raise ValueError("Categoria sugerida não está disponível.")

    try:
        priority = RequestPriority(str(values.get("prioridadeSugerida", "MEDIA")).upper())
    except ValueError as error:
        raise ValueError("Prioridade sugerida inválida.") from error
    impact = str(values.get("impacto", "MEDIO")).upper()
    urgency = str(values.get("urgencia", "MEDIO")).upper()
    if impact not in LEVELS or urgency not in LEVELS:
        raise ValueError("Impacto ou urgência inválidos.")

    service_request.category_id = category.id if category else None
    service_request.category = category.name if category else None
    service_request.subcategory = str(values.get("subcategoria", "")).strip() or None
    service_request.priority = priority
    service_request.impact = impact
    service_request.urgency = urgency
    if category:
        service_request.due_at = service_request.created_at + timedelta(hours=category.sla_hours)
    return {
        "categoriaId": str(category.id) if category else None,
        "categoria": category.name if category else None,
        "subcategoria": service_request.subcategory,
        "prioridade": priority.value,
        "impacto": impact,
        "urgencia": urgency,
    }


def _service_request(tenant_id: uuid.UUID, request_id: uuid.UUID) -> ServiceRequest | None:
    return db.session.execute(
        select(ServiceRequest).where(
            ServiceRequest.id == request_id,
            ServiceRequest.tenant_id == tenant_id,
        )
    ).scalar_one_or_none()
