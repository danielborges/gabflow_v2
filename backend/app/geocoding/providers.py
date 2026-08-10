from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Protocol

from app.geocoding.contract import (
    CanonicalGeocodeResult,
    GeocodeGranularity,
    GeocodeQuery,
    NormalizedAddress,
    status_for_result,
    unresolved_result,
)

MAX_RESPONSE_BYTES = 2 * 1024 * 1024


class GeocodingProvider(Protocol):
    name: str
    version: str

    def geocode(self, query: GeocodeQuery) -> CanonicalGeocodeResult: ...


class GeocodingProviderError(RuntimeError):
    pass


class JsonTransport(Protocol):
    def get(self, url: str, *, timeout_seconds: float) -> dict: ...


class UrllibJsonTransport:
    def __init__(self, *, attempts: int = 3) -> None:
        self.attempts = max(1, attempts)

    def get(self, url: str, *, timeout_seconds: float) -> dict:
        request = urllib.request.Request(  # noqa: S310 - URL validated by adapter
            url,
            headers={"Accept": "application/json", "User-Agent": "GabFlow-Geocoder/1.0"},
        )
        last_error: Exception | None = None
        for attempt in range(self.attempts):
            try:
                with urllib.request.urlopen(  # noqa: S310 - provider URL validated by adapter
                    request,
                    timeout=timeout_seconds,
                ) as response:
                    payload = response.read(MAX_RESPONSE_BYTES + 1)
                    if len(payload) > MAX_RESPONSE_BYTES:
                        raise GeocodingProviderError("Resposta do provedor excedeu o limite.")
                    parsed = json.loads(payload.decode("utf-8"))
                    if not isinstance(parsed, dict):
                        raise GeocodingProviderError("Provedor retornou JSON incompatível.")
                    return parsed
            except urllib.error.HTTPError as error:
                last_error = error
                if error.code != 429 and error.code < 500:
                    break
                retry_after = error.headers.get("Retry-After") if error.headers else None
                delay = min(5.0, float(retry_after or 2**attempt))
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
                last_error = error
                delay = min(5.0, float(2**attempt))
            if attempt + 1 < self.attempts:
                time.sleep(delay)
        raise GeocodingProviderError(
            "Provedor indisponível ou retornou resposta inválida."
        ) from last_error


class _BaseAdapter:
    name = "BASE"
    version = "v1"
    attribution: tuple[str, ...] = ()
    retention_policy = "VERIFY_CONTRACT"

    def __init__(
        self,
        api_key: str,
        *,
        endpoint: str,
        timeout_seconds: float = 12,
        transport: JsonTransport | None = None,
    ) -> None:
        if not api_key.strip():
            raise ValueError(f"Credencial ausente para {self.name}.")
        parsed = urllib.parse.urlsplit(endpoint)
        if parsed.scheme != "https" or not parsed.hostname:
            raise ValueError("O endpoint do geocodificador deve usar HTTPS.")
        self.api_key = api_key
        self.endpoint = endpoint.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.transport = transport or UrllibJsonTransport()

    def _get(self, parameters: dict[str, str | int | float]) -> dict:
        query = urllib.parse.urlencode(parameters)
        return self.transport.get(f"{self.endpoint}?{query}", timeout_seconds=self.timeout_seconds)

    def _unresolved(self, query: GeocodeQuery) -> CanonicalGeocodeResult:
        return unresolved_result(
            provider=self.name,
            provider_version=self.version,
            query=query,
            attribution=self.attribution,
            retention_policy=self.retention_policy,
        )


class GeoapifyAdapter(_BaseAdapter):
    name = "GEOAPIFY"
    version = "geocoding-v1"
    attribution = ("Geoapify", "OpenStreetMap contributors")
    retention_policy = "PERSIST_WITH_SOURCE_ATTRIBUTION"

    def __init__(self, api_key: str, **kwargs) -> None:
        super().__init__(
            api_key,
            endpoint=kwargs.pop("endpoint", "https://api.geoapify.com/v1/geocode/search"),
            **kwargs,
        )

    def geocode(self, query: GeocodeQuery) -> CanonicalGeocodeResult:
        parameters: dict[str, str | int | float] = {
            "text": query.text,
            "filter": f"countrycode:{query.country_code.lower()}",
            "limit": 2,
            "format": "geojson",
            "apiKey": self.api_key,
        }
        if query.jurisdiction_bbox:
            min_lon, min_lat, max_lon, max_lat = query.jurisdiction_bbox
            parameters["bias"] = f"rect:{min_lon},{min_lat},{max_lon},{max_lat}"
        payload = self._get(parameters)
        features = payload.get("features")
        if not isinstance(features, list) or not features:
            return self._unresolved(query)
        feature = features[0] if isinstance(features[0], dict) else {}
        properties = (
            feature.get("properties") if isinstance(feature.get("properties"), dict) else {}
        )
        rank = properties.get("rank") if isinstance(properties.get("rank"), dict) else {}
        confidence = _confidence(rank.get("confidence", properties.get("confidence")), 0.5)
        latitude = _required_coordinate(properties.get("lat"), "latitude")
        longitude = _required_coordinate(properties.get("lon"), "longitude")
        result_type = str(properties.get("result_type") or "unknown")
        granularity = _granularity(result_type)
        address = NormalizedAddress(
            formatted=_text(properties.get("formatted")),
            number=_text(properties.get("housenumber")),
            street=_text(properties.get("street")),
            neighborhood=_text(properties.get("suburb") or properties.get("district")),
            city=_text(properties.get("city") or properties.get("municipality")),
            state=_text(properties.get("state_code") or properties.get("state")),
            postcode=_text(properties.get("postcode")),
            country_code=_text(properties.get("country_code")),
        )
        return _canonical(
            adapter=self,
            query=query,
            latitude=latitude,
            longitude=longitude,
            confidence=confidence,
            granularity=granularity,
            address=address,
            provider_result_id=_text(properties.get("place_id")),
            candidate_count=len(features),
            metadata={"matchType": result_type},
        )


class GoogleMapsAdapter(_BaseAdapter):
    name = "GOOGLE"
    version = "geocoding-v3"
    attribution = ("Google Maps",)
    retention_policy = "TEMPORARY_30_DAYS_UNLESS_CONTRACT_EXCEPTION"

    def __init__(self, api_key: str, **kwargs) -> None:
        super().__init__(
            api_key,
            endpoint=kwargs.pop("endpoint", "https://maps.googleapis.com/maps/api/geocode/json"),
            **kwargs,
        )

    def geocode(self, query: GeocodeQuery) -> CanonicalGeocodeResult:
        payload = self._get(
            {
                "address": query.text,
                "components": f"country:{query.country_code}",
                "language": "pt-BR",
                "key": self.api_key,
            }
        )
        results = payload.get("results")
        if payload.get("status") == "ZERO_RESULTS" or not isinstance(results, list) or not results:
            return self._unresolved(query)
        result = results[0] if isinstance(results[0], dict) else {}
        geometry = result.get("geometry") if isinstance(result.get("geometry"), dict) else {}
        location = geometry.get("location") if isinstance(geometry.get("location"), dict) else {}
        location_type = str(geometry.get("location_type") or "APPROXIMATE").upper()
        confidence = {
            "ROOFTOP": 0.98,
            "RANGE_INTERPOLATED": 0.82,
            "GEOMETRIC_CENTER": 0.62,
            "APPROXIMATE": 0.48,
        }.get(location_type, 0.45)
        components = _google_components(result.get("address_components"))
        number = components.get("street_number")
        return _canonical(
            adapter=self,
            query=query,
            latitude=_required_coordinate(location.get("lat"), "latitude"),
            longitude=_required_coordinate(location.get("lng"), "longitude"),
            confidence=confidence,
            granularity=GeocodeGranularity.ADDRESS if number else _google_granularity(result),
            address=NormalizedAddress(
                formatted=_text(result.get("formatted_address")),
                number=number,
                street=components.get("route"),
                neighborhood=components.get("sublocality") or components.get("neighborhood"),
                city=components.get("administrative_area_level_2") or components.get("locality"),
                state=components.get("administrative_area_level_1_short"),
                postcode=components.get("postal_code"),
                country_code=components.get("country_short"),
            ),
            provider_result_id=_text(result.get("place_id")),
            candidate_count=len(results),
            metadata={
                "locationType": location_type,
                "partialMatch": bool(result.get("partial_match")),
            },
            ambiguous=bool(result.get("partial_match")) and confidence < 0.9,
        )


class MapboxAdapter(_BaseAdapter):
    name = "MAPBOX"
    version = "geocoding-v6"
    attribution = ("Mapbox", "OpenStreetMap contributors")
    retention_policy = "PERMANENT_GEOCODING_ONLY"

    def __init__(self, api_key: str, **kwargs) -> None:
        super().__init__(
            api_key,
            endpoint=kwargs.pop("endpoint", "https://api.mapbox.com/search/geocode/v6/forward"),
            **kwargs,
        )

    def geocode(self, query: GeocodeQuery) -> CanonicalGeocodeResult:
        parameters: dict[str, str | int | float] = {
            "q": query.text,
            "country": query.country_code.lower(),
            "language": "pt",
            "autocomplete": "false",
            "permanent": "true",
            "limit": 2,
            "access_token": self.api_key,
        }
        if query.jurisdiction_bbox:
            parameters["bbox"] = ",".join(str(value) for value in query.jurisdiction_bbox)
        payload = self._get(parameters)
        features = payload.get("features")
        if not isinstance(features, list) or not features:
            return self._unresolved(query)
        feature = features[0] if isinstance(features[0], dict) else {}
        properties = (
            feature.get("properties") if isinstance(feature.get("properties"), dict) else {}
        )
        coordinates = feature.get("geometry", {}).get("coordinates", [])
        if not isinstance(coordinates, list) or len(coordinates) < 2:
            raise GeocodingProviderError("Mapbox não retornou coordenadas válidas.")
        coordinate_meta = (
            properties.get("coordinates") if isinstance(properties.get("coordinates"), dict) else {}
        )
        accuracy = str(coordinate_meta.get("accuracy") or "").lower()
        match_code = (
            properties.get("match_code")
            if isinstance(properties.get("match_code"), dict)
            else {}
        )
        confidence_label = str(match_code.get("confidence") or "").lower()
        confidence = {"exact": 0.98, "high": 0.9, "medium": 0.7, "low": 0.45}.get(
            confidence_label,
            0.88 if accuracy in {"rooftop", "parcel", "point"} else 0.62,
        )
        context = properties.get("context") if isinstance(properties.get("context"), dict) else {}
        place_types = feature.get("place_type")
        fallback_type = (
            place_types[0] if isinstance(place_types, list) and place_types else "unknown"
        )
        result_type = str(properties.get("feature_type") or fallback_type)
        number = _text(properties.get("address_number"))
        return _canonical(
            adapter=self,
            query=query,
            latitude=_required_coordinate(coordinates[1], "latitude"),
            longitude=_required_coordinate(coordinates[0], "longitude"),
            confidence=confidence,
            granularity=GeocodeGranularity.ADDRESS if number else _granularity(result_type),
            address=NormalizedAddress(
                formatted=_text(properties.get("full_address") or properties.get("name")),
                number=number,
                street=_context_text(context, "street", properties.get("name")),
                neighborhood=_context_text(context, "neighborhood"),
                city=_context_text(context, "place"),
                state=_context_text(context, "region", short=True),
                postcode=_context_text(context, "postcode"),
                country_code=_context_text(context, "country", short=True),
            ),
            provider_result_id=_text(properties.get("mapbox_id") or feature.get("id")),
            candidate_count=len(features),
            metadata={"accuracy": accuracy or None, "matchConfidence": confidence_label or None},
            ambiguous=confidence_label == "low",
        )


class GeocodeEarthAdapter(_BaseAdapter):
    name = "GEOCODE_EARTH"
    version = "pelias-v1"
    attribution = ("Geocode Earth", "OpenStreetMap contributors")
    retention_policy = "PERSIST_INDEFINITELY_WITH_ATTRIBUTION"

    def __init__(self, api_key: str, **kwargs) -> None:
        super().__init__(
            api_key,
            endpoint=kwargs.pop("endpoint", "https://api.geocode.earth/v1/search"),
            **kwargs,
        )

    def geocode(self, query: GeocodeQuery) -> CanonicalGeocodeResult:
        parameters: dict[str, str | int | float] = {
            "text": query.text,
            "boundary.country": query.country_code,
            "lang": "pt-BR",
            "size": 2,
            "api_key": self.api_key,
        }
        if query.jurisdiction_bbox:
            min_lon, min_lat, max_lon, max_lat = query.jurisdiction_bbox
            parameters.update(
                {
                    "boundary.rect.min_lon": min_lon,
                    "boundary.rect.min_lat": min_lat,
                    "boundary.rect.max_lon": max_lon,
                    "boundary.rect.max_lat": max_lat,
                }
            )
        payload = self._get(parameters)
        features = payload.get("features")
        if not isinstance(features, list) or not features:
            return self._unresolved(query)
        feature = features[0] if isinstance(features[0], dict) else {}
        properties = (
            feature.get("properties") if isinstance(feature.get("properties"), dict) else {}
        )
        coordinates = feature.get("geometry", {}).get("coordinates", [])
        if not isinstance(coordinates, list) or len(coordinates) < 2:
            raise GeocodingProviderError("Geocode Earth não retornou coordenadas válidas.")
        layer = str(properties.get("layer") or "unknown")
        number = _text(properties.get("housenumber"))
        return _canonical(
            adapter=self,
            query=query,
            latitude=_required_coordinate(coordinates[1], "latitude"),
            longitude=_required_coordinate(coordinates[0], "longitude"),
            confidence=_confidence(properties.get("confidence"), 0.5),
            granularity=GeocodeGranularity.ADDRESS if number else _granularity(layer),
            address=NormalizedAddress(
                formatted=_text(properties.get("label")),
                number=number,
                street=_text(properties.get("street")),
                neighborhood=_text(properties.get("neighbourhood") or properties.get("borough")),
                city=_text(properties.get("locality") or properties.get("localadmin")),
                state=_text(properties.get("region_a") or properties.get("region")),
                postcode=_text(properties.get("postalcode")),
                country_code=_text(properties.get("country_a")),
            ),
            provider_result_id=_text(properties.get("gid") or properties.get("id")),
            candidate_count=len(features),
            metadata={"layer": layer, "source": _text(properties.get("source"))},
        )


PROVIDER_NAMES = ("geoapify", "google", "mapbox", "geocode-earth")
DEFAULT_PROVIDER_NAMES = ("geoapify", "google", "geocode-earth")


def provider_from_environment(
    name: str,
    *,
    timeout_seconds: float = 12,
    transport: JsonTransport | None = None,
) -> GeocodingProvider:
    normalized = name.strip().lower()
    definitions = {
        "geoapify": (GeoapifyAdapter, "GEOAPIFY_API_KEY"),
        "google": (GoogleMapsAdapter, "GOOGLE_MAPS_API_KEY"),
        "mapbox": (MapboxAdapter, "MAPBOX_ACCESS_TOKEN"),
        "geocode-earth": (GeocodeEarthAdapter, "GEOCODE_EARTH_API_KEY"),
    }
    if normalized not in definitions:
        raise ValueError(f"Provedor desconhecido: {name}.")
    adapter_class, variable = definitions[normalized]
    api_key = os.getenv(variable, "").strip()
    if not api_key:
        raise ValueError(f"Defina {variable} para executar o provedor {normalized}.")
    return adapter_class(api_key, timeout_seconds=timeout_seconds, transport=transport)


def _canonical(
    *,
    adapter: _BaseAdapter,
    query: GeocodeQuery,
    latitude: float,
    longitude: float,
    confidence: float,
    granularity: GeocodeGranularity,
    address: NormalizedAddress,
    provider_result_id: str | None,
    candidate_count: int,
    metadata: dict,
    ambiguous: bool = False,
) -> CanonicalGeocodeResult:
    confidence = max(0.0, min(1.0, confidence))
    return CanonicalGeocodeResult(
        provider=adapter.name,
        provider_version=adapter.version,
        query_fingerprint=query.fingerprint,
        status=status_for_result(
            query,
            latitude=latitude,
            longitude=longitude,
            confidence=confidence,
            granularity=granularity,
            number=address.number,
            ambiguous=ambiguous,
        ),
        latitude=latitude,
        longitude=longitude,
        confidence=confidence,
        granularity=granularity,
        address=address,
        provider_result_id=provider_result_id,
        candidate_count=candidate_count,
        attribution=adapter.attribution,
        retention_policy=adapter.retention_policy,
        metadata={key: value for key, value in metadata.items() if value is not None},
    )


def _required_coordinate(value, label: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError) as error:
        raise GeocodingProviderError(f"Provedor retornou {label} inválida.") from error


def _confidence(value, default: float) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return default


def _text(value) -> str | None:
    if value is None:
        return None
    normalized = " ".join(str(value).split()).strip()
    return normalized or None


def _granularity(value: str) -> GeocodeGranularity:
    normalized = value.lower()
    if normalized in {"address", "building", "street_address", "premise", "venue"}:
        return GeocodeGranularity.ADDRESS
    if normalized in {"route", "street"}:
        return GeocodeGranularity.STREET
    if normalized in {"neighborhood", "neighbourhood", "borough", "suburb"}:
        return GeocodeGranularity.NEIGHBORHOOD
    if normalized in {"postcode", "postalcode"}:
        return GeocodeGranularity.POSTCODE
    if normalized in {"city", "place", "locality", "localadmin", "municipality"}:
        return GeocodeGranularity.LOCALITY
    if normalized in {"region", "state", "county"}:
        return GeocodeGranularity.REGION
    return GeocodeGranularity.UNKNOWN


def _google_components(value) -> dict[str, str]:
    result: dict[str, str] = {}
    if not isinstance(value, list):
        return result
    for component in value:
        if not isinstance(component, dict) or not isinstance(component.get("types"), list):
            continue
        long_name = _text(component.get("long_name"))
        short_name = _text(component.get("short_name"))
        for component_type in component["types"]:
            if long_name:
                result[str(component_type)] = long_name
            if short_name:
                result[f"{component_type}_short"] = short_name
    return result


def _google_granularity(result: dict) -> GeocodeGranularity:
    types = result.get("types") if isinstance(result.get("types"), list) else []
    for item in types:
        granularity = _granularity(str(item))
        if granularity != GeocodeGranularity.UNKNOWN:
            return granularity
    return GeocodeGranularity.UNKNOWN


def _context_text(context: dict, key: str, fallback=None, *, short: bool = False) -> str | None:
    value = context.get(key)
    if not isinstance(value, dict):
        return _text(fallback)
    if short:
        return _text(value.get("region_code") or value.get("country_code") or value.get("name"))
    return _text(value.get("name") or value.get("text"))
