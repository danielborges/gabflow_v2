from __future__ import annotations

import hashlib
from dataclasses import dataclass
from enum import StrEnum


class GeocodeStatus(StrEnum):
    VERIFIED = "VERIFIED"
    APPROXIMATE = "APPROXIMATE"
    AMBIGUOUS = "AMBIGUOUS"
    UNRESOLVED = "UNRESOLVED"
    OUTSIDE_JURISDICTION = "OUTSIDE_JURISDICTION"


class GeocodeGranularity(StrEnum):
    ADDRESS = "ADDRESS"
    STREET = "STREET"
    NEIGHBORHOOD = "NEIGHBORHOOD"
    POSTCODE = "POSTCODE"
    LOCALITY = "LOCALITY"
    REGION = "REGION"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class GeocodeQuery:
    text: str
    country_code: str = "BR"
    jurisdiction_bbox: tuple[float, float, float, float] | None = None

    def __post_init__(self) -> None:
        normalized_text = " ".join(self.text.split())
        if not normalized_text or len(normalized_text) > 512:
            raise ValueError("O endereço deve conter entre 1 e 512 caracteres.")
        country = self.country_code.strip().upper()
        if len(country) != 2 or not country.isalpha():
            raise ValueError("O país deve usar código ISO alpha-2.")
        if self.jurisdiction_bbox is not None:
            min_lon, min_lat, max_lon, max_lat = self.jurisdiction_bbox
            if not (-180 <= min_lon < max_lon <= 180 and -90 <= min_lat < max_lat <= 90):
                raise ValueError("A bounding box da jurisdição é inválida.")
        object.__setattr__(self, "text", normalized_text)
        object.__setattr__(self, "country_code", country)

    @property
    def fingerprint(self) -> str:
        payload = f"{self.country_code}\n{self.text}".encode()
        return hashlib.sha256(payload).hexdigest()


@dataclass(frozen=True)
class NormalizedAddress:
    formatted: str | None = None
    number: str | None = None
    street: str | None = None
    neighborhood: str | None = None
    city: str | None = None
    state: str | None = None
    postcode: str | None = None
    country_code: str | None = None

    def to_dict(self) -> dict:
        return {
            "formatted": self.formatted,
            "number": self.number,
            "street": self.street,
            "neighborhood": self.neighborhood,
            "city": self.city,
            "state": self.state,
            "postcode": self.postcode,
            "countryCode": self.country_code,
        }


@dataclass(frozen=True)
class CanonicalGeocodeResult:
    provider: str
    provider_version: str
    query_fingerprint: str
    status: GeocodeStatus
    latitude: float | None
    longitude: float | None
    confidence: float
    granularity: GeocodeGranularity
    address: NormalizedAddress
    provider_result_id: str | None
    candidate_count: int
    attribution: tuple[str, ...]
    retention_policy: str
    metadata: dict

    def __post_init__(self) -> None:
        if not 0 <= self.confidence <= 1:
            raise ValueError("A confiança normalizada deve estar entre zero e um.")
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError("Latitude e longitude devem ser informadas em conjunto.")
        if self.latitude is not None and not -90 <= self.latitude <= 90:
            raise ValueError("Latitude inválida.")
        if self.longitude is not None and not -180 <= self.longitude <= 180:
            raise ValueError("Longitude inválida.")
        if self.candidate_count < 0:
            raise ValueError("A quantidade de candidatos não pode ser negativa.")

    def to_dict(self) -> dict:
        return {
            "provider": self.provider,
            "providerVersion": self.provider_version,
            "queryFingerprint": self.query_fingerprint,
            "status": self.status.value,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "confidence": round(self.confidence, 4),
            "granularity": self.granularity.value,
            "address": self.address.to_dict(),
            "providerResultId": self.provider_result_id,
            "candidateCount": self.candidate_count,
            "attribution": list(self.attribution),
            "retentionPolicy": self.retention_policy,
            "metadata": self.metadata,
        }


def status_for_result(
    query: GeocodeQuery,
    *,
    latitude: float,
    longitude: float,
    confidence: float,
    granularity: GeocodeGranularity,
    number: str | None,
    ambiguous: bool = False,
) -> GeocodeStatus:
    if query.jurisdiction_bbox is not None:
        min_lon, min_lat, max_lon, max_lat = query.jurisdiction_bbox
        if not (min_lon <= longitude <= max_lon and min_lat <= latitude <= max_lat):
            return GeocodeStatus.OUTSIDE_JURISDICTION
    if ambiguous or confidence < 0.5:
        return GeocodeStatus.AMBIGUOUS
    if confidence >= 0.9 and granularity == GeocodeGranularity.ADDRESS and number:
        return GeocodeStatus.VERIFIED
    return GeocodeStatus.APPROXIMATE


def unresolved_result(
    *,
    provider: str,
    provider_version: str,
    query: GeocodeQuery,
    attribution: tuple[str, ...],
    retention_policy: str,
) -> CanonicalGeocodeResult:
    return CanonicalGeocodeResult(
        provider=provider,
        provider_version=provider_version,
        query_fingerprint=query.fingerprint,
        status=GeocodeStatus.UNRESOLVED,
        latitude=None,
        longitude=None,
        confidence=0,
        granularity=GeocodeGranularity.UNKNOWN,
        address=NormalizedAddress(),
        provider_result_id=None,
        candidate_count=0,
        attribution=attribution,
        retention_policy=retention_policy,
        metadata={},
    )
