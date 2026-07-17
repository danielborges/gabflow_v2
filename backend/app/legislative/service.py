import hashlib
import json
import time
import uuid
from datetime import UTC, datetime

from flask import current_app
from sqlalchemy import select

from app.ai.provider import AIProviderError
from app.extensions import db
from app.legislative.foundation import foundation_retriever
from app.legislative.generator import (
    LegislativeInput,
    LegislativeProvider,
    LocalLegislativeProvider,
    OllamaLegislativeProvider,
)
from app.legislative.precedents import semantic_precedent_search
from app.models import (
    AIExecution,
    AIExecutionStatus,
    ExternalAgency,
    LegislativeDraft,
    LegislativeDraftRequest,
    LegislativeDraftVersion,
    LegislativeGenerationStatus,
    LegislativeTemplate,
    NotificationType,
    OutboxEvent,
    ServiceRequest,
)
from app.notifications.service import notify_user

LEGISLATIVE_GENERATION_EVENT = "GeracaoMinutaLegislativa"
LEGISLATIVE_CASE_USE = "PRODUCAO_LEGISLATIVA"


def legislative_provider() -> LegislativeProvider:
    provider = current_app.config["AI_LEGISLATIVE_PROVIDER"].lower()
    if provider == "local":
        return _local_provider()
    if provider == "ollama":
        return OllamaLegislativeProvider(
            base_url=current_app.config["OLLAMA_BASE_URL"],
            model=current_app.config["AI_LEGISLATIVE_MODEL"],
            prompt_version=current_app.config["AI_LEGISLATIVE_PROMPT_VERSION"],
            timeout_seconds=current_app.config["AI_LEGISLATIVE_TIMEOUT_SECONDS"],
        )
    raise RuntimeError(f"Provedor legislativo não suportado: {provider}.")


def _local_provider() -> LocalLegislativeProvider:
    return LocalLegislativeProvider(
        model=current_app.config["AI_LEGISLATIVE_FALLBACK_MODEL"],
        prompt_version=current_app.config["AI_LEGISLATIVE_PROMPT_VERSION"],
    )


def enqueue_generation(
    draft: LegislativeDraft,
    primary_request: ServiceRequest,
    requested_by_id: uuid.UUID,
    parameters: dict,
) -> AIExecution:
    provider = legislative_provider()
    digest = hashlib.sha256(
        json.dumps(parameters, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    execution = AIExecution(
        tenant_id=draft.tenant_id,
        request_id=primary_request.id,
        case_use=LEGISLATIVE_CASE_USE,
        provider=provider.provider,
        model=provider.model,
        prompt_version=provider.prompt_version,
        input_hash=digest,
        output={
            "minutaId": str(draft.id),
            "parametros": parameters,
            "rascunho": True,
            "protocoloAutomatico": False,
        },
        requested_by_id=requested_by_id,
    )
    db.session.add(execution)
    db.session.flush()
    draft.ai_execution_id = execution.id
    db.session.add(
        OutboxEvent(
            tenant_id=draft.tenant_id,
            event_type=LEGISLATIVE_GENERATION_EVENT,
            aggregate_type="MinutaLegislativa",
            aggregate_id=str(draft.id),
            payload={"executionId": str(execution.id), "draftId": str(draft.id)},
        )
    )
    return execution


def execute_generation(execution: AIExecution) -> None:
    draft = db.session.execute(
        select(LegislativeDraft).where(
            LegislativeDraft.ai_execution_id == execution.id,
            LegislativeDraft.tenant_id == execution.tenant_id,
        )
    ).scalar_one_or_none()
    if draft is None:
        raise RuntimeError("Minuta da execução não foi encontrada.")
    links = (
        db.session.execute(
            select(LegislativeDraftRequest).where(
                LegislativeDraftRequest.draft_id == draft.id,
                LegislativeDraftRequest.tenant_id == draft.tenant_id,
            )
        )
        .scalars()
        .all()
    )
    requests = (
        db.session.execute(
            select(ServiceRequest).where(
                ServiceRequest.id.in_([link.request_id for link in links]),
                ServiceRequest.tenant_id == draft.tenant_id,
            )
        )
        .scalars()
        .all()
    )
    if not requests:
        raise RuntimeError("A minuta não possui solicitação válida vinculada.")

    parameters = (execution.output or {}).get("parametros") or {}
    request_order = list(parameters.get("solicitacoesIds") or [])
    requests_by_id = {str(item.id): item for item in requests}
    ordered_requests = [
        requests_by_id[item_id] for item_id in request_order if item_id in requests_by_id
    ]
    ordered_ids = {item.id for item in ordered_requests}
    ordered_requests.extend(item for item in requests if item.id not in ordered_ids)
    template = db.session.get(LegislativeTemplate, draft.template_id) if draft.template_id else None
    agencies = {
        agency.id: agency.name
        for agency in db.session.execute(
            select(ExternalAgency).where(ExternalAgency.tenant_id == draft.tenant_id)
        ).scalars()
    }
    provider = legislative_provider()
    data = LegislativeInput(
        document_type=draft.document_type.value,
        title=draft.title,
        requests=tuple(
            {
                "id": str(item.id),
                "protocolo": item.protocol,
                "titulo": item.title,
                "descricao": item.description,
                "endereco": item.address,
                "categoria": item.category,
                "orgao": agencies.get(item.agency_id),
            }
            for item in ordered_requests
        ),
        selected_facts=tuple(parameters.get("fatosSelecionados") or ()),
        instructions=str(parameters.get("instrucoes") or "").strip() or None,
        template=template.structure if template and template.tenant_id == draft.tenant_id else None,
        normative_sources=tuple(parameters.get("fontesNormativas") or ()),
    )
    execution.status = AIExecutionStatus.PROCESSANDO
    execution.started_at = datetime.now(UTC)
    draft.generation_status = LegislativeGenerationStatus.PROCESSANDO
    db.session.flush()
    started = time.perf_counter()
    used_fallback = False
    try:
        result = provider.generate(data)
    except AIProviderError as error:
        if not current_app.config["AI_LEGISLATIVE_FALLBACK_ENABLED"]:
            raise
        current_app.logger.warning("Falha no provider legislativo; usando fallback: %s", error)
        provider = _local_provider()
        result = provider.generate(data)
        used_fallback = True
        execution.error = str(error)

    draft.title = result.title
    draft.content = result.content
    draft.justification = result.justification
    draft.legal_basis = result.legal_basis
    draft.sources = result.sources
    draft.unsupported_passages = result.unsupported_passages
    draft.similar_proposals = similar_proposals(
        draft.tenant_id, result.title, result.content, draft.id
    )
    foundation_recovery = foundation_retriever().retrieve(
        draft.tenant_id,
        "\n".join(
            value for value in (result.title, result.content, result.justification) if value
        ),
        current_app.config["AI_FOUNDATION_MAX_RESULTS"],
    )
    draft.generation_metadata = {
        "provedor": provider.provider,
        "modelo": provider.model,
        "versaoPrompt": provider.prompt_version,
        "confianca": result.confidence,
        "estruturaSugerida": result.suggested_structure,
        "guardrailsAplicados": result.guardrails,
        "fallbackUtilizado": used_fallback,
        "revisaoHumanaObrigatoria": True,
        "protocoloAutomatico": False,
        "solicitacaoPrincipalId": parameters.get("solicitacaoPrincipalId"),
        "solicitacoesIds": request_order,
        "recuperacaoFundamentacao": foundation_recovery,
    }
    draft.generation_status = LegislativeGenerationStatus.CONCLUIDA
    draft.error = None
    save_version(draft, execution.requested_by_id, "Versão inicial gerada pela IA")

    execution.provider = "LOCAL_FALLBACK" if used_fallback else provider.provider
    execution.model = provider.model
    execution.confidence = result.confidence
    execution.latency_ms = max(1, round((time.perf_counter() - started) * 1000))
    execution.estimated_cost = 0
    execution.status = AIExecutionStatus.CONCLUIDA
    execution.completed_at = datetime.now(UTC)
    execution.output = {
        "minutaId": str(draft.id),
        "titulo": draft.title,
        "fontes": draft.sources,
        "trechosSemFundamentacao": draft.unsupported_passages,
        "proposicoesSemelhantes": draft.similar_proposals,
        "guardrailsAplicados": result.guardrails,
        "rascunho": True,
        "revisaoHumanaObrigatoria": True,
        "protocoloAutomatico": False,
        "fallbackUtilizado": used_fallback,
    }
    notify_user(
        draft.tenant_id,
        execution.requested_by_id,
        NotificationType.SISTEMA,
        "Minuta legislativa pronta",
        f"A minuta “{draft.title}” está disponível para revisão.",
        "legislative_draft",
        draft.id,
    )


def fail_generation(execution: AIExecution, error_message: str) -> None:
    execution.status = AIExecutionStatus.FALHOU
    execution.error = error_message[:2000]
    draft = db.session.execute(
        select(LegislativeDraft).where(LegislativeDraft.ai_execution_id == execution.id)
    ).scalar_one_or_none()
    if draft:
        draft.generation_status = LegislativeGenerationStatus.FALHOU
        draft.error = error_message[:2000]


def save_version(draft: LegislativeDraft, user_id: uuid.UUID, reason: str) -> None:
    draft.current_version += 1
    db.session.add(
        LegislativeDraftVersion(
            tenant_id=draft.tenant_id,
            draft_id=draft.id,
            version_number=draft.current_version,
            title=draft.title,
            content=draft.content or "",
            justification=draft.justification,
            legal_basis=draft.legal_basis,
            unsupported_passages=draft.unsupported_passages,
            change_reason=reason[:500],
            created_by_id=user_id,
        )
    )


def similar_proposals(
    tenant_id: uuid.UUID,
    title: str,
    content: str,
    exclude_id: uuid.UUID | None = None,
) -> list[dict]:
    query = f"{title}\n{content}".strip()
    if not query:
        return []
    return semantic_precedent_search(
        tenant_id, query, exclude_id=exclude_id, limit=5
    )["content"]
