import hashlib
import uuid
from collections import defaultdict
from datetime import UTC, datetime, time, timedelta

from sqlalchemy import select

from app.electoral.mandate_intelligence import latest_snapshot, territory_briefing_data
from app.electoral.reports import REPORT_EVENT
from app.extensions import db
from app.models import (
    AgendaEvent,
    AgendaEventStatus,
    ElectoralCandidacy,
    ElectoralOffice,
    ElectoralPublicCommitment,
    ElectoralReportJob,
    ElectoralReportSchedule,
    ElectoralTerritory,
    ElectoralTerritorySegment,
    ElectoralUserPreference,
    OutboxEvent,
    Territory,
    User,
    UserStatus,
)

PREFERENCE_INDICATORS = {"votes", "share", "rank", "variation", "ict", "sla", "demands"}
TERRITORY_LEVELS = {"municipality", "electoral_zone", "neighborhood", "voting_place", "section"}
SCHEDULE_FREQUENCIES = {"DAILY", "WEEKLY", "MONTHLY"}


class AdvancedFeatureError(ValueError):
    pass


def user_preference(tenant_id, mandate_id, user_id):
    return db.session.execute(
        select(ElectoralUserPreference).where(
            ElectoralUserPreference.tenant_id == tenant_id,
            ElectoralUserPreference.mandate_id == mandate_id,
            ElectoralUserPreference.user_id == user_id,
        )
    ).scalar_one_or_none()


def preference_data(item) -> dict:
    return {
        "election_id": str(item.election_id) if item and item.election_id else None,
        "office_id": str(item.office_id) if item and item.office_id else None,
        "territory_level": item.territory_level if item else "municipality",
        "indicators": item.indicators if item else ["votes", "share", "rank"],
        "available_indicators": sorted(PREFERENCE_INDICATORS),
        "available_territory_levels": sorted(TERRITORY_LEVELS),
        "updated_at": item.updated_at.isoformat() if item else None,
    }


def save_user_preference(tenant_id, mandate_id, user_id, data):
    level = str(data.get("territory_level") or "municipality").lower()
    indicators = data.get("indicators") or []
    if level not in TERRITORY_LEVELS:
        raise AdvancedFeatureError("Recorte territorial inválido.")
    if not isinstance(indicators, list) or not indicators:
        raise AdvancedFeatureError("Selecione ao menos um indicador.")
    indicators = list(dict.fromkeys(str(value).lower() for value in indicators))
    if set(indicators) - PREFERENCE_INDICATORS:
        raise AdvancedFeatureError("Indicador inválido.")
    try:
        election_id = uuid.UUID(str(data["election_id"])) if data.get("election_id") else None
        office_id = uuid.UUID(str(data["office_id"])) if data.get("office_id") else None
    except ValueError as exc:
        raise AdvancedFeatureError("Eleição ou cargo inválido.") from exc
    if office_id:
        office = db.session.get(ElectoralOffice, office_id)
        if office is None:
            raise AdvancedFeatureError("Cargo eleitoral não encontrado.")
        if election_id:
            compatible = db.session.execute(
                select(ElectoralCandidacy.id).where(
                    ElectoralCandidacy.election_id == election_id,
                    ElectoralCandidacy.office_id == office_id,
                ).limit(1)
            ).scalar_one_or_none()
            if compatible is None:
                raise AdvancedFeatureError("O cargo não pertence à eleição selecionada.")
    item = user_preference(tenant_id, mandate_id, user_id)
    if item is None:
        item = ElectoralUserPreference(tenant_id=tenant_id, mandate_id=mandate_id, user_id=user_id)
        db.session.add(item)
    item.election_id = election_id
    item.office_id = office_id
    item.territory_level = level
    item.indicators = indicators
    item.updated_at = datetime.now(UTC)
    db.session.flush()
    return item


def segment_data(item, names=None) -> dict:
    names = names or {}
    return {
        "id": str(item.id),
        "name": item.name,
        "description": item.description,
        "election_id": str(item.election_id),
        "territory_ids": item.territory_ids,
        "territories": [{"id": value, "name": names.get(value)} for value in item.territory_ids],
        "created_at": item.created_at.isoformat(),
        "updated_at": item.updated_at.isoformat(),
    }


def segment_catalog(tenant_id, mandate_id, user_id, election_id) -> dict:
    units = _electoral_units(election_id)
    names = {str(item.id): _electoral_unit_label(item) for item in units}
    segments = list(
        db.session.execute(
            select(ElectoralTerritorySegment)
            .where(
                ElectoralTerritorySegment.tenant_id == tenant_id,
                ElectoralTerritorySegment.mandate_id == mandate_id,
                ElectoralTerritorySegment.user_id == user_id,
                ElectoralTerritorySegment.election_id == election_id,
            )
            .order_by(ElectoralTerritorySegment.name)
        ).scalars()
    )
    return {
        "available_territories": [
            {"id": str(item.id), "name": names[str(item.id)], "level": item.level.value}
            for item in units
        ],
        "content": [segment_data(item, names) for item in segments],
    }


def save_segment(tenant_id, mandate_id, user_id, data, item=None):
    name = str(data.get("name") or "").strip()
    description = str(data.get("description") or "").strip()[:500] or None
    if not 3 <= len(name) <= 120:
        raise AdvancedFeatureError("O nome do segmento deve ter entre 3 e 120 caracteres.")
    try:
        election_id = uuid.UUID(str(data["election_id"]))
        territory_ids = list(
            dict.fromkeys(str(uuid.UUID(str(value))) for value in data["territory_ids"])
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise AdvancedFeatureError("Eleição e territórios válidos são obrigatórios.") from exc
    if not 1 <= len(territory_ids) <= 100:
        raise AdvancedFeatureError("O segmento deve conter entre 1 e 100 unidades agregadas.")
    available = {str(unit.id) for unit in _electoral_units(election_id)}
    if set(territory_ids) - available:
        raise AdvancedFeatureError("O segmento contém território incompatível com a eleição.")
    duplicate_query = select(ElectoralTerritorySegment.id).where(
        ElectoralTerritorySegment.tenant_id == tenant_id,
        ElectoralTerritorySegment.mandate_id == mandate_id,
        ElectoralTerritorySegment.user_id == user_id,
        ElectoralTerritorySegment.name == name,
    )
    if item is not None:
        duplicate_query = duplicate_query.where(ElectoralTerritorySegment.id != item.id)
    if db.session.execute(duplicate_query).scalar_one_or_none():
        raise AdvancedFeatureError("Já existe um segmento com esse nome.")
    if item is None:
        item = ElectoralTerritorySegment(
            tenant_id=tenant_id,
            mandate_id=mandate_id,
            user_id=user_id,
            election_id=election_id,
        )
        db.session.add(item)
    item.name = name
    item.description = description
    item.election_id = election_id
    item.territory_ids = territory_ids
    db.session.flush()
    return item


def pre_visit_briefing(tenant_id, mandate_id, event_id, snapshot_id=None) -> dict:
    event = db.session.execute(
        select(AgendaEvent).where(
            AgendaEvent.id == event_id,
            AgendaEvent.tenant_id == tenant_id,
            AgendaEvent.territory_id.is_not(None),
        )
    ).scalar_one_or_none()
    if event is None:
        raise AdvancedFeatureError("Evento territorial não encontrado.")
    snapshot = latest_snapshot(tenant_id, mandate_id, snapshot_id=snapshot_id)
    if snapshot is None:
        raise AdvancedFeatureError("Gere um snapshot antes do briefing pré-visita.")
    briefing = territory_briefing_data(snapshot, event.territory_id)
    upcoming = list(
        db.session.execute(
            select(AgendaEvent)
            .where(
                AgendaEvent.tenant_id == tenant_id,
                AgendaEvent.territory_id == event.territory_id,
                AgendaEvent.status == AgendaEventStatus.AGENDADO,
                AgendaEvent.starts_at >= datetime.now(UTC),
            )
            .order_by(AgendaEvent.starts_at)
            .limit(10)
        ).scalars()
    )
    briefing.update(
        {
            "kind": "PRE_VISIT",
            "editable_draft": True,
            "agenda_event": {
                "id": str(event.id),
                "title": event.title,
                "starts_at": event.starts_at.isoformat(),
                "public_location": event.location if event.citizen_id is None else None,
            },
            "upcoming_agenda": [
                {"id": str(item.id), "title": item.title, "starts_at": item.starts_at.isoformat()}
                for item in upcoming
            ],
        }
    )
    return briefing


def mandate_map_layers(tenant_id, mandate_id, snapshot_id=None) -> dict:
    snapshot = latest_snapshot(tenant_id, mandate_id, snapshot_id=snapshot_id)
    if snapshot is None:
        raise AdvancedFeatureError("Snapshot territorial não encontrado.")
    rows = {
        item.get("territory_id"): item
        for item in snapshot.payload.get("territories", [])
        if item.get("scope") == "territory"
    }
    commitments = list(
        db.session.execute(
            select(ElectoralPublicCommitment).where(
                ElectoralPublicCommitment.tenant_id == tenant_id,
                ElectoralPublicCommitment.mandate_id == mandate_id,
                ElectoralPublicCommitment.location_is_public.is_(True),
                ElectoralPublicCommitment.latitude.is_not(None),
                ElectoralPublicCommitment.longitude.is_not(None),
            )
        ).scalars()
    )
    points = defaultdict(list)
    for item in commitments:
        points[str(item.territory_id)].append((item.latitude, item.longitude))
    heatmap = []
    for territory_id, coordinates in points.items():
        row = rows.get(territory_id)
        if not row or row.get("suppressed"):
            continue
        heatmap.append(
            {
                "territory_id": territory_id,
                "territory_name": row["territory_name"],
                "latitude": round(sum(value[0] for value in coordinates) / len(coordinates), 6),
                "longitude": round(sum(value[1] for value in coordinates) / len(coordinates), 6),
                "intensity": row.get("demand_count") or 0,
                "public_reference_points": len(coordinates),
            }
        )
    cluster_cells = defaultdict(list)
    for item in heatmap:
        cluster_cells[(round(item["latitude"], 2), round(item["longitude"], 2))].append(item)
    clusters = [
        {
            "id": hashlib.sha256(f"{key[0]}:{key[1]}".encode()).hexdigest()[:12],
            "latitude": key[0],
            "longitude": key[1],
            "territories": [item["territory_name"] for item in values],
            "intensity": sum(item["intensity"] for item in values),
        }
        for key, values in cluster_cells.items()
    ]
    return {
        "snapshot_id": str(snapshot.id),
        "heatmap": heatmap,
        "clusters": sorted(clusters, key=lambda item: item["intensity"], reverse=True),
        "privacy": {
            "threshold": snapshot.privacy_threshold,
            "rule": "Somente grupos não suprimidos e coordenadas de locais públicos confirmados.",
        },
    }


def agenda_routes(tenant_id, mandate_id, start_date, end_date) -> dict:
    start_at = datetime.combine(start_date, time.min, tzinfo=UTC)
    end_at = datetime.combine(end_date + timedelta(days=1), time.min, tzinfo=UTC)
    events = list(
        db.session.execute(
            select(AgendaEvent)
            .where(
                AgendaEvent.tenant_id == tenant_id,
                AgendaEvent.status == AgendaEventStatus.AGENDADO,
                AgendaEvent.starts_at >= start_at,
                AgendaEvent.starts_at < end_at,
                AgendaEvent.territory_id.is_not(None),
                AgendaEvent.citizen_id.is_(None),
            )
            .order_by(AgendaEvent.starts_at)
        ).scalars()
    )
    public_points = defaultdict(list)
    for item in db.session.execute(
        select(ElectoralPublicCommitment).where(
            ElectoralPublicCommitment.tenant_id == tenant_id,
            ElectoralPublicCommitment.mandate_id == mandate_id,
            ElectoralPublicCommitment.location_is_public.is_(True),
            ElectoralPublicCommitment.latitude.is_not(None),
            ElectoralPublicCommitment.longitude.is_not(None),
        )
    ).scalars():
        public_points[item.territory_id].append((item.latitude, item.longitude))
    territory_ids = {item.territory_id for item in events}
    names = (
        {
            item.id: item.name
            for item in db.session.execute(
                select(Territory).where(
                    Territory.tenant_id == tenant_id, Territory.id.in_(territory_ids)
                )
            ).scalars()
        }
        if territory_ids
        else {}
    )
    stops = []
    omitted = 0
    for event in events:
        coords = public_points.get(event.territory_id)
        if not coords:
            omitted += 1
            continue
        stops.append(
            {
                "sequence": len(stops) + 1,
                "agenda_event_id": str(event.id),
                "title": event.title,
                "starts_at": event.starts_at.isoformat(),
                "territory_id": str(event.territory_id),
                "territory_name": names.get(event.territory_id),
                "latitude": round(sum(value[0] for value in coords) / len(coords), 6),
                "longitude": round(sum(value[1] for value in coords) / len(coords), 6),
            }
        )
    return {
        "from": start_date.isoformat(),
        "to": end_date.isoformat(),
        "stops": stops,
        "omitted_without_public_reference": omitted,
        "methodology": (
            "Ordem cronológica; coordenadas derivadas somente de locais públicos "
            "confirmados no território."
        ),
    }


def report_schedule_data(item) -> dict:
    return {
        "id": str(item.id),
        "name": item.name,
        "frequency": item.frequency,
        "template_report_job_id": str(item.template_report_job_id),
        "recipient_ids": item.recipient_ids,
        "active": item.active,
        "next_run_at": item.next_run_at.isoformat(),
        "last_run_at": item.last_run_at.isoformat() if item.last_run_at else None,
        "created_at": item.created_at.isoformat(),
    }


def create_report_schedule(tenant_id, mandate_id, user_id, data):
    name = str(data.get("name") or "").strip()
    frequency = str(data.get("frequency") or "").upper()
    try:
        template_id = uuid.UUID(str(data["template_report_job_id"]))
        recipient_ids = list(
            dict.fromkeys(str(uuid.UUID(str(value))) for value in data["recipient_ids"])
        )
        next_run_at = datetime.fromisoformat(
            str(data.get("next_run_at") or datetime.now(UTC)).replace("Z", "+00:00")
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise AdvancedFeatureError(
            "Modelo, destinatários e próxima execução são obrigatórios."
        ) from exc
    if len(name) < 3 or frequency not in SCHEDULE_FREQUENCIES or not recipient_ids:
        raise AdvancedFeatureError("Nome, frequência e destinatários internos são obrigatórios.")
    if next_run_at.tzinfo is None:
        next_run_at = next_run_at.replace(tzinfo=UTC)
    template = db.session.execute(
        select(ElectoralReportJob).where(
            ElectoralReportJob.id == template_id,
            ElectoralReportJob.tenant_id == tenant_id,
            ElectoralReportJob.mandate_id == mandate_id,
        )
    ).scalar_one_or_none()
    valid_users = set(
        str(value)
        for value in db.session.scalars(
            select(User.id).where(
                User.tenant_id == tenant_id,
                User.id.in_([uuid.UUID(value) for value in recipient_ids]),
                User.status == UserStatus.ACTIVE,
            )
        )
    )
    if template is None or valid_users != set(recipient_ids):
        raise AdvancedFeatureError("Modelo ou destinatário interno inválido.")
    item = ElectoralReportSchedule(
        tenant_id=tenant_id,
        mandate_id=mandate_id,
        created_by_id=user_id,
        template_report_job_id=template_id,
        name=name[:160],
        frequency=frequency,
        recipient_ids=recipient_ids,
        next_run_at=next_run_at,
    )
    db.session.add(item)
    db.session.flush()
    return item


def dispatch_due_report_schedules(tenant_id, now=None) -> int:
    now = now or datetime.now(UTC)
    schedules = list(
        db.session.execute(
            select(ElectoralReportSchedule)
            .where(
                ElectoralReportSchedule.tenant_id == tenant_id,
                ElectoralReportSchedule.active.is_(True),
                ElectoralReportSchedule.next_run_at <= now,
            )
            .with_for_update(skip_locked=True)
        ).scalars()
    )
    created = 0
    for schedule in schedules:
        template = db.session.get(ElectoralReportJob, schedule.template_report_job_id)
        if template is None:
            schedule.active = False
            continue
        for recipient_id in schedule.recipient_ids:
            job = ElectoralReportJob(
                tenant_id=tenant_id,
                mandate_id=schedule.mandate_id,
                requested_by_id=uuid.UUID(recipient_id),
                report_type=template.report_type,
                format=template.format,
                purpose=f"Relatório recorrente: {schedule.name}",
                filters=template.filters,
                source_metadata={
                    **template.source_metadata,
                    "schedule_id": str(schedule.id),
                },
            )
            db.session.add(job)
            db.session.flush()
            db.session.add(
                OutboxEvent(
                    tenant_id=tenant_id,
                    event_type=REPORT_EVENT,
                    aggregate_type="electoral_report_job",
                    aggregate_id=str(job.id),
                    payload={
                        "jobId": str(job.id),
                        "requestedById": recipient_id,
                        "schemaVersion": 1,
                        "idempotencyKey": str(job.id),
                    },
                )
            )
            created += 1
        schedule.last_run_at = now
        schedule.next_run_at = (
            now
            + {
                "DAILY": timedelta(days=1),
                "WEEKLY": timedelta(days=7),
                "MONTHLY": timedelta(days=30),
            }[schedule.frequency]
        )
    return created


def _electoral_units(election_id):
    datasets = (
        select(ElectoralCandidacy.dataset_version_id)
        .where(ElectoralCandidacy.election_id == election_id)
        .distinct()
    )
    return list(
        db.session.execute(
            select(ElectoralTerritory)
            .where(ElectoralTerritory.dataset_version_id.in_(datasets))
            .order_by(
                ElectoralTerritory.municipality_name,
                ElectoralTerritory.level,
                ElectoralTerritory.zone,
            )
        ).scalars()
    )


def _electoral_unit_label(item):
    suffix = f"Zona {item.zone}" if item.zone else item.level.value
    return f"{item.municipality_name} · {suffix}"
