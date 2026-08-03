import hashlib
import json
import unicodedata
import uuid
from collections import Counter
from datetime import UTC, date, datetime, time, timedelta

from sqlalchemy import func, select

from app.extensions import db
from app.models import (
    AgendaEvent,
    AgendaEventStatus,
    ElectoralCandidacy,
    ElectoralCandidate,
    ElectoralCoverageProfile,
    ElectoralElection,
    ElectoralMandateSnapshot,
    ElectoralModuleSettings,
    ElectoralParty,
    ElectoralResult,
    LegislativeDraft,
    LegislativeDraftRequest,
    OversightAction,
    OversightActionStatus,
    RequestStatus,
    ServiceRequest,
    Territory,
)

DEFAULT_WEIGHTS = {
    "resolution": 0.30,
    "sla": 0.25,
    "agenda": 0.15,
    "actions": 0.15,
    "deliveries": 0.15,
}
DEFAULT_TARGETS = {"agenda": 2, "actions": 1, "deliveries": 2}
DEFAULT_SENSITIVE_CATEGORIES = [
    "saude",
    "religiao",
    "raca",
    "etnia",
    "orientacao sexual",
    "identidade de genero",
    "opiniao politica",
    "deficiencia",
]
RESOLVED_STATUSES = {RequestStatus.RESOLVIDA, RequestStatus.ENCERRADA}


class MandateIntelligenceError(ValueError):
    pass


def active_profile(tenant_id: uuid.UUID, mandate_id: uuid.UUID):
    return db.session.execute(
        select(ElectoralCoverageProfile)
        .where(
            ElectoralCoverageProfile.tenant_id == tenant_id,
            ElectoralCoverageProfile.mandate_id == mandate_id,
            ElectoralCoverageProfile.active.is_(True),
        )
        .order_by(ElectoralCoverageProfile.version.desc())
    ).scalars().first()


def ensure_default_profile(tenant_id, mandate_id, user_id) -> ElectoralCoverageProfile:
    profile = active_profile(tenant_id, mandate_id)
    if profile:
        return profile
    profile = ElectoralCoverageProfile(
        tenant_id=tenant_id,
        mandate_id=mandate_id,
        version=1,
        formula_code="ICT-1.0",
        weights=DEFAULT_WEIGHTS,
        targets=DEFAULT_TARGETS,
        sensitive_categories=DEFAULT_SENSITIVE_CATEGORIES,
        active=True,
        explanation=(
            "O ICT combina resolução, cumprimento de SLA, agenda, ações e entregas. "
            "Resultados eleitorais são apenas contexto e não integram a fórmula."
        ),
        created_by_id=user_id,
    )
    db.session.add(profile)
    db.session.flush()
    return profile


def create_profile(tenant_id, mandate_id, user_id, data: dict) -> ElectoralCoverageProfile:
    weights = _validated_numbers(data.get("weights", DEFAULT_WEIGHTS), DEFAULT_WEIGHTS, "weights")
    if abs(sum(weights.values()) - 1.0) > 0.0001:
        raise MandateIntelligenceError("Os pesos do ICT devem somar 1.")
    targets = _validated_numbers(data.get("targets", DEFAULT_TARGETS), DEFAULT_TARGETS, "targets")
    if any(value <= 0 for value in targets.values()):
        raise MandateIntelligenceError("As metas do ICT devem ser maiores que zero.")
    sensitive = data.get("sensitive_categories", DEFAULT_SENSITIVE_CATEGORIES)
    if not isinstance(sensitive, list) or not all(isinstance(item, str) for item in sensitive):
        raise MandateIntelligenceError("Categorias sensíveis devem ser uma lista de textos.")
    explanation = str(data.get("explanation") or "").strip()
    if len(explanation) < 20:
        raise MandateIntelligenceError("Informe uma explicação com pelo menos 20 caracteres.")

    current = active_profile(tenant_id, mandate_id)
    if current:
        current.active = False
    version = db.session.scalar(
        select(func.max(ElectoralCoverageProfile.version)).where(
            ElectoralCoverageProfile.tenant_id == tenant_id,
            ElectoralCoverageProfile.mandate_id == mandate_id,
        )
    ) or 0
    profile = ElectoralCoverageProfile(
        tenant_id=tenant_id,
        mandate_id=mandate_id,
        version=version + 1,
        formula_code="ICT-1.0",
        weights=weights,
        targets=targets,
        sensitive_categories=[item.strip() for item in sensitive if item.strip()],
        active=True,
        explanation=explanation[:500],
        created_by_id=user_id,
    )
    db.session.add(profile)
    db.session.flush()
    return profile


def generate_snapshot(
    tenant_id: uuid.UUID,
    mandate_id: uuid.UUID,
    user_id: uuid.UUID,
    period_start: date,
    period_end: date,
    *,
    election_id: uuid.UUID | None = None,
    candidate_id: uuid.UUID | None = None,
) -> ElectoralMandateSnapshot:
    if period_end < period_start:
        raise MandateIntelligenceError("A data final deve ser igual ou posterior à inicial.")
    if (period_end - period_start).days > 730:
        raise MandateIntelligenceError("O período máximo do snapshot é de 730 dias.")

    profile = ensure_default_profile(tenant_id, mandate_id, user_id)
    settings = db.session.get(ElectoralModuleSettings, tenant_id)
    threshold = settings.privacy_threshold if settings else 10
    cutoff = datetime.now(UTC)
    start_at = datetime.combine(period_start, time.min, tzinfo=UTC)
    end_at = datetime.combine(period_end + timedelta(days=1), time.min, tzinfo=UTC)
    metric_cutoff = min(cutoff, end_at - timedelta(microseconds=1))

    requests = list(db.session.execute(
        select(ServiceRequest).where(
            ServiceRequest.tenant_id == tenant_id,
            ServiceRequest.created_at >= start_at,
            ServiceRequest.created_at < end_at,
            ServiceRequest.created_at <= cutoff,
        )
    ).scalars())
    agenda = list(db.session.execute(
        select(AgendaEvent).where(
            AgendaEvent.tenant_id == tenant_id,
            AgendaEvent.starts_at >= start_at,
            AgendaEvent.starts_at < end_at,
            AgendaEvent.created_at <= cutoff,
            AgendaEvent.status != AgendaEventStatus.CANCELADO,
        )
    ).scalars())
    actions = list(db.session.execute(
        select(OversightAction).where(
            OversightAction.tenant_id == tenant_id,
            func.coalesce(OversightAction.occurred_at, OversightAction.created_at) >= start_at,
            func.coalesce(OversightAction.occurred_at, OversightAction.created_at) < end_at,
            OversightAction.created_at <= cutoff,
            OversightAction.status != OversightActionStatus.CANCELADA,
        )
    ).scalars())
    draft_rows = list(db.session.execute(
        select(LegislativeDraft, LegislativeDraftRequest.request_id)
        .outerjoin(LegislativeDraftRequest, LegislativeDraftRequest.draft_id == LegislativeDraft.id)
        .where(
            LegislativeDraft.tenant_id == tenant_id,
            LegislativeDraft.created_at >= start_at,
            LegislativeDraft.created_at < end_at,
            LegislativeDraft.created_at <= cutoff,
        )
    ).all())
    territories = list(db.session.execute(
        select(Territory).where(Territory.tenant_id == tenant_id, Territory.active.is_(True))
        .order_by(Territory.name)
    ).scalars())

    request_by_id = {item.id: item for item in requests}
    rows = [
        _territory_metrics(
            None, "Mandato inteiro", requests, agenda, actions, draft_rows, request_by_id,
            threshold, profile, metric_cutoff,
        )
    ]
    rows.extend(
        _territory_metrics(
            territory.id, territory.name, requests, agenda, actions, draft_rows, request_by_id,
            threshold, profile, metric_cutoff,
        )
        for territory in territories
    )
    context = _electoral_context(election_id, candidate_id)
    config = {
        "formula_code": profile.formula_code,
        "profile_version": profile.version,
        "weights": profile.weights,
        "targets": profile.targets,
        "sensitive_categories": profile.sensitive_categories,
        "privacy_threshold": threshold,
    }
    config_hash = hashlib.sha256(
        json.dumps(config, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()
    snapshot = ElectoralMandateSnapshot(
        tenant_id=tenant_id,
        mandate_id=mandate_id,
        coverage_profile_id=profile.id,
        created_by_id=user_id,
        period_start=period_start,
        period_end=period_end,
        privacy_threshold=threshold,
        config_hash=config_hash,
        source_cutoff_at=cutoff,
        electoral_context=context,
        payload={
            "formula": {
                "code": profile.formula_code,
                "version": profile.version,
                "weights": profile.weights,
                "targets": profile.targets,
                "explanation": profile.explanation,
                "electoral_performance_used": False,
            },
            "territories": rows,
            "privacy": {
                "threshold": threshold,
                "rule": (
                    "Métricas do mandato são suprimidas abaixo do limiar; "
                    "categorias pequenas não são exibidas."
                ),
            },
            "metric_cutoff_at": metric_cutoff.isoformat(),
        },
    )
    db.session.add(snapshot)
    db.session.flush()
    return snapshot


def snapshot_data(snapshot: ElectoralMandateSnapshot) -> dict:
    return {
        "id": str(snapshot.id),
        "period_start": snapshot.period_start.isoformat(),
        "period_end": snapshot.period_end.isoformat(),
        "privacy_threshold": snapshot.privacy_threshold,
        "config_hash": snapshot.config_hash,
        "source_cutoff_at": snapshot.source_cutoff_at.isoformat(),
        "electoral_context": snapshot.electoral_context,
        "payload": snapshot.payload,
        "created_at": snapshot.created_at.isoformat(),
    }


def profile_data(profile: ElectoralCoverageProfile) -> dict:
    return {
        "id": str(profile.id),
        "version": profile.version,
        "formula_code": profile.formula_code,
        "weights": profile.weights,
        "targets": profile.targets,
        "sensitive_categories": profile.sensitive_categories,
        "active": profile.active,
        "explanation": profile.explanation,
        "created_at": profile.created_at.isoformat(),
    }


def _territory_metrics(
    territory_id, name, requests, agenda, actions, draft_rows, request_by_id,
    threshold, profile, cutoff,
) -> dict:
    scoped_requests = [
        item for item in requests if territory_id is None or item.territory_id == territory_id
    ]
    request_ids = {item.id for item in scoped_requests}
    scoped_agenda = [
        item for item in agenda if territory_id is None or item.territory_id == territory_id
    ]
    scoped_actions = [
        item for item in actions
        if territory_id is None or (
            item.request_id in request_ids
            and request_by_id.get(item.request_id)
            and request_by_id[item.request_id].territory_id == territory_id
        )
    ]
    scoped_drafts = {
        draft.id for draft, request_id in draft_rows
        if territory_id is None or request_id in request_ids
    }
    demand_count = len(scoped_requests)
    base = {
        "territory_id": str(territory_id) if territory_id else None,
        "territory_name": name,
        "scope": "territory" if territory_id else "mandate",
        "demand_count": demand_count if demand_count >= threshold else None,
        "suppressed": demand_count < threshold,
        "suppression_reason": "privacy_threshold" if demand_count < threshold else None,
    }
    if demand_count < threshold:
        return {
            **base,
            "metrics": None,
            "categories": [],
            "ict": None,
            "alerts": [f"Dados do mandato ocultos: grupo com menos de {threshold} demandas."],
        }

    resolved = [
        item for item in scoped_requests
        if item.status in RESOLVED_STATUSES
        and item.closed_at is not None
        and _aware(item.closed_at) <= _aware(cutoff)
    ]
    assessed = [item for item in scoped_requests if item.due_at is not None]
    sla_met = [item for item in assessed if not _sla_breached(item, cutoff)]
    overdue = len(assessed) - len(sla_met)
    realized_agenda = sum(item.status == AgendaEventStatus.REALIZADO for item in scoped_agenda)
    completed_actions = sum(
        item.status == OversightActionStatus.CONCLUIDA for item in scoped_actions
    )
    deliveries = sum(bool(item.closing_evidence) for item in resolved)
    components = {
        "resolution": len(resolved) / demand_count,
        "sla": len(sla_met) / len(assessed) if assessed else None,
        "agenda": min(realized_agenda / float(profile.targets["agenda"]), 1.0),
        "actions": min(completed_actions / float(profile.targets["actions"]), 1.0),
        "deliveries": min(deliveries / float(profile.targets["deliveries"]), 1.0),
    }
    available_weight = sum(
        float(profile.weights[key]) for key, value in components.items() if value is not None
    )
    score = round(
        100 * sum(
            float(profile.weights[key]) * value
            for key, value in components.items() if value is not None
        ) / available_weight,
        1,
    )
    alerts = []
    if assessed and len(sla_met) / len(assessed) < 0.8:
        alerts.append("Cumprimento de SLA abaixo de 80% no período.")
    if overdue:
        alerts.append(f"{overdue} demandas com SLA vencido no recorte agregado.")
    if realized_agenda == 0:
        alerts.append("Nenhuma agenda territorial realizada no período.")
    if completed_actions == 0:
        alerts.append("Nenhuma ação de fiscalização concluída no período.")

    return {
        **base,
        "metrics": {
            "resolved": len(resolved),
            "resolution_rate": round(len(resolved) / demand_count, 4),
            "sla_assessed": len(assessed),
            "sla_met": len(sla_met),
            "sla_rate": round(len(sla_met) / len(assessed), 4) if assessed else None,
            "overdue": overdue,
            "agenda_realized": realized_agenda,
            "oversight_completed": completed_actions,
            "legislative_actions": len(scoped_drafts),
            "deliveries_with_evidence": deliveries,
        },
        "categories": _safe_categories(scoped_requests, threshold, profile.sensitive_categories),
        "ict": {"score": score, "components": components},
        "alerts": alerts,
    }


def _safe_categories(requests, threshold: int, sensitive_categories: list[str]) -> list[dict]:
    protected = {_normalize(item) for item in sensitive_categories}
    counts = Counter()
    protected_count = 0
    other_small = 0
    for item in requests:
        label = (item.category or item.theme or "Sem categoria").strip()
        normalized = _normalize(label)
        if any(term and term in normalized for term in protected):
            protected_count += 1
        else:
            counts[label] += 1
    result = []
    for label, count in counts.most_common():
        if count >= threshold:
            result.append({"label": label, "count": count})
        else:
            other_small += count
    if other_small >= threshold:
        result.append({"label": "Outros temas agregados", "count": other_small})
    if protected_count >= threshold:
        result.append({"label": "Temas protegidos (agregado)", "count": protected_count})
    return result


def _electoral_context(election_id, candidate_id) -> dict:
    if not election_id and not candidate_id:
        return {"available": False, "linkage_level": "jurisdiction"}
    if not election_id or not candidate_id:
        raise MandateIntelligenceError("Eleição e candidatura devem ser informadas em conjunto.")
    row = db.session.execute(
        select(ElectoralCandidacy, ElectoralCandidate, ElectoralElection, ElectoralParty)
        .join(ElectoralCandidate, ElectoralCandidate.id == ElectoralCandidacy.candidate_id)
        .join(ElectoralElection, ElectoralElection.id == ElectoralCandidacy.election_id)
        .join(ElectoralParty, ElectoralParty.id == ElectoralCandidacy.party_id)
        .where(
            ElectoralCandidacy.election_id == election_id,
            ElectoralCandidacy.candidate_id == candidate_id,
        )
    ).one_or_none()
    if not row:
        raise MandateIntelligenceError("Candidatura não encontrada para a eleição informada.")
    candidacy, candidate, election, party = row
    votes = db.session.scalar(
        select(func.sum(ElectoralResult.votes)).where(
            ElectoralResult.election_id == election.id,
            ElectoralResult.candidacy_id == candidacy.id,
        )
    ) or 0
    return {
        "available": True,
        "election_id": str(election.id),
        "candidate_id": str(candidate.id),
        "candidate_name": candidate.ballot_name,
        "party": party.acronym,
        "year": election.year,
        "votes": votes,
        "linkage_level": "jurisdiction",
        "warning": (
            "Contexto eleitoral público; não integra o ICT nem define prioridade de atendimento."
        ),
    }


def _sla_breached(item: ServiceRequest, cutoff: datetime) -> bool:
    due_at = _aware(item.due_at)
    completed_at = (
        _aware(item.closed_at)
        if item.status in RESOLVED_STATUSES
        and item.closed_at is not None
        and _aware(item.closed_at) <= _aware(cutoff)
        else _aware(cutoff)
    )
    return completed_at > due_at


def _aware(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _normalize(value: str) -> str:
    return "".join(
        char for char in unicodedata.normalize("NFKD", value.casefold())
        if not unicodedata.combining(char)
    )


def _validated_numbers(candidate, expected, name: str) -> dict:
    if not isinstance(candidate, dict) or set(candidate) != set(expected):
        raise MandateIntelligenceError(f"{name} deve conter: {', '.join(expected)}.")
    try:
        values = {key: float(candidate[key]) for key in expected}
    except (TypeError, ValueError) as exc:
        raise MandateIntelligenceError(f"{name} contém valor inválido.") from exc
    if any(value < 0 for value in values.values()):
        raise MandateIntelligenceError(f"{name} não aceita valores negativos.")
    return values
