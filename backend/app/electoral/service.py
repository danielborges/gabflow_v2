from datetime import date

from sqlalchemy import select

from app.extensions import db
from app.models import Mandate, MandateStatus, Role, Tenant, User, UserStatus

ACTIVE_PROFILE_STATUSES = {"ATIVO", "ATUAL", "ACTIVE", "CURRENT"}


def active_mandate(tenant_id) -> Mandate | None:
    return db.session.execute(
        select(Mandate).where(
            Mandate.tenant_id == tenant_id,
            Mandate.status == MandateStatus.ACTIVE,
        )
    ).scalar_one_or_none()


def sync_active_mandate(tenant: Tenant) -> Mandate | None:
    representative = db.session.execute(
        select(User).where(
            User.tenant_id == tenant.id,
            User.role == Role.REPRESENTATIVE,
            User.status == UserStatus.ACTIVE,
        )
    ).scalar_one_or_none()
    profile = tenant.representative_info or {}
    profile_active = str(profile.get("statusMandato") or "ATIVO").upper() in {
        "ATIVO",
        "ATUAL",
        "ACTIVE",
        "CURRENT",
    }
    current = active_mandate(tenant.id)
    if representative is None or not profile_active:
        if current is not None:
            current.status = MandateStatus.INACTIVE
        return None

    if current is not None and current.representative_user_id != representative.id:
        current.status = MandateStatus.INACTIVE
        current = None
    if current is None:
        current = (
            db.session.execute(
                select(Mandate)
                .where(
                    Mandate.tenant_id == tenant.id,
                    Mandate.representative_user_id == representative.id,
                )
                .order_by(Mandate.created_at.desc())
            )
            .scalars()
            .first()
        )
    values = _profile_mandate_values(tenant)
    if current is None:
        current = Mandate(
            tenant_id=tenant.id,
            representative_user_id=representative.id,
            status=MandateStatus.ACTIVE,
            **values,
        )
        db.session.add(current)
    else:
        current.status = MandateStatus.ACTIVE
        current.office = values["office"]
        current.jurisdiction = values["jurisdiction"]
        current.starts_on = values["starts_on"]
        current.ends_on = values["ends_on"]
        current.source_metadata = values["source_metadata"]
    return current


def _profile_mandate_values(tenant: Tenant) -> dict:
    profile = tenant.representative_info or {}
    mandates = profile.get("mandatos") if isinstance(profile.get("mandatos"), list) else []
    active = next(
        (
            item
            for item in mandates
            if isinstance(item, dict)
            and str(item.get("status") or "").upper() in ACTIVE_PROFILE_STATUSES
        ),
        {},
    )
    return {
        "office": str(active.get("cargo") or tenant.chamber_type or "").strip()[:120] or None,
        "jurisdiction": str(tenant.jurisdiction_name or "").strip()[:160] or None,
        "starts_on": _date(active.get("inicio")),
        "ends_on": _date(active.get("fim")),
        "source_metadata": {
            "origin": "tenant_representative_profile",
            "legislature": str(active.get("legislatura") or "").strip()[:80] or None,
        },
    }


def _date(value) -> date | None:
    try:
        return date.fromisoformat(str(value)) if value else None
    except ValueError:
        return None
