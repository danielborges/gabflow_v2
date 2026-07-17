import uuid
from datetime import UTC, datetime, timedelta

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt, get_jwt_identity, jwt_required
from sqlalchemy import select

from app.ai.service import (
    AI_ASSISTANCE_CASE_USE,
    enqueue_assistance_execution,
    enqueue_triage_execution,
    execution_data,
    latest_assistance_execution,
    latest_triage_execution,
    triage_quality_data,
)
from app.audit import add_audit
from app.extensions import db
from app.models import (
    AIExecution,
    AIExecutionStatus,
    AIReviewStatus,
    ExternalAgency,
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
ASSISTANCE_CHANNELS = {"WHATSAPP", "EMAIL", "TELEFONE", "PRESENCIAL", "INTERNO"}
ASSISTANCE_TONES = {"ACOLHEDOR", "CLARO", "FORMAL", "OBJETIVO"}


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


@ai_bp.post("/solicitacoes/<uuid:request_id>/assistencia-ia")
@jwt_required()
def request_assistance(request_id: uuid.UUID):
    tenant_id, user_id = _context()
    service_request = _service_request(tenant_id, request_id)
    if service_request is None:
        return jsonify(error="resource_not_found", message="Solicitação não encontrada."), 404
    current = latest_assistance_execution(tenant_id, request_id)
    if current is not None and current.status in {
        AIExecutionStatus.PENDENTE,
        AIExecutionStatus.PROCESSANDO,
    }:
        return jsonify(execution_data(current)), 202

    payload = request.get_json(silent=True) or {}
    channel = str(payload.get("canal", "WHATSAPP")).upper()
    tone = str(payload.get("tom", "ACOLHEDOR")).upper()
    if channel not in ASSISTANCE_CHANNELS:
        return jsonify(error="validation_error", message="Canal da resposta inválido."), 422
    if tone not in ASSISTANCE_TONES:
        return jsonify(error="validation_error", message="Tom da resposta inválido."), 422

    execution = enqueue_assistance_execution(service_request, user_id, channel, tone)
    details = {
        "execucaoId": str(execution.id),
        "modelo": execution.model,
        "versaoPrompt": execution.prompt_version,
        "canal": channel,
        "tom": tone,
        "envioAutomatico": False,
    }
    db.session.add(
        RequestHistory(
            tenant_id=tenant_id,
            request_id=request_id,
            user_id=user_id,
            action="request.ai_assistance.requested",
            changes=details,
        )
    )
    add_audit(
        tenant_id,
        user_id,
        "request.ai_assistance.requested",
        "service_request",
        request_id,
        after=details,
    )
    db.session.commit()
    return jsonify(execution_data(execution)), 202


@ai_bp.post("/assistencias-ia/<uuid:execution_id>/revisao")
@jwt_required()
def review_assistance(execution_id: uuid.UUID):
    tenant_id, user_id = _context()
    execution = db.session.execute(
        select(AIExecution).where(
            AIExecution.id == execution_id,
            AIExecution.tenant_id == tenant_id,
            AIExecution.case_use == AI_ASSISTANCE_CASE_USE,
        )
    ).scalar_one_or_none()
    if execution is None:
        return jsonify(error="resource_not_found", message="Assistência não encontrada."), 404
    if execution.status != AIExecutionStatus.CONCLUIDA:
        return jsonify(error="conflict", message="A assistência ainda não foi concluída."), 409
    if execution.review_status != AIReviewStatus.PENDENTE:
        return jsonify(error="conflict", message="A assistência já foi revisada."), 409

    payload = request.get_json(silent=True) or {}
    action = str(payload.get("acao", "")).upper()
    review_status = REVIEW_ACTIONS.get(action)
    if review_status is None:
        return jsonify(error="validation_error", message="Ação de revisão inválida."), 422
    output = execution.output or {}
    response_data = output.get("respostaSugerida") or {}
    if action == "EDITAR":
        values = payload.get("valores") or {}
        content = str(values.get("conteudo", "")).strip()
        if not content:
            return jsonify(
                error="validation_error", message="A resposta revisada é obrigatória."
            ), 422
        response_data = {
            **response_data,
            "canal": str(values.get("canal", response_data.get("canal", "WHATSAPP"))).upper(),
            "assunto": str(values.get("assunto", response_data.get("assunto") or "")).strip()
            or None,
            "conteudo": content,
        }
        if response_data["canal"] not in ASSISTANCE_CHANNELS:
            return jsonify(error="validation_error", message="Canal da resposta inválido."), 422

    execution.review_status = review_status
    execution.reviewed_by_id = user_id
    execution.reviewed_at = datetime.now(UTC)
    execution.output = {
        **output,
        "respostaSugerida": response_data,
        "envioAutomatico": False,
        "revisao": {
            "decisao": review_status.value,
            "revisadaEm": execution.reviewed_at.isoformat(),
            "aplicadaAoFormulario": action != "REJEITAR",
            "enviada": False,
        },
    }
    details = {
        "execucaoId": str(execution.id),
        "decisao": review_status.value,
        "aplicadaAoFormulario": action != "REJEITAR",
        "enviada": False,
    }
    db.session.add(
        RequestHistory(
            tenant_id=tenant_id,
            request_id=execution.request_id,
            user_id=user_id,
            action=f"request.ai_assistance.{review_status.value.lower()}",
            changes=details,
        )
    )
    add_audit(
        tenant_id,
        user_id,
        f"request.ai_assistance.{review_status.value.lower()}",
        "ai_execution",
        execution.id,
        after=details,
    )
    db.session.commit()
    return jsonify(execution_data(execution))


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
    execution.output = {
        **(execution.output or {}),
        "revisao": {
            "decisao": review_status.value,
            "valoresAplicados": applied,
            "revisadaEm": execution.reviewed_at.isoformat(),
        },
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


@ai_bp.get("/ia/qualidade-triagem")
@jwt_required()
def triage_quality():
    tenant_id, _ = _context()
    try:
        days = int(request.args.get("dias", "30"))
    except ValueError:
        return jsonify(error="validation_error", message="Período inválido."), 422
    if days not in {30, 90, 180, 365}:
        return jsonify(error="validation_error", message="Período não suportado."), 422
    return jsonify(triage_quality_data(tenant_id, days))


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

    agency = None
    agency_id = values.get("orgaoId")
    if agency_id:
        try:
            agency_uuid = uuid.UUID(str(agency_id))
        except ValueError as error:
            raise ValueError("Órgão sugerido inválido.") from error
        agency = db.session.execute(
            select(ExternalAgency).where(
                ExternalAgency.id == agency_uuid,
                ExternalAgency.tenant_id == tenant_id,
                ExternalAgency.active.is_(True),
            )
        ).scalar_one_or_none()
        if agency is None:
            raise ValueError("Órgão sugerido não está disponível.")

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
    service_request.agency_id = agency.id if agency else None
    service_request.priority = priority
    service_request.impact = impact
    service_request.urgency = urgency
    if category:
        service_request.due_at = service_request.created_at + timedelta(hours=category.sla_hours)
    return {
        "categoriaId": str(category.id) if category else None,
        "categoria": category.name if category else None,
        "subcategoria": service_request.subcategory,
        "orgaoId": str(agency.id) if agency else None,
        "orgao": agency.name if agency else None,
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
