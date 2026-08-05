import uuid
from datetime import UTC, date, datetime
from urllib.parse import urlparse

from sqlalchemy import func, select

from app.extensions import db
from app.models import (
    ElectoralCommitmentEvidence,
    ElectoralCommitmentHistory,
    ElectoralPublicCommitment,
    Tenant,
    Territory,
    User,
    UserStatus,
)

MANUAL_STATUSES = {"PLANNED", "IN_PROGRESS", "COMPLETED", "CANCELLED"}


class CommitmentError(ValueError):
    pass


def create_commitment(tenant_id, mandate_id, user_id, data: dict) -> ElectoralPublicCommitment:
    title = _required_text(data, "title", 180)
    description = _required_text(data, "description", 5000)
    territory = _territory(tenant_id, data.get("territory_id"))
    responsible = _responsible(tenant_id, data.get("responsible_user_id"))
    due_on = _date(data.get("due_on"), "due_on")
    latitude, longitude, public_name, is_public = _location(data)
    _validate_point_in_jurisdiction(tenant_id, latitude, longitude)
    item = ElectoralPublicCommitment(
        tenant_id=tenant_id,
        mandate_id=mandate_id,
        territory_id=territory.id,
        responsible_user_id=responsible.id,
        title=title,
        description=description,
        due_on=due_on,
        status="PLANNED",
        progress=0,
        public_location_name=public_name,
        latitude=latitude,
        longitude=longitude,
        location_is_public=is_public,
        created_by_id=user_id,
        updated_by_id=user_id,
    )
    db.session.add(item)
    db.session.flush()
    _history(item, "CREATED", user_id)
    return item


def update_commitment(item: ElectoralPublicCommitment, user_id, data: dict) -> None:
    if "title" in data:
        item.title = _required_text(data, "title", 180)
    if "description" in data:
        item.description = _required_text(data, "description", 5000)
    if "territory_id" in data:
        item.territory_id = _territory(item.tenant_id, data["territory_id"]).id
    if "responsible_user_id" in data:
        item.responsible_user_id = _responsible(
            item.tenant_id, data["responsible_user_id"]
        ).id
    if "due_on" in data:
        item.due_on = _date(data["due_on"], "due_on")
    if "status" in data:
        status = str(data["status"]).upper()
        if status not in MANUAL_STATUSES:
            raise CommitmentError("Estado manual inválido.")
        item.status = status
        if status == "COMPLETED":
            item.progress = 100
            item.completed_at = item.completed_at or datetime.now(UTC)
        elif item.completed_at:
            item.completed_at = None
    if "progress" in data and item.status != "COMPLETED":
        try:
            progress = int(data["progress"])
        except (TypeError, ValueError) as exc:
            raise CommitmentError("Progresso deve ser um inteiro entre 0 e 100.") from exc
        if not 0 <= progress <= 100:
            raise CommitmentError("Progresso deve ser um inteiro entre 0 e 100.")
        item.progress = progress
    location_fields = {"latitude", "longitude", "public_location_name", "location_is_public"}
    if location_fields & set(data):
        combined = {
            "latitude": data.get("latitude", item.latitude),
            "longitude": data.get("longitude", item.longitude),
            "public_location_name": data.get(
                "public_location_name", item.public_location_name
            ),
            "location_is_public": data.get("location_is_public", item.location_is_public),
        }
        latitude, longitude, public_name, is_public = _location(combined)
        _validate_point_in_jurisdiction(item.tenant_id, latitude, longitude)
        item.latitude = latitude
        item.longitude = longitude
        item.public_location_name = public_name
        item.location_is_public = is_public
    item.updated_by_id = user_id
    item.updated_at = datetime.now(UTC)
    db.session.flush()
    _history(item, "UPDATED", user_id)


def add_evidence(item: ElectoralPublicCommitment, user_id, data: dict):
    title = _required_text(data, "title", 180)
    public_url = _required_text(data, "public_url", 2000)
    parsed = urlparse(public_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise CommitmentError("A evidência deve possuir uma URL pública HTTP(S) válida.")
    evidence = ElectoralCommitmentEvidence(
        tenant_id=item.tenant_id,
        commitment_id=item.id,
        title=title,
        description=_optional_text(data.get("description"), 500),
        public_url=public_url,
        evidence_date=_date(data.get("evidence_date") or date.today(), "evidence_date"),
        added_by_id=user_id,
    )
    db.session.add(evidence)
    db.session.flush()
    _history(item, "EVIDENCE_ADDED", user_id, evidence_id=evidence.id)
    return evidence


def accessible_commitment(tenant_id, mandate_id, commitment_id):
    return db.session.execute(
        select(ElectoralPublicCommitment).where(
            ElectoralPublicCommitment.id == commitment_id,
            ElectoralPublicCommitment.tenant_id == tenant_id,
            ElectoralPublicCommitment.mandate_id == mandate_id,
        )
    ).scalar_one_or_none()


def commitment_data(item: ElectoralPublicCommitment, *, include_history=False) -> dict:
    territory = db.session.get(Territory, item.territory_id)
    responsible = db.session.get(User, item.responsible_user_id)
    evidence = list(db.session.execute(
        select(ElectoralCommitmentEvidence)
        .where(ElectoralCommitmentEvidence.commitment_id == item.id)
        .order_by(ElectoralCommitmentEvidence.evidence_date.desc())
    ).scalars())
    result = {
        "id": str(item.id),
        "title": item.title,
        "description": item.description,
        "territory": {
            "id": str(item.territory_id),
            "name": territory.name if territory else "Território removido",
        },
        "responsible": {
            "id": str(item.responsible_user_id),
            "name": responsible.name if responsible else "Responsável removido",
        },
        "due_on": item.due_on.isoformat(),
        "status": item.status,
        "effective_status": effective_status(item),
        "status_source": (
            "derived_deadline" if effective_status(item) == "OVERDUE" else "manual"
        ),
        "progress": item.progress,
        "public_location": (
            {
                "name": item.public_location_name,
                "latitude": item.latitude,
                "longitude": item.longitude,
                "confirmed_public": item.location_is_public,
            }
            if item.latitude is not None and item.longitude is not None
            else None
        ),
        "evidence": [evidence_data(entry) for entry in evidence],
        "completed_at": item.completed_at.isoformat() if item.completed_at else None,
        "created_at": item.created_at.isoformat(),
        "updated_at": item.updated_at.isoformat(),
    }
    if include_history:
        history = list(db.session.execute(
            select(ElectoralCommitmentHistory)
            .where(ElectoralCommitmentHistory.commitment_id == item.id)
            .order_by(ElectoralCommitmentHistory.version.desc())
        ).scalars())
        result["history"] = [history_data(entry) for entry in history]
    return result


def evidence_data(item: ElectoralCommitmentEvidence) -> dict:
    return {
        "id": str(item.id),
        "title": item.title,
        "description": item.description,
        "public_url": item.public_url,
        "evidence_date": item.evidence_date.isoformat(),
        "created_at": item.created_at.isoformat(),
    }


def history_data(item: ElectoralCommitmentHistory) -> dict:
    return {
        "id": str(item.id),
        "action": item.action,
        "version": item.version,
        "changed_by_id": str(item.changed_by_id),
        "snapshot": item.snapshot,
        "created_at": item.created_at.isoformat(),
    }


def operational_map_data(tenant_id, mandate_id) -> dict:
    tenant = db.session.get(Tenant, tenant_id)
    has_official_boundary = bool(tenant and tenant.jurisdiction_geojson)
    commitments = list(db.session.execute(
        select(ElectoralPublicCommitment).where(
            ElectoralPublicCommitment.tenant_id == tenant_id,
            ElectoralPublicCommitment.mandate_id == mandate_id,
            ElectoralPublicCommitment.status != "CANCELLED",
        )
    ).scalars())
    located = [
        item for item in commitments
        if has_official_boundary
        and item.location_is_public
        and item.latitude is not None
        and item.longitude is not None
    ]
    warnings = [
        "Territórios operacionais sem geometria oficial permanecem apenas na tabela; "
        "nenhum polígono foi criado artificialmente."
    ]
    if not has_official_boundary:
        warnings.append(
            "A malha oficial da jurisdição ainda não foi carregada; pontos permanecem fora do mapa."
        )
    return {
        "geometry_available": has_official_boundary,
        "boundary": tenant.jurisdiction_geojson if tenant else None,
        "geometry_kind": "official_jurisdiction_boundary",
        "source": {
            "name": "IBGE - Malha Municipal Digital",
            "url": "https://servicodados.ibge.gov.br/api/v3/malhas",
            "official": True,
            "ibge_code": tenant.jurisdiction_ibge_code if tenant else None,
        },
        "features": [
            {
                "type": "Feature",
                "id": str(item.id),
                "geometry": {
                    "type": "Point",
                    "coordinates": [item.longitude, item.latitude],
                },
                "properties": {
                    "commitment_id": str(item.id),
                    "title": item.title,
                    "territory_id": str(item.territory_id),
                    "status": effective_status(item),
                    "progress": item.progress,
                    "location_name": item.public_location_name,
                },
            }
            for item in located
        ],
        "unmapped_commitments": len(commitments) - len(located),
        "warnings": warnings,
    }


def effective_status(item: ElectoralPublicCommitment, today=None) -> str:
    reference = today or date.today()
    if item.status not in {"COMPLETED", "CANCELLED"} and item.due_on < reference:
        return "OVERDUE"
    return item.status


def _history(item, action: str, user_id, *, evidence_id=None) -> None:
    snapshot = {
        "title": item.title,
        "description": item.description,
        "territory_id": str(item.territory_id),
        "responsible_user_id": str(item.responsible_user_id),
        "due_on": item.due_on.isoformat(),
        "status": item.status,
        "progress": item.progress,
        "public_location_name": item.public_location_name,
        "latitude": item.latitude,
        "longitude": item.longitude,
    }
    if evidence_id:
        snapshot["evidence_id"] = str(evidence_id)
    version = db.session.scalar(
        select(func.max(ElectoralCommitmentHistory.version)).where(
            ElectoralCommitmentHistory.tenant_id == item.tenant_id,
            ElectoralCommitmentHistory.commitment_id == item.id,
        )
    ) or 0
    history = ElectoralCommitmentHistory(
        tenant_id=item.tenant_id,
        commitment_id=item.id,
        action=action,
        version=version + 1,
        changed_by_id=user_id,
        snapshot=snapshot,
    )
    db.session.add(history)
    db.session.flush()


def _territory(tenant_id, value) -> Territory:
    try:
        territory_id = uuid.UUID(str(value))
    except (TypeError, ValueError) as exc:
        raise CommitmentError("Território inválido.") from exc
    item = db.session.execute(
        select(Territory).where(
            Territory.id == territory_id,
            Territory.tenant_id == tenant_id,
            Territory.active.is_(True),
        )
    ).scalar_one_or_none()
    if not item:
        raise CommitmentError("Território ativo não encontrado no gabinete.")
    return item


def _responsible(tenant_id, value) -> User:
    try:
        user_id = uuid.UUID(str(value))
    except (TypeError, ValueError) as exc:
        raise CommitmentError("Responsável inválido.") from exc
    item = db.session.execute(
        select(User).where(
            User.id == user_id,
            User.tenant_id == tenant_id,
            User.status == UserStatus.ACTIVE,
        )
    ).scalar_one_or_none()
    if not item:
        raise CommitmentError("Responsável ativo não encontrado no gabinete.")
    return item


def _location(data: dict):
    latitude = data.get("latitude")
    longitude = data.get("longitude")
    if latitude in (None, "") and longitude in (None, ""):
        return None, None, _optional_text(data.get("public_location_name"), 180), False
    if latitude in (None, "") or longitude in (None, ""):
        raise CommitmentError("Latitude e longitude devem ser informadas em conjunto.")
    try:
        latitude = float(latitude)
        longitude = float(longitude)
    except (TypeError, ValueError) as exc:
        raise CommitmentError("Coordenadas inválidas.") from exc
    if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
        raise CommitmentError("Coordenadas fora dos limites válidos.")
    if data.get("location_is_public") is not True:
        raise CommitmentError("Confirme que o ponto representa um local público.")
    public_name = _optional_text(data.get("public_location_name"), 180)
    if not public_name:
        raise CommitmentError("Informe o nome do local público.")
    return latitude, longitude, public_name, True


def _validate_point_in_jurisdiction(tenant_id, latitude, longitude) -> None:
    if latitude is None or longitude is None:
        return
    tenant = db.session.get(Tenant, tenant_id)
    collection = tenant.jurisdiction_geojson if tenant else None
    if not collection:
        return
    features = (
        collection.get("features", [])
        if collection.get("type") == "FeatureCollection"
        else [collection]
    )
    polygons = []
    for feature in features:
        geometry = feature.get("geometry", feature)
        if geometry.get("type") == "Polygon":
            polygons.append(geometry.get("coordinates", []))
        elif geometry.get("type") == "MultiPolygon":
            polygons.extend(geometry.get("coordinates", []))
    inside_jurisdiction = any(
        _point_in_polygon(longitude, latitude, polygon) for polygon in polygons
    )
    if polygons and not inside_jurisdiction:
        raise CommitmentError("O ponto público deve estar dentro da jurisdição oficial.")


def _point_in_polygon(x: float, y: float, polygon: list) -> bool:
    if not polygon or not _point_in_ring(x, y, polygon[0]):
        return False
    return not any(_point_in_ring(x, y, hole) for hole in polygon[1:])


def _point_in_ring(x: float, y: float, ring: list) -> bool:
    inside = False
    previous = ring[-1] if ring else None
    for current in ring:
        if previous is None:
            break
        x1, y1 = previous[:2]
        x2, y2 = current[:2]
        if (y1 > y) != (y2 > y):
            crossing = (x2 - x1) * (y - y1) / (y2 - y1) + x1
            if x < crossing:
                inside = not inside
        previous = current
    return inside


def _required_text(data: dict, key: str, limit: int) -> str:
    value = str(data.get(key) or "").strip()
    if not value:
        raise CommitmentError(f"{key} é obrigatório.")
    if len(value) > limit:
        raise CommitmentError(f"{key} excede {limit} caracteres.")
    return value


def _optional_text(value, limit: int) -> str | None:
    text = str(value or "").strip()
    if len(text) > limit:
        raise CommitmentError(f"Texto excede {limit} caracteres.")
    return text or None


def _date(value, key: str) -> date:
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError) as exc:
        raise CommitmentError(f"{key} deve ser uma data válida.") from exc
