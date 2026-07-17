import hashlib
import json
import time
import uuid
from datetime import UTC, datetime

from flask import current_app
from sqlalchemy import select

from app.ai.provider import (
    AIProviderError,
    LocalTriageProvider,
    OllamaTriageProvider,
    TriageCategory,
    TriageInput,
    TriageProvider,
)
from app.extensions import db
from app.models import (
    AIExecution,
    AIExecutionStatus,
    NotificationType,
    OutboxEvent,
    RequestCategory,
    ServiceRequest,
)
from app.notifications.service import notify_user

AI_TRIAGE_EVENT = "TriagemIASolicitacao"
AI_TRIAGE_CASE_USE = "TRIAGEM_SOLICITACAO"


def triage_provider() -> TriageProvider:
    provider = current_app.config["AI_TRIAGE_PROVIDER"].lower()
    if provider == "local":
        return _local_provider()
    if provider == "ollama":
        return OllamaTriageProvider(
            base_url=current_app.config["OLLAMA_BASE_URL"],
            model=current_app.config["AI_TRIAGE_MODEL"],
            prompt_version=current_app.config["AI_TRIAGE_PROMPT_VERSION"],
            timeout_seconds=current_app.config["AI_TRIAGE_TIMEOUT_SECONDS"],
        )
    raise RuntimeError(f"Provedor de triagem não suportado: {provider}.")


def _local_provider() -> LocalTriageProvider:
    return LocalTriageProvider(
        model=current_app.config["AI_TRIAGE_FALLBACK_MODEL"],
        prompt_version=current_app.config["AI_TRIAGE_PROMPT_VERSION"],
    )


def create_triage_execution(
    service_request: ServiceRequest,
    requested_by_id: uuid.UUID,
) -> AIExecution:
    provider = triage_provider()
    input_data = {
        "title": service_request.title or "",
        "description": service_request.description,
    }
    execution = AIExecution(
        tenant_id=service_request.tenant_id,
        request_id=service_request.id,
        case_use=AI_TRIAGE_CASE_USE,
        provider=provider.provider,
        model=provider.model,
        prompt_version=provider.prompt_version,
        input_hash=hashlib.sha256(
            json.dumps(input_data, sort_keys=True, ensure_ascii=False).encode("utf-8")
        ).hexdigest(),
        requested_by_id=requested_by_id,
    )
    db.session.add(execution)
    db.session.flush()
    return execution


def enqueue_triage_execution(
    service_request: ServiceRequest,
    requested_by_id: uuid.UUID,
) -> AIExecution:
    execution = create_triage_execution(service_request, requested_by_id)
    db.session.add(
        OutboxEvent(
            tenant_id=service_request.tenant_id,
            event_type=AI_TRIAGE_EVENT,
            aggregate_type="ExecucaoIA",
            aggregate_id=str(execution.id),
            payload={"executionId": str(execution.id)},
        )
    )
    return execution


def execute_triage(execution: AIExecution) -> None:
    service_request = db.session.get(ServiceRequest, execution.request_id)
    if service_request is None or service_request.tenant_id != execution.tenant_id:
        raise RuntimeError("Solicitação da triagem não foi encontrada.")

    categories = tuple(
        TriageCategory(id=str(item.id), name=item.name)
        for item in db.session.execute(
            select(RequestCategory).where(
                RequestCategory.tenant_id == execution.tenant_id,
                RequestCategory.active.is_(True),
            )
        ).scalars()
    )
    execution.status = AIExecutionStatus.PROCESSANDO
    execution.started_at = datetime.now(UTC)
    db.session.flush()
    started = time.perf_counter()
    triage_input = TriageInput(
        title=service_request.title or "",
        description=service_request.description,
        categories=categories,
    )
    provider = triage_provider()
    used_fallback = False
    try:
        result = provider.classify(triage_input)
    except AIProviderError as error:
        if not current_app.config["AI_TRIAGE_FALLBACK_ENABLED"]:
            raise
        current_app.logger.warning(
            "Falha no provider %s; usando fallback local: %s",
            provider.provider,
            error,
        )
        provider = _local_provider()
        result = provider.classify(triage_input)
        used_fallback = True
        execution.error = str(error)
    execution.provider = provider.provider if not used_fallback else "LOCAL_FALLBACK"
    execution.model = provider.model
    execution.output = {
        "categoriaId": result.category_id,
        "categoria": result.category,
        "subcategoria": result.subcategory,
        "prioridadeSugerida": result.priority,
        "impacto": result.impact,
        "urgencia": result.urgency,
        "resumo": result.summary,
        "justificativa": result.rationale,
        "emergencia": result.emergency,
        "orientacaoEmergencia": result.emergency_guidance,
        "entidades": result.entities,
        "revisaoHumanaObrigatoria": True,
        "fallbackUtilizado": used_fallback,
    }
    execution.confidence = result.confidence
    execution.latency_ms = max(1, round((time.perf_counter() - started) * 1000))
    execution.estimated_cost = 0
    execution.status = AIExecutionStatus.CONCLUIDA
    execution.completed_at = datetime.now(UTC)
    db.session.add(
        OutboxEvent(
            tenant_id=execution.tenant_id,
            event_type="ClassificacaoConcluida",
            aggregate_type="Solicitacao",
            aggregate_id=str(service_request.id),
            payload={
                "executionId": str(execution.id),
                "requestId": str(service_request.id),
                "confidence": result.confidence,
                "emergency": result.emergency,
            },
        )
    )
    notify_user(
        execution.tenant_id,
        execution.requested_by_id,
        NotificationType.SISTEMA,
        "Triagem assistida concluída",
        f"A solicitação {service_request.protocol} possui uma sugestão aguardando revisão.",
        "ai_execution",
        execution.id,
    )


def execution_data(execution: AIExecution | None) -> dict | None:
    if execution is None:
        return None
    return {
        "id": str(execution.id),
        "casoUso": execution.case_use,
        "provedor": execution.provider,
        "modelo": execution.model,
        "versaoPrompt": execution.prompt_version,
        "status": execution.status.value,
        "statusRevisao": execution.review_status.value,
        "resultado": execution.output,
        "confianca": execution.confidence,
        "erro": execution.error,
        "latenciaMs": execution.latency_ms,
        "custoEstimado": execution.estimated_cost,
        "criadaEm": execution.created_at.isoformat(),
        "concluidaEm": execution.completed_at.isoformat() if execution.completed_at else None,
        "revisadaEm": execution.reviewed_at.isoformat() if execution.reviewed_at else None,
    }


def latest_triage_execution(
    tenant_id: uuid.UUID,
    request_id: uuid.UUID,
) -> AIExecution | None:
    return db.session.execute(
        select(AIExecution)
        .where(
            AIExecution.tenant_id == tenant_id,
            AIExecution.request_id == request_id,
            AIExecution.case_use == AI_TRIAGE_CASE_USE,
        )
        .order_by(AIExecution.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()
