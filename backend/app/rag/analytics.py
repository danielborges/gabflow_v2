import re
import unicodedata
import uuid
from collections import defaultdict
from datetime import UTC, date, datetime, time, timedelta

from flask import current_app
from sqlalchemy import select

from app.extensions import db
from app.models import (
    AgendaEvent,
    Citizen,
    ExternalAgency,
    LegislativeTramitation,
    OversightAction,
    RagThematicMemory,
    RequestForwarding,
    RequestPriority,
    RequestStatus,
    ServiceRequest,
    Territory,
)

DATASETS = {
    "CIDADAOS": (Citizen, Citizen.created_at),
    "SOLICITACOES": (ServiceRequest, ServiceRequest.created_at),
    "ENCAMINHAMENTOS": (RequestForwarding, RequestForwarding.created_at),
    "TRAMITACOES": (LegislativeTramitation, LegislativeTramitation.occurred_at),
    "AGENDA": (AgendaEvent, AgendaEvent.starts_at),
    "FISCALIZACOES": (OversightAction, OversightAction.created_at),
}
METRICS = {"CONTAGEM", "PRAZOS_VENCIDOS", "TEMPO_MEDIO_RESOLUCAO_HORAS"}
GROUPS = {
    "NENHUM",
    "STATUS",
    "TEMA",
    "TERRITORIO",
    "ORGAO",
    "TIPO",
    "ETAPA",
    "MES",
}


def rebuild_thematic_memories(
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    *,
    period_start: date,
    period_end: date,
) -> list[RagThematicMemory]:
    if period_start > period_end:
        raise ValueError("O início do período deve ser anterior ou igual ao fim.")
    starts_at = datetime.combine(period_start, time.min, tzinfo=UTC)
    ends_before = datetime.combine(period_end + timedelta(days=1), time.min, tzinfo=UTC)
    requests = list(
        db.session.scalars(
            select(ServiceRequest).where(
                ServiceRequest.tenant_id == tenant_id,
                ServiceRequest.created_at >= starts_at,
                ServiceRequest.created_at < ends_before,
                ServiceRequest.status != RequestStatus.CANCELADA,
            )
        )
    )
    territories = {
        item.id: item.name
        for item in db.session.scalars(
            select(Territory).where(Territory.tenant_id == tenant_id)
        )
    }
    grouped: dict[tuple[str, str], list[ServiceRequest]] = defaultdict(list)
    for item in requests:
        theme = _group_label(item.theme or item.category or "Sem tema", 120)
        territory = _group_label(territories.get(item.territory_id, ""), 160)
        grouped[(theme, territory)].append(item)

    minimum = max(2, int(current_app.config["RAG_THEMATIC_MIN_GROUP_SIZE"]))
    existing = {
        (item.theme, item.territory): item
        for item in db.session.scalars(
            select(RagThematicMemory).where(
                RagThematicMemory.tenant_id == tenant_id,
                RagThematicMemory.period_start == period_start,
                RagThematicMemory.period_end == period_end,
            )
        )
    }
    generated: list[RagThematicMemory] = []
    eligible_keys = {
        key for key, items in grouped.items() if len(items) >= minimum
    }
    for key, item in existing.items():
        if key not in eligible_keys:
            db.session.delete(item)

    now = datetime.now(UTC)
    for (theme, territory), items in sorted(grouped.items()):
        if len(items) < minimum:
            continue
        resolved = sum(
            item.status in {RequestStatus.RESOLVIDA, RequestStatus.ENCERRADA}
            for item in items
        )
        high_priority = sum(
            item.priority in {RequestPriority.ALTA, RequestPriority.CRITICA}
            for item in items
        )
        summary = (
            f"No período, o tema {theme} registrou {len(items)} solicitações"
            f"{f' no território {territory}' if territory else ''}; "
            f"{resolved} foram resolvidas ou encerradas e "
            f"{high_priority} tiveram prioridade alta ou crítica."
        )
        memory = existing.get((theme, territory))
        if memory is None:
            memory = RagThematicMemory(
                tenant_id=tenant_id,
                theme=theme,
                territory=territory,
                period_start=period_start,
                period_end=period_end,
                generated_by_id=user_id,
                request_count=len(items),
                resolved_count=resolved,
                high_priority_count=high_priority,
                summary=summary,
                generated_at=now,
            )
            db.session.add(memory)
        else:
            memory.generated_by_id = user_id
            memory.request_count = len(items)
            memory.resolved_count = resolved
            memory.high_priority_count = high_priority
            memory.summary = summary
            memory.generated_at = now
        generated.append(memory)
    db.session.flush()
    return generated


def structured_query(tenant_id: uuid.UUID, payload: dict) -> dict:
    dataset = str(payload.get("dataset", "SOLICITACOES")).strip().upper()
    metric = str(payload.get("metrica", "CONTAGEM")).strip().upper()
    group_by = str(payload.get("agruparPor", "NENHUM")).strip().upper()
    if dataset not in DATASETS:
        raise ValueError("Dataset estruturado inválido.")
    if metric not in METRICS:
        raise ValueError("Métrica estruturada inválida.")
    if group_by not in GROUPS:
        raise ValueError("Agrupamento estruturado inválido.")
    if metric == "TEMPO_MEDIO_RESOLUCAO_HORAS" and dataset != "SOLICITACOES":
        raise ValueError("Tempo médio de resolução está disponível somente para solicitações.")
    if metric == "PRAZOS_VENCIDOS" and dataset not in {
        "SOLICITACOES",
        "ENCAMINHAMENTOS",
    }:
        raise ValueError("Prazos vencidos não estão disponíveis para este dataset.")

    period_start = _optional_date(payload.get("inicio"))
    period_end = _optional_date(payload.get("fim"))
    if period_start and period_end and period_start > period_end:
        raise ValueError("O início do período deve ser anterior ou igual ao fim.")
    model, timestamp = DATASETS[dataset]
    date_field = str(payload.get("campoData", "PADRAO")).strip().upper()
    if date_field not in {"PADRAO", "ENCERRAMENTO"}:
        raise ValueError("Campo de data estruturado inválido.")
    if date_field == "ENCERRAMENTO":
        if dataset != "SOLICITACOES":
            raise ValueError("Data de encerramento está disponível somente para solicitações.")
        timestamp = ServiceRequest.closed_at
    statement = select(model).where(model.tenant_id == tenant_id)
    if dataset == "CIDADAOS":
        statement = statement.where(Citizen.anonymized_at.is_(None))
    if period_start:
        statement = statement.where(
            timestamp >= datetime.combine(period_start, time.min, tzinfo=UTC)
        )
    if period_end:
        statement = statement.where(
            timestamp
            < datetime.combine(period_end + timedelta(days=1), time.min, tzinfo=UTC)
        )
    status = str(payload.get("status", "")).strip().upper()
    items = list(db.session.scalars(statement))
    if status:
        items = [
            item
            for item in items
            if getattr(getattr(item, "status", None), "value", "") == status
        ]
    theme = str(payload.get("tema", "")).strip()
    if theme:
        items = [
            item
            for item in items
            if str(getattr(item, "theme", "") or "").casefold() == theme.casefold()
        ]
    territory_id = _optional_uuid(payload.get("territorioId"), "território")
    if territory_id:
        items = [
            item for item in items if getattr(item, "territory_id", None) == territory_id
        ]
    agency_id = _optional_uuid(payload.get("orgaoId"), "órgão")
    if agency_id:
        items = [
            item for item in items if getattr(item, "agency_id", None) == agency_id
        ]
    name = str(payload.get("nome", "")).strip()
    if name:
        normalized_name = _normalize_person_name(name)
        name_pattern = re.compile(rf"(?:^|\s){re.escape(normalized_name)}(?:\s|$)")
        items = [
            item
            for item in items
            if name_pattern.search(
                _normalize_person_name(getattr(item, "name", "") or "")
            )
            or name_pattern.search(
                _normalize_person_name(getattr(item, "social_name", "") or "")
            )
        ]

    agency_names = {
        item.id: item.name
        for item in db.session.scalars(
            select(ExternalAgency).where(ExternalAgency.tenant_id == tenant_id)
        )
    }
    territory_names = {
        item.id: item.name
        for item in db.session.scalars(
            select(Territory).where(Territory.tenant_id == tenant_id)
        )
    }
    grouped: dict[str, list] = defaultdict(list)
    for item in items:
        grouped[
            _structured_group(
                item,
                group_by,
                timestamp,
                agency_names,
                territory_names,
            )
        ].append(item)

    results = []
    for label, group_items in sorted(grouped.items()):
        value = _metric_value(metric, group_items)
        results.append({"grupo": label, "valor": value})
    total = _metric_value(metric, items)
    applied_filters = {
        "status": status or None,
        "tema": theme or None,
        "territorioId": str(territory_id) if territory_id else None,
        "orgaoId": str(agency_id) if agency_id else None,
        **({"campoData": date_field} if date_field != "PADRAO" else {}),
    }
    if dataset == "CIDADAOS":
        applied_filters["nome"] = name or None
    return {
        "metodo": "ESTRUTURADO",
        "dataset": dataset,
        "metrica": metric,
        "agruparPor": group_by,
        "filtros": applied_filters,
        "periodo": {
            "inicio": period_start.isoformat() if period_start else None,
            "fim": period_end.isoformat() if period_end else None,
        },
        "total": total,
        "itens": results,
        "tenantScoped": True,
    }


def _structured_group(
    item,
    group_by: str,
    timestamp,
    agency_names: dict,
    territory_names: dict,
) -> str:
    if group_by == "NENHUM":
        return "TOTAL"
    if group_by == "STATUS":
        return getattr(getattr(item, "status", None), "value", "SEM_STATUS")
    if group_by == "TEMA":
        return _group_label(getattr(item, "theme", None) or "Sem tema", 120)
    if group_by == "TERRITORIO":
        return territory_names.get(
            getattr(item, "territory_id", None), "Sem território"
        )
    if group_by == "ORGAO":
        return agency_names.get(getattr(item, "agency_id", None), "Sem órgão")
    if group_by == "TIPO":
        value = getattr(item, "event_type", None) or getattr(item, "document_type", None)
        return getattr(value, "value", "Sem tipo")
    if group_by == "ETAPA":
        return _group_label(getattr(item, "stage", None) or "Sem etapa", 160)
    if group_by == "MES":
        value = getattr(item, timestamp.key)
        return value.astimezone(UTC).strftime("%Y-%m") if value else "Sem data"
    raise ValueError("Agrupamento não suportado pelo dataset.")


def _metric_value(metric: str, items: list) -> int | float | None:
    if metric == "CONTAGEM":
        return len(items)
    if metric == "PRAZOS_VENCIDOS":
        now = datetime.now(UTC)
        return sum(
            bool(getattr(item, "due_at", None))
            and _as_utc(item.due_at) < now
            and getattr(getattr(item, "status", None), "value", "")
            not in {"RESOLVIDA", "ENCERRADA", "CANCELADA", "RESPONDIDO"}
            for item in items
        )
    hours = [
        (_as_utc(item.closed_at) - _as_utc(item.created_at)).total_seconds() / 3600
        for item in items
        if getattr(item, "closed_at", None)
    ]
    return round(sum(hours) / len(hours), 2) if hours else None


def _optional_date(value) -> date | None:
    if value in (None, ""):
        return None
    try:
        return date.fromisoformat(str(value))
    except ValueError as error:
        raise ValueError("Data inválida; use AAAA-MM-DD.") from error


def _optional_uuid(value, label: str) -> uuid.UUID | None:
    if value in (None, ""):
        return None
    try:
        return uuid.UUID(str(value))
    except ValueError as error:
        raise ValueError(f"Identificador de {label} inválido.") from error


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def _group_label(value: str, limit: int) -> str:
    return " ".join(str(value or "").split())[:limit]


def _normalize_person_name(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", str(value).casefold())
    without_accents = "".join(
        character for character in decomposed if not unicodedata.combining(character)
    )
    return " ".join(re.sub(r"[^a-z0-9]+", " ", without_accents).split())
