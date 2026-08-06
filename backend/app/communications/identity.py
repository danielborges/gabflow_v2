import re
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.extensions import db
from app.models import (
    ChannelAssistedSetting,
    ChannelIdentityReview,
    ChannelIdentityReviewStatus,
    ChannelMessage,
    Citizen,
    RequestSource,
)

SUPPORTED_IDENTITY_CHANNELS = {RequestSource.WHATSAPP, RequestSource.EMAIL}
DEFAULT_SLA_HOURS = 24
DEFAULT_RETENTION_DAYS = 365


def get_assisted_settings(tenant_id: uuid.UUID) -> ChannelAssistedSetting | None:
    return db.session.execute(
        select(ChannelAssistedSetting).where(ChannelAssistedSetting.tenant_id == tenant_id)
    ).scalar_one_or_none()


def assisted_settings_data(item: ChannelAssistedSetting | None) -> dict:
    return {
        "baseLegalPadrao": item.default_legal_basis if item else None,
        "slaHoras": item.sla_hours if item else DEFAULT_SLA_HOURS,
        "retencaoDias": item.retention_days if item else DEFAULT_RETENTION_DAYS,
        "atualizadaEm": (
            item.updated_at.isoformat() if item and item.updated_at is not None else None
        ),
    }


def normalize_channel_contact(channel: RequestSource, value: str | None) -> str | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    if channel == RequestSource.EMAIL:
        normalized = raw.casefold()
        return normalized if "@" in normalized else None
    if channel == RequestSource.WHATSAPP:
        digits = re.sub(r"\D", "", raw)
        if digits.startswith("55") and len(digits) in {12, 13}:
            digits = digits[2:]
        return digits if len(digits) in {10, 11} else None
    return None


def _contact_matches(channel: RequestSource, sender_contact: str | None, citizen: Citizen) -> bool:
    expected = normalize_channel_contact(channel, sender_contact)
    if expected is None:
        return False
    accepted_types = {
        RequestSource.EMAIL: {"EMAIL"},
        RequestSource.WHATSAPP: {"WHATSAPP", "TELEFONE"},
    }[channel]
    for contact in citizen.contacts or []:
        if not isinstance(contact, dict):
            continue
        if str(contact.get("tipo", "")).upper() not in accepted_types:
            continue
        if normalize_channel_contact(channel, contact.get("valor")) == expected:
            return True
    return False


def prepare_identity_review(item: ChannelMessage) -> ChannelIdentityReview | None:
    if item.channel not in SUPPORTED_IDENTITY_CHANNELS:
        return None
    existing = db.session.execute(
        select(ChannelIdentityReview).where(
            ChannelIdentityReview.tenant_id == item.tenant_id,
            ChannelIdentityReview.message_id == item.id,
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing

    citizens = db.session.execute(
        select(Citizen).where(
            Citizen.tenant_id == item.tenant_id,
            Citizen.anonymized_at.is_(None),
        )
    ).scalars()
    matches = [
        citizen
        for citizen in citizens
        if _contact_matches(item.channel, item.sender_contact, citizen)
    ]
    candidate_ids = [str(citizen.id) for citizen in matches]
    state = {
        0: "SEM_CORRESPONDENCIA",
        1: "CORRESPONDENCIA_UNICA",
    }.get(len(candidate_ids), "CORRESPONDENCIA_AMBIGUA")
    settings = get_assisted_settings(item.tenant_id)
    review = ChannelIdentityReview(
        tenant_id=item.tenant_id,
        message_id=item.id,
        status=ChannelIdentityReviewStatus.PENDENTE,
        resolution_state=state,
        candidate_citizen_ids=candidate_ids,
        match_basis=["CONTATO_EXATO"] if candidate_ids else [],
        due_at=datetime.now(UTC)
        + timedelta(hours=settings.sla_hours if settings else DEFAULT_SLA_HOURS),
    )
    db.session.add(review)
    db.session.flush()
    return review


def parse_candidate_ids(review: ChannelIdentityReview) -> list[uuid.UUID]:
    result = []
    for value in review.candidate_citizen_ids or []:
        try:
            result.append(uuid.UUID(str(value)))
        except (TypeError, ValueError):
            continue
    return result
