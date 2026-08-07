from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.extensions import db
from app.models import (
    ExternalAgency,
    RequestCategory,
    ServiceRequest,
    Tenant,
    Territory,
    User,
    UserStatus,
)

GEOLOCATION_PATTERN = (
    "APPROXIMATE",
    "APPROXIMATE",
    "APPROXIMATE",
    "APPROXIMATE",
    "VERIFIED",
    "VERIFIED",
    "VERIFIED",
    "UNRESOLVED",
    "AMBIGUOUS",
    "OUTSIDE_JURISDICTION",
)
MINIMUM_REQUESTS = 30


class TerritorialHomologationError(ValueError):
    pass


def prepare_territorial_homologation(
    tenant: Tenant,
    *,
    reference_time: datetime | None = None,
) -> dict:
    """Prepare a repeatable, synthetic territorial homologation data distribution."""

    requests = list(
        db.session.scalars(
            select(ServiceRequest)
            .where(ServiceRequest.tenant_id == tenant.id)
            .order_by(ServiceRequest.protocol, ServiceRequest.id)
        )
    )
    if len(requests) < MINIMUM_REQUESTS:
        raise TerritorialHomologationError(
            f"O tenant precisa de pelo menos {MINIMUM_REQUESTS} solicitações para a carga."
        )

    territories = list(
        db.session.scalars(
            select(Territory)
            .where(Territory.tenant_id == tenant.id, Territory.active.is_(True))
            .order_by(Territory.name, Territory.id)
        )
    )
    categories = list(
        db.session.scalars(
            select(RequestCategory)
            .where(RequestCategory.tenant_id == tenant.id, RequestCategory.active.is_(True))
            .order_by(RequestCategory.name, RequestCategory.id)
        )
    )
    agencies = list(
        db.session.scalars(
            select(ExternalAgency)
            .where(ExternalAgency.tenant_id == tenant.id, ExternalAgency.active.is_(True))
            .order_by(ExternalAgency.name, ExternalAgency.id)
        )
    )
    workers = list(
        db.session.scalars(
            select(User)
            .where(User.tenant_id == tenant.id, User.status == UserStatus.ACTIVE)
            .order_by(User.name, User.id)
        )
    )
    missing = [
        label
        for label, collection in (
            ("territórios", territories),
            ("categorias", categories),
            ("órgãos", agencies),
            ("trabalhadores", workers),
        )
        if not collection
    ]
    if missing:
        raise TerritorialHomologationError(
            "Pré-requisitos ausentes para a carga: " + ", ".join(missing) + "."
        )

    reference = reference_time or datetime.now(UTC)
    if reference.tzinfo is None:
        reference = reference.replace(tzinfo=UTC)
    anchor = reference.astimezone(UTC).replace(hour=12, minute=0, second=0, microsecond=0)
    center_latitude = tenant.jurisdiction_center_latitude
    center_longitude = tenant.jurisdiction_center_longitude
    if center_latitude is None or center_longitude is None:
        raise TerritorialHomologationError(
            "O tenant precisa de um centro territorial governado para a carga."
        )

    bounds = tenant.jurisdiction_bounds or {}
    outside_latitude = float(bounds.get("maxLatitude", center_latitude + 0.15)) + 0.03
    status_counts = {status: 0 for status in GEOLOCATION_PATTERN}
    current_window = 0
    previous_window = 0
    insufficient_cells = 0

    for index, item in enumerate(requests):
        territory_index = index % len(territories)
        territory = territories[territory_index]
        category = categories[index % len(categories)]
        geocode_status = GEOLOCATION_PATTERN[index % len(GEOLOCATION_PATTERN)]

        # Two unique cells exercise privacy suppression; every other eligible point is
        # clustered deterministically by territory so authorized cells retain >= 3 items.
        column = territory_index % 5
        row = (territory_index // 5) % 3
        base_latitude = float(center_latitude) + ((row - 1) * 0.025)
        base_longitude = float(center_longitude) + ((column - 2) * 0.025)
        if index < 2:
            base_latitude += 0.071 + (index * 0.013)
            base_longitude += 0.067 + (index * 0.013)
            insufficient_cells += 1

        if geocode_status == "UNRESOLVED":
            item.latitude = None
            item.longitude = None
            item.geocode_source = None
            item.geocode_method = None
            item.geocode_confidence = None
            item.geocode_verified = False
            item.geocoded_at = None
        elif geocode_status == "OUTSIDE_JURISDICTION":
            item.latitude = outside_latitude + (territory_index * 0.001)
            item.longitude = base_longitude
            item.geocode_source = "HOMOLOGATION_FIXTURE"
            item.geocode_method = "SYNTHETIC_OUTSIDE"
            item.geocode_confidence = 0.98
            item.geocode_verified = False
            item.geocoded_at = anchor - timedelta(hours=index % 72)
        elif geocode_status == "AMBIGUOUS":
            item.latitude = base_latitude + 0.004
            item.longitude = base_longitude + 0.004
            item.geocode_source = "HOMOLOGATION_FIXTURE"
            item.geocode_method = "SYNTHETIC_AMBIGUOUS"
            item.geocode_confidence = 0.35
            item.geocode_verified = False
            item.geocoded_at = anchor - timedelta(hours=index % 72)
        else:
            item.latitude = base_latitude
            item.longitude = base_longitude
            item.geocode_source = "HOMOLOGATION_FIXTURE"
            item.geocode_method = (
                "SYNTHETIC_VERIFIED" if geocode_status == "VERIFIED" else "SYNTHETIC_APPROXIMATE"
            )
            item.geocode_confidence = 0.99 if geocode_status == "VERIFIED" else 0.72
            item.geocode_verified = geocode_status == "VERIFIED"
            item.geocoded_at = anchor - timedelta(hours=index % 72)
        item.geocode_status = geocode_status
        status_counts[geocode_status] += 1

        # Forty percent form the equivalent previous window; the rest stay in the
        # current 30-day window. Re-running on the same day writes the same values.
        # Rotate whole territory rounds between windows. Using the raw request index
        # would correlate the window with territory whenever their counts share a
        # divisor, leaving some territories without a comparison baseline.
        territory_round = index // len(territories)
        if territory_round % 5 in {0, 1}:
            days_ago = 31 + (index % 28)
            previous_window += 1
        else:
            days_ago = 1 + (index % 28)
            current_window += 1
        created_at = anchor - timedelta(days=days_ago, hours=index % 8)
        item.created_at = created_at
        item.updated_at = created_at + timedelta(hours=12)

        item.territory_id = territory.id
        item.category_id = category.id
        item.category = category.name
        item.agency_id = agencies[(index // 2) % len(agencies)].id
        item.responsible_id = (
            None if index % 17 == 0 else workers[(index // 3) % len(workers)].id
        )

        due_pattern = index % 6
        if due_pattern == 0:
            item.due_at = anchor - timedelta(days=10 + (index % 12))
        elif due_pattern == 1:
            item.due_at = anchor - timedelta(days=1 + (index % 5))
        elif due_pattern == 2:
            item.due_at = anchor + timedelta(days=3 + (index % 4))
        elif due_pattern == 3:
            item.due_at = anchor + timedelta(days=14 + (index % 14))
        elif due_pattern == 4:
            item.due_at = created_at + timedelta(hours=category.sla_hours)
        else:
            item.due_at = None

    db.session.commit()
    return {
        "tenant": tenant.slug,
        "requests": len(requests),
        "current_window": current_window,
        "previous_window": previous_window,
        "geocode_statuses": status_counts,
        "territories": len(territories),
        "categories": len(categories),
        "agencies": len(agencies),
        "workers": len(workers),
        "insufficient_cells": insufficient_cells,
        "reference_date": anchor.date().isoformat(),
    }


def prepare_territorial_homologation_by_slug(
    tenant_slug: str,
    *,
    reference_time: datetime | None = None,
) -> dict:
    tenant = db.session.execute(
        select(Tenant).where(Tenant.slug == tenant_slug)
    ).scalar_one_or_none()
    if tenant is None:
        raise TerritorialHomologationError("Tenant não encontrado.")
    return prepare_territorial_homologation(tenant, reference_time=reference_time)
