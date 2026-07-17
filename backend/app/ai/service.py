import hashlib
import json
import time
import uuid
from datetime import UTC, datetime, timedelta

from flask import current_app
from sqlalchemy import select

from app.ai.assistance import (
    AssistanceInput,
    AssistanceProvider,
    LocalAssistanceProvider,
    OllamaAssistanceProvider,
)
from app.ai.duplicates import duplicate_suggestions
from app.ai.provider import (
    AIProviderError,
    LocalTriageProvider,
    OllamaTriageProvider,
    TriageAgency,
    TriageCategory,
    TriageInput,
    TriageProvider,
)
from app.extensions import db
from app.models import (
    AIExecution,
    AIExecutionStatus,
    AIReviewStatus,
    AudioTranscription,
    AudioTranscriptionReviewStatus,
    AudioTranscriptionStatus,
    Citizen,
    DocumentOcr,
    DocumentOcrReviewStatus,
    DocumentOcrStatus,
    ExternalAgency,
    NotificationType,
    OutboxEvent,
    RequestCategory,
    ServiceRequest,
)
from app.notifications.service import notify_user

AI_TRIAGE_EVENT = "TriagemIASolicitacao"
AI_TRIAGE_CASE_USE = "TRIAGEM_SOLICITACAO"
AI_ASSISTANCE_EVENT = "AssistenciaIASolicitacao"
AI_ASSISTANCE_CASE_USE = "ASSISTENCIA_ATENDIMENTO"


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


def assistance_provider() -> AssistanceProvider:
    provider = current_app.config["AI_ASSISTANCE_PROVIDER"].lower()
    if provider == "local":
        return _local_assistance_provider()
    if provider == "ollama":
        return OllamaAssistanceProvider(
            base_url=current_app.config["OLLAMA_BASE_URL"],
            model=current_app.config["AI_ASSISTANCE_MODEL"],
            prompt_version=current_app.config["AI_ASSISTANCE_PROMPT_VERSION"],
            timeout_seconds=current_app.config["AI_ASSISTANCE_TIMEOUT_SECONDS"],
        )
    raise RuntimeError(f"Provedor de assistência não suportado: {provider}.")


def _local_assistance_provider() -> LocalAssistanceProvider:
    return LocalAssistanceProvider(
        model=current_app.config["AI_ASSISTANCE_FALLBACK_MODEL"],
        prompt_version=current_app.config["AI_ASSISTANCE_PROMPT_VERSION"],
    )


def enqueue_assistance_execution(
    service_request: ServiceRequest,
    requested_by_id: uuid.UUID,
    channel: str,
    tone: str,
) -> AIExecution:
    provider = assistance_provider()
    parameters = {"canal": channel, "tom": tone}
    input_data = {
        "requestId": str(service_request.id),
        "updatedAt": service_request.updated_at.isoformat(),
        **parameters,
    }
    execution = AIExecution(
        tenant_id=service_request.tenant_id,
        request_id=service_request.id,
        case_use=AI_ASSISTANCE_CASE_USE,
        provider=provider.provider,
        model=provider.model,
        prompt_version=provider.prompt_version,
        input_hash=hashlib.sha256(
            json.dumps(input_data, sort_keys=True, ensure_ascii=False).encode("utf-8")
        ).hexdigest(),
        output={"parametros": parameters, "envioAutomatico": False},
        requested_by_id=requested_by_id,
    )
    db.session.add(execution)
    db.session.flush()
    db.session.add(
        OutboxEvent(
            tenant_id=service_request.tenant_id,
            event_type=AI_ASSISTANCE_EVENT,
            aggregate_type="ExecucaoIA",
            aggregate_id=str(execution.id),
            payload={"executionId": str(execution.id)},
        )
    )
    return execution


def execute_assistance(execution: AIExecution) -> None:
    service_request = db.session.get(ServiceRequest, execution.request_id)
    if service_request is None or service_request.tenant_id != execution.tenant_id:
        raise RuntimeError("Solicitação da assistência não foi encontrada.")
    parameters = (execution.output or {}).get("parametros") or {}
    citizen = (
        db.session.get(Citizen, service_request.citizen_id) if service_request.citizen_id else None
    )
    agency = (
        db.session.get(ExternalAgency, service_request.agency_id)
        if service_request.agency_id
        else None
    )
    assistance_input = AssistanceInput(
        protocol=service_request.protocol,
        title=service_request.title or "Solicitação sem título",
        description=service_request.description,
        status=service_request.status.value,
        category=service_request.category,
        subcategory=service_request.subcategory,
        agency=agency.name if agency and agency.tenant_id == execution.tenant_id else None,
        address=service_request.address,
        citizen_name=(
            citizen.social_name or citizen.name
            if citizen and citizen.tenant_id == execution.tenant_id
            else None
        ),
        channel=str(parameters.get("canal", "WHATSAPP")),
        tone=str(parameters.get("tom", "ACOLHEDOR")),
        interactions=tuple(
            {
                "tipo": item.interaction_type,
                "direcao": item.direction.value,
                "conteudo": item.content[:1200],
                "criadaEm": item.created_at.isoformat(),
            }
            for item in service_request.interactions[-20:]
        ),
        history=tuple(
            {
                "acao": item.action,
                "alteracoes": item.changes,
                "criadaEm": item.created_at.isoformat(),
            }
            for item in service_request.history[-20:]
        ),
    )
    execution.status = AIExecutionStatus.PROCESSANDO
    execution.started_at = datetime.now(UTC)
    db.session.flush()
    started = time.perf_counter()
    provider = assistance_provider()
    used_fallback = False
    try:
        result = provider.suggest(assistance_input)
    except AIProviderError as error:
        if not current_app.config["AI_ASSISTANCE_FALLBACK_ENABLED"]:
            raise
        current_app.logger.warning(
            "Falha no provider de assistência %s; usando fallback local: %s",
            provider.provider,
            error,
        )
        provider = _local_assistance_provider()
        result = provider.suggest(assistance_input)
        used_fallback = True
        execution.error = str(error)
    execution.provider = provider.provider if not used_fallback else "LOCAL_FALLBACK"
    execution.model = provider.model
    execution.output = {
        "resumoHistorico": result.history_summary,
        "perguntasFaltantes": result.missing_questions,
        "documentosNecessarios": result.required_documents,
        "proximosPassos": result.next_steps,
        "respostaSugerida": result.suggested_response,
        "alertas": result.alerts,
        "guardrailsAplicados": result.guardrails,
        "revisaoHumanaObrigatoria": True,
        "envioAutomatico": False,
        "fallbackUtilizado": used_fallback,
    }
    execution.confidence = result.confidence
    execution.latency_ms = max(1, round((time.perf_counter() - started) * 1000))
    execution.estimated_cost = 0
    execution.status = AIExecutionStatus.CONCLUIDA
    execution.completed_at = datetime.now(UTC)
    notify_user(
        execution.tenant_id,
        execution.requested_by_id,
        NotificationType.SISTEMA,
        "Assistência de atendimento concluída",
        f"As sugestões para {service_request.protocol} estão prontas para revisão.",
        "ai_execution",
        execution.id,
    )


def latest_assistance_execution(
    tenant_id: uuid.UUID,
    request_id: uuid.UUID,
) -> AIExecution | None:
    return db.session.execute(
        select(AIExecution)
        .where(
            AIExecution.tenant_id == tenant_id,
            AIExecution.request_id == request_id,
            AIExecution.case_use == AI_ASSISTANCE_CASE_USE,
        )
        .order_by(AIExecution.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()


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
    agencies = tuple(
        TriageAgency(id=str(item.id), name=item.name)
        for item in db.session.execute(
            select(ExternalAgency).where(
                ExternalAgency.tenant_id == execution.tenant_id,
                ExternalAgency.active.is_(True),
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
        agencies=agencies,
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
    duplicates = duplicate_suggestions(service_request)
    execution.output = {
        "categoriaId": result.category_id,
        "categoria": result.category,
        "subcategoria": result.subcategory,
        "orgaoId": result.agency_id,
        "orgao": result.agency,
        "prioridadeSugerida": result.priority,
        "impacto": result.impact,
        "urgencia": result.urgency,
        "resumo": result.summary,
        "resumoEstruturado": result.structured_summary,
        "justificativa": result.rationale,
        "conteudoOfensivo": result.offensive_content,
        "marcadoresConteudo": result.content_markers,
        "emergencia": result.emergency,
        "orientacaoEmergencia": result.emergency_guidance,
        "entidades": result.entities,
        "analiseDuplicidade": duplicates,
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


def triage_quality_data(tenant_id: uuid.UUID, days: int) -> dict:
    since = datetime.now(UTC) - timedelta(days=days)
    executions = list(
        db.session.execute(
            select(AIExecution).where(
                AIExecution.tenant_id == tenant_id,
                AIExecution.case_use == AI_TRIAGE_CASE_USE,
                AIExecution.created_at >= since,
            )
        ).scalars()
    )
    transcriptions = list(
        db.session.execute(
            select(AudioTranscription).where(
                AudioTranscription.tenant_id == tenant_id,
                AudioTranscription.created_at >= since,
            )
        ).scalars()
    )
    completed_transcriptions = [
        item for item in transcriptions if item.status == AudioTranscriptionStatus.CONCLUIDA
    ]
    reviewed_transcriptions = [
        item
        for item in completed_transcriptions
        if item.review_status != AudioTranscriptionReviewStatus.PENDENTE
    ]
    ocr_executions = list(
        db.session.execute(
            select(DocumentOcr).where(
                DocumentOcr.tenant_id == tenant_id,
                DocumentOcr.created_at >= since,
            )
        ).scalars()
    )
    completed_ocr = [item for item in ocr_executions if item.status == DocumentOcrStatus.CONCLUIDO]
    reviewed_ocr = [
        item for item in completed_ocr if item.review_status != DocumentOcrReviewStatus.PENDENTE
    ]
    completed = [item for item in executions if item.status == AIExecutionStatus.CONCLUIDA]
    reviewed = [item for item in completed if item.review_status != AIReviewStatus.PENDENTE]
    accepted = [item for item in reviewed if item.review_status == AIReviewStatus.ACEITA]
    edited = [item for item in reviewed if item.review_status == AIReviewStatus.EDITADA]
    rejected = [item for item in reviewed if item.review_status == AIReviewStatus.REJEITADA]
    fallback = [item for item in completed if item.provider == "LOCAL_FALLBACK"]
    entity_results = [item for item in completed if _has_entities(item.output)]
    agency_results = [item for item in completed if (item.output or {}).get("orgaoId")]
    offensive_results = [item for item in completed if (item.output or {}).get("conteudoOfensivo")]
    emergency_results = [item for item in completed if (item.output or {}).get("emergencia")]
    duplicate_analyses = [
        item for item in completed if (item.output or {}).get("analiseDuplicidade") is not None
    ]
    duplicate_candidates = sum(
        len(((item.output or {}).get("analiseDuplicidade") or {}).get("candidatos") or [])
        for item in duplicate_analyses
    )
    category_reviews = [*accepted, *edited]
    category_matches = [item for item in category_reviews if _category_agreed(item)]

    models: dict[tuple[str, str], list[AIExecution]] = {}
    for execution in executions:
        models.setdefault((execution.provider, execution.model), []).append(execution)

    return {
        "periodoDias": days,
        "geradoEm": datetime.now(UTC).isoformat(),
        "amostraMinimaAtingida": len(reviewed) >= 30,
        "indicadores": {
            "execucoes": len(executions),
            "concluidas": len(completed),
            "falhas": sum(item.status == AIExecutionStatus.FALHOU for item in executions),
            "revisadas": len(reviewed),
            "confiancaMedia": _average(item.confidence for item in completed),
            "latenciaMediaMs": _average(item.latency_ms for item in completed),
            "taxaConclusao": _rate(len(completed), len(executions)),
            "taxaAceitacao": _rate(len(accepted), len(reviewed)),
            "taxaIntervencaoHumana": _rate(len(edited) + len(rejected), len(reviewed)),
            "taxaFallback": _rate(len(fallback), len(completed)),
            "concordanciaCategoria": _rate(len(category_matches), len(category_reviews)),
        },
        "revisoes": {
            "pendentes": len(completed) - len(reviewed),
            "aceitas": len(accepted),
            "editadas": len(edited),
            "rejeitadas": len(rejected),
        },
        "cobertura": {
            "entidadesExtraidas": len(entity_results),
            "orgaosSugeridos": len(agency_results),
            "conteudoOfensivoSinalizado": len(offensive_results),
            "emergenciasSinalizadas": len(emergency_results),
            "analisesDuplicidade": len(duplicate_analyses),
            "candidatosDuplicidade": duplicate_candidates,
            "audiosTranscritos": len(completed_transcriptions),
            "transcricoesRevisadas": len(reviewed_transcriptions),
            "falhasTranscricao": sum(
                item.status == AudioTranscriptionStatus.FALHOU for item in transcriptions
            ),
            "documentosProcessadosOcr": len(completed_ocr),
            "ocrRevisados": len(reviewed_ocr),
            "confiancaMediaOcr": _average(item.confidence for item in completed_ocr),
            "falhasOcr": sum(item.status == DocumentOcrStatus.FALHOU for item in ocr_executions),
        },
        "porModelo": [
            {
                "provedor": provider,
                "modelo": model,
                "execucoes": len(items),
                "concluidas": sum(item.status == AIExecutionStatus.CONCLUIDA for item in items),
                "confiancaMedia": _average(item.confidence for item in items),
                "latenciaMediaMs": _average(item.latency_ms for item in items),
            }
            for (provider, model), items in sorted(models.items())
        ],
    }


def _has_entities(output: dict | None) -> bool:
    entities = (output or {}).get("entidades") or {}
    return any(value for value in entities.values())


def _category_agreed(execution: AIExecution) -> bool:
    if execution.review_status == AIReviewStatus.ACEITA:
        return True
    output = execution.output or {}
    applied = (output.get("revisao") or {}).get("valoresAplicados") or {}
    return output.get("categoriaId") == applied.get("categoriaId")


def _average(values) -> float | int | None:
    numbers = [float(value) for value in values if value is not None]
    if not numbers:
        return None
    result = sum(numbers) / len(numbers)
    return round(result, 2)


def _rate(part: int, total: int) -> float | None:
    return round(part / total, 4) if total else None
