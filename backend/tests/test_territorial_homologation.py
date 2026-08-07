from collections import Counter
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.extensions import db
from app.models import (
    ExternalAgency,
    RequestCategory,
    RequestPriority,
    RequestSource,
    RequestStatus,
    ServiceRequest,
    Tenant,
    Territory,
    User,
)
from app.territorial_homologation import prepare_territorial_homologation


def test_territorial_homologation_seed_is_repeatable_and_covers_scenarios(app):
    reference = datetime(2026, 8, 7, 16, 30, tzinfo=UTC)
    with app.app_context():
        tenant = db.session.execute(
            select(Tenant).where(Tenant.slug == "gabinete-a")
        ).scalar_one()
        tenant.jurisdiction_center_latitude = -21.7619
        tenant.jurisdiction_center_longitude = -43.3496
        tenant.jurisdiction_bounds = {
            "minLatitude": -21.92,
            "maxLatitude": -21.58,
            "minLongitude": -43.58,
            "maxLongitude": -43.17,
        }
        users = list(db.session.scalars(select(User).where(User.tenant_id == tenant.id)))
        territories = [
            Territory(tenant_id=tenant.id, name=f"Território {index}") for index in range(4)
        ]
        categories = [
            RequestCategory(tenant_id=tenant.id, name="Saúde", sla_hours=24),
            RequestCategory(tenant_id=tenant.id, name="Obras", sla_hours=96),
        ]
        agencies = [
            ExternalAgency(tenant_id=tenant.id, name="Secretaria A"),
            ExternalAgency(tenant_id=tenant.id, name="Secretaria B"),
        ]
        db.session.add_all([*territories, *categories, *agencies])
        db.session.flush()
        db.session.add_all(
            [
                ServiceRequest(
                    tenant_id=tenant.id,
                    protocol=f"GF-2026-{index:06d}",
                    source=RequestSource.PRESENCIAL,
                    title=f"Solicitação sintética {index}",
                    description="Massa exclusiva de teste.",
                    status=RequestStatus.EM_ATENDIMENTO,
                    priority=RequestPriority.MEDIA,
                    created_by_id=users[0].id,
                )
                for index in range(40)
            ]
        )
        db.session.commit()

        first = prepare_territorial_homologation(tenant, reference_time=reference)
        requests = list(
            db.session.scalars(
                select(ServiceRequest)
                .where(ServiceRequest.tenant_id == tenant.id)
                .order_by(ServiceRequest.protocol)
            )
        )
        snapshot = [
            (
                item.id,
                item.created_at,
                item.due_at,
                item.geocode_status,
                item.latitude,
                item.longitude,
                item.territory_id,
                item.category_id,
                item.agency_id,
                item.responsible_id,
            )
            for item in requests
        ]

        second = prepare_territorial_homologation(tenant, reference_time=reference)
        repeated = list(
            db.session.scalars(
                select(ServiceRequest)
                .where(ServiceRequest.tenant_id == tenant.id)
                .order_by(ServiceRequest.protocol)
            )
        )
        repeated_snapshot = [
            (
                item.id,
                item.created_at,
                item.due_at,
                item.geocode_status,
                item.latitude,
                item.longitude,
                item.territory_id,
                item.category_id,
                item.agency_id,
                item.responsible_id,
            )
            for item in repeated
        ]

        assert first == second
        assert snapshot == repeated_snapshot
        assert first["current_window"] == 24
        assert first["previous_window"] == 16
        assert set(first["geocode_statuses"]) == {
            "APPROXIMATE",
            "VERIFIED",
            "UNRESOLVED",
            "AMBIGUOUS",
            "OUTSIDE_JURISDICTION",
        }
        assert all(total > 0 for total in first["geocode_statuses"].values())
        assert all(item.territory_id is not None for item in requests)
        assert all(item.category_id is not None for item in requests)
        assert all(item.agency_id is not None for item in requests)
        assert any(item.responsible_id is None for item in requests)
        assert any(item.responsible_id is not None for item in requests)
        assert any(item.due_at is None for item in requests)
        database_reference = reference
        if requests[0].created_at.tzinfo is None:
            database_reference = reference.replace(tzinfo=None)
        assert any(item.due_at < database_reference for item in requests if item.due_at)
        assert any(item.due_at > database_reference for item in requests if item.due_at)

        eligible_cells = Counter(
            (
                item.territory_id,
                round(item.latitude, 2),
                round(item.longitude, 2),
            )
            for item in requests
            if item.geocode_status in {"APPROXIMATE", "VERIFIED"}
        )
        assert sum(total < 3 for total in eligible_cells.values()) == 2
        assert any(total >= 3 for total in eligible_cells.values())

        current_start = reference.replace(hour=12, minute=0, second=0, microsecond=0) - timedelta(
            days=30
        )
        previous_start = current_start - timedelta(days=30)
        if requests[0].created_at.tzinfo is None:
            current_start = current_start.replace(tzinfo=None)
            previous_start = previous_start.replace(tzinfo=None)
        assert sum(item.created_at >= current_start for item in requests) == 24
        assert sum(previous_start <= item.created_at < current_start for item in requests) == 16
