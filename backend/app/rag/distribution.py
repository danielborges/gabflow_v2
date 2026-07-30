import re
import unicodedata
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime

from sqlalchemy import select

from app.extensions import db
from app.models import (
    GlobalDistributionPolicy,
    GlobalEntitlementStatus,
    GlobalKnowledgeCollection,
    GlobalKnowledgeDocumentVersion,
    GlobalKnowledgeEntitlement,
    GlobalUpdateMode,
    GlobalVersionStatus,
    RagIngestionStatus,
    Tenant,
)


@dataclass(frozen=True)
class CollectionAccess:
    collection: GlobalKnowledgeCollection
    enabled: bool
    reason: str
    entitlement: GlobalKnowledgeEntitlement | None


def resolve_collection_access(
    tenant: Tenant,
    collection: GlobalKnowledgeCollection,
    entitlement: GlobalKnowledgeEntitlement | None,
    *,
    today: date | None = None,
) -> CollectionAccess:
    reference_date = today or datetime.now(UTC).date()
    if collection.status.value != "PUBLICADA":
        return CollectionAccess(collection, False, "COLLECTION_NOT_PUBLISHED", entitlement)
    if not jurisdiction_matches(tenant, collection.jurisdiction):
        return CollectionAccess(collection, False, "JURISDICTION_MISMATCH", entitlement)

    entitlement_active = _entitlement_active(entitlement, reference_date)
    policy = collection.distribution_policy
    if policy == GlobalDistributionPolicy.OBRIGATORIA:
        return CollectionAccess(collection, True, "MANDATORY", entitlement)
    if policy == GlobalDistributionPolicy.PADRAO:
        enabled = entitlement is None or entitlement.status == GlobalEntitlementStatus.ATIVA
        return CollectionAccess(
            collection,
            enabled,
            "DEFAULT" if enabled else "TENANT_OPT_OUT",
            entitlement,
        )
    if policy == GlobalDistributionPolicy.OPCIONAL:
        return CollectionAccess(
            collection,
            entitlement_active,
            "TENANT_OPT_IN" if entitlement_active else "OPT_IN_REQUIRED",
            entitlement,
        )
    if policy == GlobalDistributionPolicy.DIRECIONADA:
        enabled = entitlement_active and entitlement.grant_source == "GLOBAL_GRANT"
        return CollectionAccess(
            collection,
            enabled,
            "GLOBAL_GRANT" if enabled else "GLOBAL_GRANT_REQUIRED",
            entitlement,
        )
    if policy == GlobalDistributionPolicy.RESTRITA_JURISDICAO:
        return CollectionAccess(collection, True, "JURISDICTION_MATCH", entitlement)
    return CollectionAccess(collection, False, "PLATFORM_PRIVATE", entitlement)


def collection_access_for_tenant(
    tenant_id: uuid.UUID,
) -> list[CollectionAccess]:
    tenant = db.session.get(Tenant, tenant_id)
    if tenant is None:
        return []
    entitlements = {
        item.collection_id: item
        for item in db.session.execute(
            select(GlobalKnowledgeEntitlement).where(
                GlobalKnowledgeEntitlement.tenant_id == tenant_id
            )
        ).scalars()
    }
    collections = db.session.execute(
        select(GlobalKnowledgeCollection).order_by(GlobalKnowledgeCollection.name)
    ).scalars()
    return [
        resolve_collection_access(
            tenant,
            collection,
            entitlements.get(collection.id),
        )
        for collection in collections
    ]


def global_versions_for_tenant(
    tenant_id: uuid.UUID,
) -> list[GlobalKnowledgeDocumentVersion]:
    access = [item for item in collection_access_for_tenant(tenant_id) if item.enabled]
    if not access:
        return []
    access_by_collection = {item.collection.id: item for item in access}
    today = datetime.now(UTC).date()
    versions = db.session.execute(
        select(GlobalKnowledgeDocumentVersion)
        .join(GlobalKnowledgeDocumentVersion.document)
        .where(
            GlobalKnowledgeDocumentVersion.ingestion_status == RagIngestionStatus.INDEXADO,
            GlobalKnowledgeDocumentVersion.publication_status.in_(
                {
                    GlobalVersionStatus.PUBLICADA,
                    GlobalVersionStatus.SUBSTITUIDA,
                }
            ),
        )
    ).scalars()
    eligible = []
    for version in versions:
        access_item = access_by_collection.get(version.document.collection_id)
        if access_item is None or not _version_valid(version, today):
            continue
        entitlement = access_item.entitlement
        if (
            entitlement
            and entitlement.update_mode == GlobalUpdateMode.FIXADA
            and entitlement.pinned_version_id
            and version.document_id == entitlement.pinned_version.document_id
            and version.id != entitlement.pinned_version_id
        ):
            continue
        if version.publication_status == GlobalVersionStatus.SUBSTITUIDA and not (
            entitlement
            and entitlement.update_mode == GlobalUpdateMode.FIXADA
            and entitlement.pinned_version_id == version.id
        ):
            continue
        eligible.append(version)
    return eligible


def jurisdiction_matches(tenant: Tenant, jurisdiction: dict | None) -> bool:
    rules = jurisdiction or {}
    if not rules:
        return True
    aliases = {
        "pais": "BR",
        "country": "BR",
        "uf": tenant.jurisdiction_state,
        "estado": tenant.jurisdiction_state,
        "state": tenant.jurisdiction_state,
        "municipio": tenant.jurisdiction_city,
        "cidade": tenant.jurisdiction_city,
        "city": tenant.jurisdiction_city,
        "codigoIbge": tenant.jurisdiction_ibge_code,
        "ibge": tenant.jurisdiction_ibge_code,
        "tipoCasa": tenant.chamber_type,
        "chamberType": tenant.chamber_type,
    }
    for key, expected in rules.items():
        if key == "esfera":
            sphere = _normalize(expected)
            if sphere == "FEDERAL":
                continue
            if sphere == "ESTADUAL" and tenant.jurisdiction_state:
                continue
            if sphere == "MUNICIPAL" and tenant.jurisdiction_city:
                continue
            return False
        actual = aliases.get(key)
        if actual is None or not _matches_value(actual, expected):
            return False
    return True


def entitlement_data(item: GlobalKnowledgeEntitlement | None) -> dict | None:
    if item is None:
        return None
    return {
        "id": str(item.id),
        "estado": item.status.value,
        "modoAtualizacao": item.update_mode.value,
        "versaoFixadaId": (str(item.pinned_version_id) if item.pinned_version_id else None),
        "origem": item.grant_source,
        "justificativa": item.justification,
        "vigenteDesde": item.valid_from.isoformat() if item.valid_from else None,
        "vigenteAte": item.valid_until.isoformat() if item.valid_until else None,
    }


def _entitlement_active(entitlement: GlobalKnowledgeEntitlement | None, today: date) -> bool:
    return bool(
        entitlement
        and entitlement.status == GlobalEntitlementStatus.ATIVA
        and (entitlement.valid_from is None or entitlement.valid_from <= today)
        and (entitlement.valid_until is None or entitlement.valid_until >= today)
    )


def _version_valid(version: GlobalKnowledgeDocumentVersion, today: date) -> bool:
    return bool(
        (version.valid_from is None or version.valid_from <= today)
        and (version.valid_until is None or version.valid_until >= today)
    )


def _matches_value(actual: object, expected: object) -> bool:
    if isinstance(expected, list):
        return any(_normalize(actual) == _normalize(item) for item in expected)
    return _normalize(actual) == _normalize(expected)


def _normalize(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or "").strip().upper())
    return re.sub(r"\s+", " ", "".join(char for char in text if not unicodedata.combining(char)))
