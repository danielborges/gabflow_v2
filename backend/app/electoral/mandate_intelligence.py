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
    ElectoralAlertDelivery,
    ElectoralAlertPreference,
    ElectoralCandidacy,
    ElectoralCandidate,
    ElectoralCoverageProfile,
    ElectoralElection,
    ElectoralMandateSnapshot,
    ElectoralModuleSettings,
    ElectoralOperationalTerritoryLink,
    ElectoralParty,
    ElectoralPublicCommitment,
    ElectoralResult,
    ElectoralTerritory,
    LegislativeDraft,
    LegislativeDraftRequest,
    OutboxEvent,
    OversightAction,
    OversightActionStatus,
    RequestStatus,
    ServiceRequest,
    Territory,
    User,
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
ALERT_TYPES = {
    "SLA_DEGRADED",
    "SLA_OVERDUE",
    "AGENDA_GAP",
    "OVERSIGHT_GAP",
    "COMMITMENT_OVERDUE",
}
ALERT_CHANNELS = {"IN_APP", "EMAIL"}
ALERT_FREQUENCIES = {"IMMEDIATE", "DAILY", "WEEKLY"}
ELECTORAL_ALERT_EMAIL_EVENT = "EntregaAlertaEleitoralEmail"


class MandateIntelligenceError(ValueError):
    pass


def active_profile(tenant_id: uuid.UUID, mandate_id: uuid.UUID):
    return (
        db.session.execute(
            select(ElectoralCoverageProfile)
            .where(
                ElectoralCoverageProfile.tenant_id == tenant_id,
                ElectoralCoverageProfile.mandate_id == mandate_id,
                ElectoralCoverageProfile.active.is_(True),
            )
            .order_by(ElectoralCoverageProfile.version.desc())
        )
        .scalars()
        .first()
    )


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
    version = (
        db.session.scalar(
            select(func.max(ElectoralCoverageProfile.version)).where(
                ElectoralCoverageProfile.tenant_id == tenant_id,
                ElectoralCoverageProfile.mandate_id == mandate_id,
            )
        )
        or 0
    )
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

    requests = list(
        db.session.execute(
            select(ServiceRequest).where(
                ServiceRequest.tenant_id == tenant_id,
                ServiceRequest.created_at >= start_at,
                ServiceRequest.created_at < end_at,
                ServiceRequest.created_at <= cutoff,
            )
        ).scalars()
    )
    agenda = list(
        db.session.execute(
            select(AgendaEvent).where(
                AgendaEvent.tenant_id == tenant_id,
                AgendaEvent.starts_at >= start_at,
                AgendaEvent.starts_at < end_at,
                AgendaEvent.created_at <= cutoff,
                AgendaEvent.status != AgendaEventStatus.CANCELADO,
            )
        ).scalars()
    )
    actions = list(
        db.session.execute(
            select(OversightAction).where(
                OversightAction.tenant_id == tenant_id,
                func.coalesce(OversightAction.occurred_at, OversightAction.created_at) >= start_at,
                func.coalesce(OversightAction.occurred_at, OversightAction.created_at) < end_at,
                OversightAction.created_at <= cutoff,
                OversightAction.status != OversightActionStatus.CANCELADA,
            )
        ).scalars()
    )
    draft_rows = list(
        db.session.execute(
            select(LegislativeDraft, LegislativeDraftRequest.request_id)
            .outerjoin(
                LegislativeDraftRequest, LegislativeDraftRequest.draft_id == LegislativeDraft.id
            )
            .where(
                LegislativeDraft.tenant_id == tenant_id,
                LegislativeDraft.created_at >= start_at,
                LegislativeDraft.created_at < end_at,
                LegislativeDraft.created_at <= cutoff,
            )
        ).all()
    )
    territories = list(
        db.session.execute(
            select(Territory)
            .where(Territory.tenant_id == tenant_id, Territory.active.is_(True))
            .order_by(Territory.name)
        ).scalars()
    )
    commitments = list(
        db.session.execute(
            select(ElectoralPublicCommitment).where(
                ElectoralPublicCommitment.tenant_id == tenant_id,
                ElectoralPublicCommitment.mandate_id == mandate_id,
                ElectoralPublicCommitment.created_at < end_at,
                ElectoralPublicCommitment.created_at <= cutoff,
            )
        ).scalars()
    )

    context = _electoral_context(election_id, candidate_id)
    electoral_overlays = _electoral_overlays(
        tenant_id,
        mandate_id,
        context.get("candidacy_id"),
        context.get("dataset_version_id"),
    )
    request_by_id = {item.id: item for item in requests}
    rows = [
        _territory_metrics(
            None,
            "Mandato inteiro",
            requests,
            agenda,
            actions,
            draft_rows,
            request_by_id,
            commitments,
            threshold,
            profile,
            metric_cutoff,
            None,
        )
    ]
    rows.extend(
        _territory_metrics(
            territory.id,
            territory.name,
            requests,
            agenda,
            actions,
            draft_rows,
            request_by_id,
            commitments,
            threshold,
            profile,
            metric_cutoff,
            electoral_overlays.get(territory.id),
        )
        for territory in territories
    )
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


def latest_snapshot(
    tenant_id: uuid.UUID,
    mandate_id: uuid.UUID,
    *,
    snapshot_id: uuid.UUID | None = None,
    period_start: date | None = None,
    period_end: date | None = None,
) -> ElectoralMandateSnapshot | None:
    statement = select(ElectoralMandateSnapshot).where(
        ElectoralMandateSnapshot.tenant_id == tenant_id,
        ElectoralMandateSnapshot.mandate_id == mandate_id,
    )
    if snapshot_id:
        statement = statement.where(ElectoralMandateSnapshot.id == snapshot_id)
    if period_start:
        statement = statement.where(ElectoralMandateSnapshot.period_start == period_start)
    if period_end:
        statement = statement.where(ElectoralMandateSnapshot.period_end == period_end)
    return (
        db.session.execute(statement.order_by(ElectoralMandateSnapshot.created_at.desc()))
        .scalars()
        .first()
    )


def territory_overlay_data(snapshot: ElectoralMandateSnapshot, territory_id: uuid.UUID) -> dict:
    row = next(
        (
            item
            for item in snapshot.payload.get("territories", [])
            if item.get("scope") == "territory" and item.get("territory_id") == str(territory_id)
        ),
        None,
    )
    if row is None:
        raise MandateIntelligenceError("Território não encontrado no snapshot selecionado.")
    return {
        "snapshot": {
            "id": str(snapshot.id),
            "period_start": snapshot.period_start.isoformat(),
            "period_end": snapshot.period_end.isoformat(),
            "source_cutoff_at": snapshot.source_cutoff_at.isoformat(),
            "config_hash": snapshot.config_hash,
        },
        "territory": row,
        "formula": snapshot.payload.get("formula", {}),
        "privacy": snapshot.payload.get("privacy", {}),
        "electoral_context": snapshot.electoral_context,
        "linkage": {
            "level": "operational_territory",
            "electoral_overlay_available": bool(row.get("electoral_overlay")),
            "electoral_overlay": row.get("electoral_overlay"),
            "reason": None if row.get("electoral_overlay") else (
                "O território operacional não possui crosswalk oficial/revisado com uma "
                "unidade eleitoral; resultados eleitorais permanecem no contexto jurisdicional."
            ),
        },
    }


def territory_briefing_data(snapshot: ElectoralMandateSnapshot, territory_id: uuid.UUID) -> dict:
    overlay = territory_overlay_data(snapshot, territory_id)
    row = overlay["territory"]
    facts = []
    if not row.get("suppressed"):
        metrics = row.get("metrics") or {}
        facts = [
            {"label": "Demandas agregadas", "value": row.get("demand_count")},
            {"label": "ICT", "value": (row.get("ict") or {}).get("score")},
            {"label": "Resolvidas", "value": metrics.get("resolved")},
            {"label": "SLA cumprido", "value": metrics.get("sla_rate")},
            {"label": "Agendas realizadas", "value": metrics.get("agenda_realized")},
            {
                "label": "Entregas com evidência",
                "value": metrics.get("deliveries_with_evidence"),
            },
        ]
    return {
        "draft": True,
        "review_required": True,
        "title": f"Briefing territorial — {row['territory_name']}",
        "period": overlay["snapshot"],
        "privacy": {
            **overlay["privacy"],
            "suppressed": bool(row.get("suppressed")),
        },
        "facts": facts,
        "categories": row.get("categories", []) if not row.get("suppressed") else [],
        "alerts": row.get("alert_events", []),
        "public_commitments": row.get("public_commitments", {}),
        "suggested_questions": [
            "Quais entregas públicas possuem evidência verificável no período?",
            "Quais gargalos de SLA exigem investigação operacional?",
            "Quais compromissos públicos estão próximos do prazo?",
        ],
        "methodology_notice": (
            "Rascunho baseado exclusivamente em dados agregados do mandato. "
            "Não usa desempenho eleitoral para priorizar atendimento e exige revisão humana."
        ),
        "linkage": overlay["linkage"],
    }


def alert_preference(tenant_id, mandate_id, user_id) -> ElectoralAlertPreference | None:
    return db.session.execute(
        select(ElectoralAlertPreference).where(
            ElectoralAlertPreference.tenant_id == tenant_id,
            ElectoralAlertPreference.mandate_id == mandate_id,
            ElectoralAlertPreference.user_id == user_id,
        )
    ).scalar_one_or_none()


def alert_preference_data(item: ElectoralAlertPreference | None) -> dict:
    return {
        "enabled": item.enabled if item else True,
        "channels": item.channels if item else ["IN_APP"],
        "frequency": item.frequency if item else "DAILY",
        "alert_types": item.alert_types if item else sorted(ALERT_TYPES),
        "available_channels": sorted(ALERT_CHANNELS),
        "available_frequencies": sorted(ALERT_FREQUENCIES),
        "available_alert_types": sorted(ALERT_TYPES),
        "updated_at": item.updated_at.isoformat() if item else None,
    }


def upsert_alert_preference(tenant_id, mandate_id, user_id, data: dict) -> ElectoralAlertPreference:
    enabled = data.get("enabled", True)
    if not isinstance(enabled, bool):
        raise MandateIntelligenceError("enabled deve ser verdadeiro ou falso.")
    channels = data.get("channels", ["IN_APP"])
    alert_types = data.get("alert_types", sorted(ALERT_TYPES))
    frequency = str(data.get("frequency") or "DAILY").upper()
    if not isinstance(channels, list) or not channels:
        raise MandateIntelligenceError("Selecione ao menos um canal de alerta.")
    channels = list(dict.fromkeys(str(item).upper() for item in channels))
    if set(channels) - ALERT_CHANNELS:
        raise MandateIntelligenceError("Canal de alerta inválido.")
    if frequency not in ALERT_FREQUENCIES:
        raise MandateIntelligenceError("Frequência de alerta inválida.")
    if not isinstance(alert_types, list) or not alert_types:
        raise MandateIntelligenceError("Selecione ao menos um tipo de alerta.")
    alert_types = list(dict.fromkeys(str(item).upper() for item in alert_types))
    if set(alert_types) - ALERT_TYPES:
        raise MandateIntelligenceError("Tipo de alerta inválido.")
    item = alert_preference(tenant_id, mandate_id, user_id)
    if item is None:
        item = ElectoralAlertPreference(
            tenant_id=tenant_id,
            mandate_id=mandate_id,
            user_id=user_id,
        )
        db.session.add(item)
    item.enabled = enabled
    item.channels = channels
    item.frequency = frequency
    item.alert_types = alert_types
    item.updated_at = datetime.now(UTC)
    db.session.flush()
    return item


def alert_feed_data(
    snapshot: ElectoralMandateSnapshot | None,
    preference: ElectoralAlertPreference | None,
) -> dict:
    settings = alert_preference_data(preference)
    if snapshot is None or not settings["enabled"]:
        return {"preference": settings, "snapshot_id": None, "content": []}
    allowed = set(settings["alert_types"])
    content = []
    for row in snapshot.payload.get("territories", []):
        if row.get("scope") != "territory":
            continue
        for event in row.get("alert_events", []):
            if event.get("type") in allowed:
                content.append(
                    {
                        **event,
                        "territory_id": row.get("territory_id"),
                        "territory_name": row.get("territory_name"),
                    }
                )
    return {
        "preference": settings,
        "snapshot_id": str(snapshot.id),
        "source_cutoff_at": snapshot.source_cutoff_at.isoformat(),
        "content": content,
    }


def dispatch_alert_deliveries(
    tenant_id, mandate_id, *, snapshot=None, frequencies=None, now=None
) -> int:
    now = now or datetime.now(UTC)
    snapshot = snapshot or latest_snapshot(tenant_id, mandate_id)
    if snapshot is None:
        return 0
    statement = select(ElectoralAlertPreference).where(
        ElectoralAlertPreference.tenant_id == tenant_id,
        ElectoralAlertPreference.mandate_id == mandate_id,
        ElectoralAlertPreference.enabled.is_(True),
    )
    if frequencies:
        statement = statement.where(ElectoralAlertPreference.frequency.in_(frequencies))
    created = 0
    for preference in db.session.execute(statement).scalars():
        if not _alert_frequency_due(preference.frequency, snapshot.created_at, now):
            continue
        feed = alert_feed_data(snapshot, preference)
        user = db.session.get(User, preference.user_id)
        for alert in feed["content"]:
            raw_key = "|".join(
                str(alert.get(key) or "") for key in ("type", "territory_id", "message")
            )
            event_key = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()
            for channel in preference.channels:
                exists = db.session.execute(
                    select(ElectoralAlertDelivery.id).where(
                        ElectoralAlertDelivery.preference_id == preference.id,
                        ElectoralAlertDelivery.snapshot_id == snapshot.id,
                        ElectoralAlertDelivery.event_key == event_key,
                        ElectoralAlertDelivery.channel == channel,
                    )
                ).scalar_one_or_none()
                if exists:
                    continue
                delivery = ElectoralAlertDelivery(
                    tenant_id=tenant_id,
                    mandate_id=mandate_id,
                    preference_id=preference.id,
                    user_id=preference.user_id,
                    snapshot_id=snapshot.id,
                    event_key=event_key,
                    alert_type=alert["type"],
                    channel=channel,
                    status="DELIVERED" if channel == "IN_APP" else "PENDING",
                    payload=alert,
                    scheduled_for=now,
                    delivered_at=now if channel == "IN_APP" else None,
                )
                db.session.add(delivery)
                db.session.flush()
                if channel == "EMAIL" and user:
                    event = OutboxEvent(
                        tenant_id=tenant_id,
                        event_type=ELECTORAL_ALERT_EMAIL_EVENT,
                        aggregate_type="ElectoralAlertDelivery",
                        aggregate_id=str(delivery.id),
                        payload={},
                    )
                    event.payload = {
                        "deliveryId": str(delivery.id),
                        "recipient": user.email,
                        "subject": f"GabFlow · {alert['type']}",
                        "text": (
                            f"{alert.get('territory_name') or 'Mandato'}\n\n"
                            f"{alert.get('message')}\n\n"
                            "Consulte o snapshot territorial no GabFlow."
                        ),
                        "idempotencyKey": f"gabflow-electoral-alert-{delivery.id}",
                    }
                    db.session.add(event)
                created += 1
    return created


def alert_delivery_data(item: ElectoralAlertDelivery) -> dict:
    return {
        "id": str(item.id),
        "snapshot_id": str(item.snapshot_id),
        "alert_type": item.alert_type,
        "channel": item.channel,
        "status": item.status,
        "payload": item.payload,
        "scheduled_for": item.scheduled_for.isoformat(),
        "delivered_at": item.delivered_at.isoformat() if item.delivered_at else None,
        "error": item.error,
        "created_at": item.created_at.isoformat(),
    }


def _alert_frequency_due(frequency: str, snapshot_created_at: datetime, now: datetime) -> bool:
    created = _aware(snapshot_created_at)
    if frequency == "IMMEDIATE":
        return True
    if frequency == "DAILY":
        return now.date() > created.date()
    return now >= created + timedelta(days=7)


def _territory_metrics(
    territory_id,
    name,
    requests,
    agenda,
    actions,
    draft_rows,
    request_by_id,
    commitments,
    threshold,
    profile,
    cutoff,
    electoral_overlay,
) -> dict:
    scoped_requests = [
        item for item in requests if territory_id is None or item.territory_id == territory_id
    ]
    request_ids = {item.id for item in scoped_requests}
    scoped_agenda = [
        item for item in agenda if territory_id is None or item.territory_id == territory_id
    ]
    scoped_actions = [
        item
        for item in actions
        if territory_id is None
        or (
            item.request_id in request_ids
            and request_by_id.get(item.request_id)
            and request_by_id[item.request_id].territory_id == territory_id
        )
    ]
    scoped_drafts = {
        draft.id
        for draft, request_id in draft_rows
        if territory_id is None or request_id in request_ids
    }
    scoped_commitments = [
        item for item in commitments if territory_id is None or item.territory_id == territory_id
    ]
    completed_commitments = [
        item
        for item in scoped_commitments
        if item.status == "COMPLETED"
        and item.completed_at is not None
        and _aware(item.completed_at) <= _aware(cutoff)
    ]
    overdue_commitments = [
        item
        for item in scoped_commitments
        if item.status not in {"COMPLETED", "CANCELLED"} and item.due_on < cutoff.date()
    ]
    commitment_summary = {
        "total": len(scoped_commitments),
        "completed": len(completed_commitments),
        "overdue": len(overdue_commitments),
        "average_progress": (
            round(sum(item.progress for item in scoped_commitments) / len(scoped_commitments), 1)
            if scoped_commitments
            else None
        ),
    }
    demand_count = len(scoped_requests)
    base = {
        "territory_id": str(territory_id) if territory_id else None,
        "territory_name": name,
        "scope": "territory" if territory_id else "mandate",
        "demand_count": demand_count if demand_count >= threshold else None,
        "suppressed": demand_count < threshold,
        "suppression_reason": "privacy_threshold" if demand_count < threshold else None,
        "public_commitments": commitment_summary,
        "electoral_overlay": electoral_overlay,
    }
    if demand_count < threshold:
        message = f"Dados do mandato ocultos: grupo com menos de {threshold} demandas."
        return {
            **base,
            "metrics": None,
            "categories": [],
            "ict": None,
            "alerts": [message],
            "alert_events": [
                {"type": "PRIVACY_SUPPRESSION", "severity": "INFO", "message": message}
            ],
        }

    resolved = [
        item
        for item in scoped_requests
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
        100
        * sum(
            float(profile.weights[key]) * value
            for key, value in components.items()
            if value is not None
        )
        / available_weight,
        1,
    )
    alert_events = []
    if assessed and len(sla_met) / len(assessed) < 0.8:
        alert_events.append(
            {
                "type": "SLA_DEGRADED",
                "severity": "WARNING",
                "message": "Cumprimento de SLA abaixo de 80% no período.",
            }
        )
    if overdue:
        alert_events.append(
            {
                "type": "SLA_OVERDUE",
                "severity": "WARNING",
                "message": f"{overdue} demandas com SLA vencido no recorte agregado.",
            }
        )
    if realized_agenda == 0:
        alert_events.append(
            {
                "type": "AGENDA_GAP",
                "severity": "INFO",
                "message": "Nenhuma agenda territorial realizada no período.",
            }
        )
    if completed_actions == 0:
        alert_events.append(
            {
                "type": "OVERSIGHT_GAP",
                "severity": "INFO",
                "message": "Nenhuma ação de fiscalização concluída no período.",
            }
        )
    if overdue_commitments:
        alert_events.append(
            {
                "type": "COMMITMENT_OVERDUE",
                "severity": "WARNING",
                "message": (f"{len(overdue_commitments)} compromissos públicos com prazo vencido."),
            }
        )

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
        "alerts": [item["message"] for item in alert_events],
        "alert_events": alert_events,
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
    votes = (
        db.session.scalar(
            select(func.sum(ElectoralResult.votes)).where(
                ElectoralResult.election_id == election.id,
                ElectoralResult.candidacy_id == candidacy.id,
            )
        )
        or 0
    )
    return {
        "available": True,
        "election_id": str(election.id),
        "candidate_id": str(candidate.id),
        "candidacy_id": str(candidacy.id),
        "dataset_version_id": str(candidacy.dataset_version_id),
        "candidate_name": candidate.ballot_name,
        "party": party.acronym,
        "year": election.year,
        "votes": votes,
        "linkage_level": "jurisdiction",
        "warning": (
            "Contexto eleitoral público; não integra o ICT nem define prioridade de atendimento."
        ),
    }


def _electoral_overlays(tenant_id, mandate_id, candidacy_id, dataset_version_id) -> dict:
    if not candidacy_id or not dataset_version_id:
        return {}
    rows = db.session.execute(
        select(
            ElectoralOperationalTerritoryLink.territory_id,
            ElectoralOperationalTerritoryLink.method,
            ElectoralOperationalTerritoryLink.reviewed_at,
            ElectoralTerritory,
            ElectoralResult.votes,
        )
        .join(
            ElectoralTerritory,
            ElectoralTerritory.id == ElectoralOperationalTerritoryLink.electoral_territory_id,
        )
        .outerjoin(
            ElectoralResult,
            (ElectoralResult.territory_id == ElectoralTerritory.id)
            & (ElectoralResult.candidacy_id == uuid.UUID(str(candidacy_id))),
        )
        .where(
            ElectoralOperationalTerritoryLink.tenant_id == tenant_id,
            ElectoralOperationalTerritoryLink.mandate_id == mandate_id,
            ElectoralOperationalTerritoryLink.active.is_(True),
            ElectoralTerritory.dataset_version_id == uuid.UUID(str(dataset_version_id)),
        )
    ).all()
    grouped = {}
    for territory_id, method, reviewed_at, electoral, votes in rows:
        entry = grouped.setdefault(
            territory_id,
            {
                "votes": 0,
                "units": [],
                "methods": set(),
                "reviewed_at": [],
                "warning": (
                    "Resultado eleitoral agregado e revisado; não integra o ICT nem define "
                    "prioridade de atendimento."
                ),
            },
        )
        entry["votes"] += int(votes or 0)
        entry["methods"].add(method)
        entry["reviewed_at"].append(reviewed_at.isoformat())
        entry["units"].append(
            {
                "id": str(electoral.id),
                "level": electoral.level.value,
                "municipality": electoral.municipality_name,
                "zone": electoral.zone,
                "votes": int(votes or 0),
            }
        )
    for entry in grouped.values():
        entry["methods"] = sorted(entry["methods"])
        entry["reviewed_at"] = max(entry["reviewed_at"])
    return grouped


def territory_link_catalog(tenant_id, mandate_id, election_id) -> dict:
    operational = list(
        db.session.execute(
            select(Territory)
            .where(Territory.tenant_id == tenant_id, Territory.active.is_(True))
            .order_by(Territory.name)
        ).scalars()
    )
    dataset_ids = (
        select(ElectoralCandidacy.dataset_version_id)
        .where(ElectoralCandidacy.election_id == election_id)
        .distinct()
    )
    electoral = list(
        db.session.execute(
            select(ElectoralTerritory)
            .where(ElectoralTerritory.dataset_version_id.in_(dataset_ids))
            .order_by(
                ElectoralTerritory.municipality_name,
                ElectoralTerritory.level,
                ElectoralTerritory.zone,
            )
        ).scalars()
    )
    links = list(
        db.session.execute(
            select(ElectoralOperationalTerritoryLink)
            .join(
                ElectoralTerritory,
                ElectoralTerritory.id == ElectoralOperationalTerritoryLink.electoral_territory_id,
            )
            .where(
                ElectoralOperationalTerritoryLink.tenant_id == tenant_id,
                ElectoralOperationalTerritoryLink.mandate_id == mandate_id,
                ElectoralOperationalTerritoryLink.active.is_(True),
                ElectoralTerritory.dataset_version_id.in_(dataset_ids),
            )
            .order_by(ElectoralOperationalTerritoryLink.created_at)
        ).scalars()
    )
    territory_by_id = {item.id: item for item in operational}
    electoral_by_id = {item.id: item for item in electoral}
    return {
        "operational_territories": [
            {"id": str(item.id), "name": item.name} for item in operational
        ],
        "electoral_territories": [_electoral_territory_data(item) for item in electoral],
        "content": [
            territory_link_data(
                item,
                territory_by_id.get(item.territory_id),
                electoral_by_id.get(item.electoral_territory_id),
            )
            for item in links
        ],
    }


def create_territory_link(tenant_id, mandate_id, user_id, data: dict):
    try:
        territory_id = uuid.UUID(str(data["territory_id"]))
        electoral_territory_id = uuid.UUID(str(data["electoral_territory_id"]))
        election_id = uuid.UUID(str(data["election_id"]))
    except (KeyError, TypeError, ValueError) as exc:
        raise MandateIntelligenceError("Territórios e eleição devem ser informados.") from exc
    territory = db.session.execute(
        select(Territory).where(
            Territory.id == territory_id,
            Territory.tenant_id == tenant_id,
            Territory.active.is_(True),
        )
    ).scalar_one_or_none()
    electoral = db.session.get(ElectoralTerritory, electoral_territory_id)
    valid_dataset = (
        electoral
        and db.session.execute(
            select(ElectoralCandidacy.id)
            .where(
                ElectoralCandidacy.election_id == election_id,
                ElectoralCandidacy.dataset_version_id == electoral.dataset_version_id,
            )
            .limit(1)
        ).scalar_one_or_none()
    )
    if territory is None or not valid_dataset:
        raise MandateIntelligenceError("Território operacional ou eleitoral incompatível.")
    item = db.session.execute(
        select(ElectoralOperationalTerritoryLink).where(
            ElectoralOperationalTerritoryLink.tenant_id == tenant_id,
            ElectoralOperationalTerritoryLink.mandate_id == mandate_id,
            ElectoralOperationalTerritoryLink.territory_id == territory_id,
            ElectoralOperationalTerritoryLink.electoral_territory_id == electoral_territory_id,
        )
    ).scalar_one_or_none()
    if item is None:
        item = ElectoralOperationalTerritoryLink(
            tenant_id=tenant_id,
            mandate_id=mandate_id,
            territory_id=territory_id,
            electoral_territory_id=electoral_territory_id,
            method="HUMAN_REVIEW",
            reviewed_by_id=user_id,
        )
        db.session.add(item)
    item.active = True
    item.notes = str(data.get("notes") or "").strip()[:500] or None
    item.reviewed_by_id = user_id
    item.reviewed_at = datetime.now(UTC)
    db.session.flush()
    return item, territory, electoral


def territory_link_data(item, territory=None, electoral=None) -> dict:
    return {
        "id": str(item.id),
        "territory_id": str(item.territory_id),
        "territory_name": territory.name if territory else None,
        "electoral_territory_id": str(item.electoral_territory_id),
        "electoral_territory": _electoral_territory_data(electoral) if electoral else None,
        "method": item.method,
        "notes": item.notes,
        "reviewed_at": item.reviewed_at.isoformat(),
    }


def _electoral_territory_data(item) -> dict:
    suffix = f"Zona {item.zone}" if item.zone else item.level.value.title()
    return {
        "id": str(item.id),
        "level": item.level.value,
        "uf": item.uf,
        "municipality_code": item.municipality_code,
        "municipality_name": item.municipality_name,
        "zone": item.zone,
        "label": f"{item.municipality_name} · {suffix}",
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
        char
        for char in unicodedata.normalize("NFKD", value.casefold())
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
