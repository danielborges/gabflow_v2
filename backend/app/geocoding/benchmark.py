from __future__ import annotations

import csv
import hashlib
import json
import math
import statistics
import time
import unicodedata
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path

from app.geocoding.contract import CanonicalGeocodeResult, GeocodeQuery, GeocodeStatus
from app.geocoding.providers import GeocodingProvider, GeocodingProviderError
from app.territory_geometry import geometry_contains, normalize_geometry

BENCHMARK_VERSION = "geocoding-benchmark-v1"
MINIMUM_SAMPLE_SIZE = 500
MAXIMUM_SAMPLE_SIZE = 1000
REQUIRED_COLUMNS = {
    "case_id",
    "segment",
    "incomplete",
    "query",
    "expected_number",
    "expected_street",
    "expected_neighborhood",
    "expected_city",
    "expected_state",
    "expected_postcode",
    "expected_latitude",
    "expected_longitude",
    "expected_inside_jurisdiction",
}


@dataclass(frozen=True)
class BenchmarkCase:
    case_id: str
    segment: str
    incomplete: bool
    query: str
    expected_number: str | None
    expected_street: str | None
    expected_neighborhood: str | None
    expected_city: str
    expected_state: str | None
    expected_postcode: str | None
    expected_latitude: float | None
    expected_longitude: float | None
    expected_inside_jurisdiction: bool


@dataclass(frozen=True)
class LoadedDataset:
    cases: tuple[BenchmarkCase, ...]
    checksum: str


def load_benchmark_dataset(
    path: str | Path,
    *,
    allow_small_sample: bool = False,
) -> LoadedDataset:
    dataset_path = Path(path)
    payload = dataset_path.read_bytes()
    checksum = hashlib.sha256(payload).hexdigest()
    with dataset_path.open("r", encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source)
        columns = set(reader.fieldnames or [])
        missing = sorted(REQUIRED_COLUMNS - columns)
        if missing:
            raise ValueError("Colunas ausentes no dataset: " + ", ".join(missing) + ".")
        cases = tuple(_case_from_row(row, row_number) for row_number, row in enumerate(reader, 2))
    if not cases:
        raise ValueError("O dataset de benchmark está vazio.")
    if len(cases) > MAXIMUM_SAMPLE_SIZE:
        raise ValueError(f"O dataset deve conter no máximo {MAXIMUM_SAMPLE_SIZE} casos.")
    if not allow_small_sample and len(cases) < MINIMUM_SAMPLE_SIZE:
        raise ValueError(f"O dataset deve conter pelo menos {MINIMUM_SAMPLE_SIZE} casos.")
    identifiers = [case.case_id for case in cases]
    if len(identifiers) != len(set(identifiers)):
        raise ValueError("O dataset contém case_id duplicado.")
    return LoadedDataset(
        cases=tuple(sorted(cases, key=lambda item: item.case_id)),
        checksum=checksum,
    )


def run_benchmark(
    dataset: LoadedDataset,
    providers: tuple[GeocodingProvider, ...],
    *,
    jurisdiction_bbox: tuple[float, float, float, float],
    jurisdiction_geometry: dict | None = None,
    country_code: str = "BR",
    delay_ms: int = 250,
    repeat_fraction: float = 0.1,
    cost_per_thousand: dict[str, float] | None = None,
    clock=time.perf_counter,
    sleeper=time.sleep,
) -> dict:
    if not providers:
        raise ValueError("Selecione pelo menos um provedor.")
    if delay_ms < 0:
        raise ValueError("O intervalo entre consultas não pode ser negativo.")
    if not 0 <= repeat_fraction <= 1:
        raise ValueError("A fração de repetição deve estar entre zero e um.")
    provider_reports = []
    detailed_results = []
    repeat_results = []
    for provider in providers:
        observations = []
        primary_results: dict[str, CanonicalGeocodeResult | None] = {}
        for index, case in enumerate(dataset.cases):
            query = GeocodeQuery(
                text=case.query,
                country_code=country_code,
                jurisdiction_bbox=jurisdiction_bbox,
            )
            started = clock()
            error = None
            result = None
            try:
                result = provider.geocode(query)
                result = _apply_jurisdiction_geometry(result, jurisdiction_geometry)
            except (
                GeocodingProviderError,
                IndexError,
                KeyError,
                TypeError,
                ValueError,
            ) as caught:
                error = caught.__class__.__name__
            latency_ms = max(0.0, (clock() - started) * 1000)
            evaluation = evaluate_result(case, result)
            primary_results[case.case_id] = result
            observations.append(
                {
                    **evaluation,
                    "segment": case.segment,
                    "incomplete": case.incomplete,
                    "latencyMs": latency_ms,
                    "error": error,
                }
            )
            detailed_results.append(
                {
                    "caseId": case.case_id,
                    "segment": case.segment,
                    "incomplete": case.incomplete,
                    "provider": provider.name,
                    "queryFingerprint": query.fingerprint,
                    "latencyMs": round(latency_ms, 3),
                    "error": error,
                    "evaluation": evaluation,
                    "result": result.to_dict() if result else None,
                }
            )
            if delay_ms and index + 1 < len(dataset.cases):
                sleeper(delay_ms / 1000)
        stability = []
        repeat_cases = _repeat_cases(dataset.cases, repeat_fraction)
        for index, case in enumerate(repeat_cases):
            query = GeocodeQuery(
                text=case.query,
                country_code=country_code,
                jurisdiction_bbox=jurisdiction_bbox,
            )
            repeated = None
            error = None
            try:
                repeated = provider.geocode(query)
                repeated = _apply_jurisdiction_geometry(repeated, jurisdiction_geometry)
            except (
                GeocodingProviderError,
                IndexError,
                KeyError,
                TypeError,
                ValueError,
            ) as caught:
                error = caught.__class__.__name__
            stable = _stable_result(primary_results[case.case_id], repeated)
            stability.append(stable)
            repeat_results.append(
                {
                    "caseId": case.case_id,
                    "provider": provider.name,
                    "queryFingerprint": query.fingerprint,
                    "stable": stable,
                    "error": error,
                    "result": repeated.to_dict() if repeated else None,
                }
            )
            if delay_ms and index + 1 < len(repeat_cases):
                sleeper(delay_ms / 1000)
        provider_reports.append(
            _provider_report(
                provider,
                observations,
                stability,
                (cost_per_thousand or {}).get(provider.name.lower()),
            )
        )
    return {
        "benchmarkVersion": BENCHMARK_VERSION,
        "generatedAt": datetime.now(UTC).isoformat(),
        "dataset": {
            "sha256": dataset.checksum,
            "caseCount": len(dataset.cases),
            "segments": _segment_counts(dataset.cases),
        },
        "configuration": {
            "countryCode": country_code.upper(),
            "jurisdictionBbox": list(jurisdiction_bbox),
            "jurisdictionGeometrySha256": _geometry_checksum(jurisdiction_geometry),
            "delayMs": delay_ms,
            "repeatFraction": repeat_fraction,
            "providerOrder": [provider.name for provider in providers],
        },
        "providers": provider_reports,
        "results": detailed_results,
        "repeatResults": repeat_results,
    }


def normalize_benchmark_geometry(value: dict) -> dict:
    """Normaliza Polygon, MultiPolygon, Feature ou FeatureCollection para o ensaio."""
    if not isinstance(value, dict):
        raise ValueError("A jurisdição deve ser um objeto GeoJSON.")
    if value.get("type") != "FeatureCollection":
        return normalize_geometry(value)
    features = value.get("features")
    if not isinstance(features, list) or not features:
        raise ValueError("A FeatureCollection da jurisdição está vazia.")
    polygons = []
    for feature in features:
        geometry = normalize_geometry(feature)
        if geometry["type"] == "Polygon":
            polygons.append(geometry["coordinates"])
        else:
            polygons.extend(geometry["coordinates"])
    return {"type": "MultiPolygon", "coordinates": polygons}


def _apply_jurisdiction_geometry(
    result: CanonicalGeocodeResult | None,
    geometry: dict | None,
) -> CanonicalGeocodeResult | None:
    if (
        result is None
        or geometry is None
        or result.latitude is None
        or result.longitude is None
    ):
        return result
    if geometry_contains(geometry, result.latitude, result.longitude):
        return result
    return replace(result, status=GeocodeStatus.OUTSIDE_JURISDICTION)


def _geometry_checksum(geometry: dict | None) -> str | None:
    if geometry is None:
        return None
    payload = json.dumps(
        geometry,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(payload).hexdigest()


def write_benchmark_report(report: dict, path: str | Path) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(output)


def evaluate_result(case: BenchmarkCase, result: CanonicalGeocodeResult | None) -> dict:
    if result is None:
        return {
            "status": None,
            "municipalityMatch": False,
            "streetMatch": False if case.expected_street else None,
            "numberMatch": False if case.expected_number else None,
            "neighborhoodMatch": False if case.expected_neighborhood else None,
            "jurisdictionMatch": False,
            "usable": False,
            "distanceMeters": None,
        }
    coordinates_inside = result.status != GeocodeStatus.OUTSIDE_JURISDICTION
    jurisdiction_match = coordinates_inside == case.expected_inside_jurisdiction
    return {
        "status": result.status.value,
        "municipalityMatch": _matches(case.expected_city, result.address.city),
        "streetMatch": _matches(case.expected_street, result.address.street),
        "numberMatch": _number_matches(case.expected_number, result.address.number),
        "neighborhoodMatch": _matches(case.expected_neighborhood, result.address.neighborhood),
        "jurisdictionMatch": jurisdiction_match,
        "outsidePromotedVerified": bool(
            not case.expected_inside_jurisdiction and result.status == GeocodeStatus.VERIFIED
        ),
        "usable": result.status in {GeocodeStatus.VERIFIED, GeocodeStatus.APPROXIMATE},
        "distanceMeters": _distance(case, result),
    }


def _provider_report(
    provider: GeocodingProvider,
    observations: list[dict],
    stability: list[bool],
    cost_per_thousand: float | None,
) -> dict:
    urban_complete = [
        item
        for item in observations
        if not item["incomplete"] and item["segment"] in {"central", "periferia"}
    ]
    complete = [item for item in observations if not item["incomplete"]]
    rates = {
        "municipality": _rate(observations, "municipalityMatch"),
        "street": _rate(observations, "streetMatch"),
        "streetUrbanComplete": _rate(urban_complete, "streetMatch"),
        "number": _rate(observations, "numberMatch"),
        "numberUrbanComplete": _rate(urban_complete, "numberMatch"),
        "neighborhood": _rate(observations, "neighborhoodMatch"),
        "jurisdiction": _rate(observations, "jurisdictionMatch"),
        "usable": _rate(observations, "usable"),
        "usableComplete": _rate(complete, "usable"),
    }
    latencies = sorted(item["latencyMs"] for item in observations)
    distances = sorted(
        item["distanceMeters"]
        for item in observations
        if item.get("distanceMeters") is not None
    )
    statuses = {
        status.value: sum(item.get("status") == status.value for item in observations)
        for status in GeocodeStatus
    }
    outside_promoted = sum(bool(item.get("outsidePromotedVerified")) for item in observations)
    errors = sum(item.get("error") is not None for item in observations)
    stability_rate = sum(stability) / len(stability) if stability else 0
    gates = {
        "municipality": rates["municipality"] >= 0.95,
        "jurisdiction": rates["jurisdiction"] >= 0.99 and outside_promoted == 0,
        "streetOverall": rates["street"] >= 0.85,
        "streetUrbanComplete": rates["streetUrbanComplete"] >= 0.90,
        "numberUrbanComplete": rates["numberUrbanComplete"] >= 0.75,
        "neighborhood": rates["neighborhood"] >= 0.85,
        "usableComplete": rates["usableComplete"] >= 0.85,
        "stability": stability_rate >= 0.98,
    }
    return {
        "provider": provider.name,
        "providerVersion": provider.version,
        "sampleCount": len(observations),
        "errorCount": errors,
        "outsidePromotedVerified": outside_promoted,
        "rates": {key: round(value, 4) for key, value in rates.items()},
        "statuses": statuses,
        "distanceMeters": {
            "sampleCount": len(distances),
            "median": round(statistics.median(distances), 2) if distances else None,
            "p90": round(_percentile(distances, 0.9), 2) if distances else None,
            "p95": round(_percentile(distances, 0.95), 2) if distances else None,
        },
        "cost": {
            "perThousand": cost_per_thousand,
            "estimatedRun": (
                round((len(observations) + len(stability)) * cost_per_thousand / 1000, 4)
                if cost_per_thousand is not None
                else None
            ),
        },
        "stability": {
            "sampleCount": len(stability),
            "rate": round(stability_rate, 4),
        },
        "segments": {
            segment: {
                "sampleCount": len(segment_items),
                "municipality": round(_rate(segment_items, "municipalityMatch"), 4),
                "street": round(_rate(segment_items, "streetMatch"), 4),
                "number": round(_rate(segment_items, "numberMatch"), 4),
                "neighborhood": round(_rate(segment_items, "neighborhoodMatch"), 4),
                "jurisdiction": round(_rate(segment_items, "jurisdictionMatch"), 4),
                "usable": round(_rate(segment_items, "usable"), 4),
            }
            for segment in ("central", "periferia", "rural", "demais")
            if (segment_items := [item for item in observations if item["segment"] == segment])
        },
        "latencyMs": {
            "median": round(statistics.median(latencies), 3) if latencies else None,
            "p90": round(_percentile(latencies, 0.9), 3) if latencies else None,
            "p95": round(_percentile(latencies, 0.95), 3) if latencies else None,
        },
        "gates": gates,
        "approved": all(gates.values()),
    }


def _case_from_row(row: dict[str, str], row_number: int) -> BenchmarkCase:
    case_id = _required(row, "case_id", row_number)
    segment = _required(row, "segment", row_number).lower()
    if segment not in {"central", "periferia", "rural", "demais"}:
        raise ValueError(f"Linha {row_number}: segmento inválido.")
    return BenchmarkCase(
        case_id=case_id,
        segment=segment,
        incomplete=_boolean(_required(row, "incomplete", row_number), row_number),
        query=_required(row, "query", row_number),
        expected_number=_optional(row.get("expected_number")),
        expected_street=_optional(row.get("expected_street")),
        expected_neighborhood=_optional(row.get("expected_neighborhood")),
        expected_city=_required(row, "expected_city", row_number),
        expected_state=_optional(row.get("expected_state")),
        expected_postcode=_optional(row.get("expected_postcode")),
        expected_latitude=_optional_float(row.get("expected_latitude"), row_number),
        expected_longitude=_optional_float(row.get("expected_longitude"), row_number),
        expected_inside_jurisdiction=_boolean(
            _required(row, "expected_inside_jurisdiction", row_number), row_number
        ),
    )


def _required(row: dict[str, str], key: str, row_number: int) -> str:
    value = _optional(row.get(key))
    if value is None:
        raise ValueError(f"Linha {row_number}: {key} é obrigatório.")
    return value


def _optional(value: str | None) -> str | None:
    normalized = " ".join((value or "").split()).strip()
    return normalized or None


def _optional_float(value: str | None, row_number: int) -> float | None:
    normalized = _optional(value)
    if normalized is None:
        return None
    try:
        return float(normalized.replace(",", "."))
    except ValueError as error:
        raise ValueError(f"Linha {row_number}: coordenada inválida.") from error


def _boolean(value: str, row_number: int) -> bool:
    normalized = value.strip().lower()
    if normalized in {"true", "1", "sim", "yes"}:
        return True
    if normalized in {"false", "0", "não", "nao", "no"}:
        return False
    raise ValueError(f"Linha {row_number}: valor booleano inválido.")


def _normalize(value: str | None) -> str:
    decomposed = unicodedata.normalize("NFKD", value or "")
    ascii_value = "".join(
        character for character in decomposed if not unicodedata.combining(character)
    )
    tokens = "".join(character if character.isalnum() else " " for character in ascii_value.lower())
    replacements = {
        "avenida": "av",
        "rodovia": "rod",
        "estrada": "est",
        "travessa": "trav",
        "praca": "pc",
    }
    return " ".join(replacements.get(token, token) for token in tokens.split())


def _matches(expected: str | None, actual: str | None) -> bool | None:
    if not expected:
        return None
    normalized_actual = _normalize(actual)
    expected_aliases = {_normalize(alias) for alias in expected.split("|")}
    return bool(actual) and normalized_actual in expected_aliases


def _number_matches(expected: str | None, actual: str | None) -> bool | None:
    if not expected:
        return None
    return _normalize(expected).replace(" ", "") == _normalize(actual).replace(" ", "")


def _distance(case: BenchmarkCase, result: CanonicalGeocodeResult) -> float | None:
    if (
        case.expected_latitude is None
        or case.expected_longitude is None
        or result.latitude is None
        or result.longitude is None
    ):
        return None
    radius = 6_371_000
    latitude_1 = math.radians(case.expected_latitude)
    latitude_2 = math.radians(result.latitude)
    delta_latitude = math.radians(result.latitude - case.expected_latitude)
    delta_longitude = math.radians(result.longitude - case.expected_longitude)
    haversine = math.sin(delta_latitude / 2) ** 2 + (
        math.cos(latitude_1) * math.cos(latitude_2) * math.sin(delta_longitude / 2) ** 2
    )
    return round(2 * radius * math.asin(math.sqrt(haversine)), 2)


def _repeat_cases(
    cases: tuple[BenchmarkCase, ...],
    repeat_fraction: float,
) -> tuple[BenchmarkCase, ...]:
    if not repeat_fraction:
        return ()
    count = max(1, math.ceil(len(cases) * repeat_fraction))
    ordered = sorted(cases, key=lambda item: hashlib.sha256(item.case_id.encode()).hexdigest())
    return tuple(ordered[:count])


def _stable_result(
    original: CanonicalGeocodeResult | None,
    repeated: CanonicalGeocodeResult | None,
) -> bool:
    if original is None or repeated is None:
        return original is repeated
    if original.status != repeated.status or original.granularity != repeated.granularity:
        return False
    if original.latitude is None or repeated.latitude is None:
        return original.latitude is repeated.latitude and original.longitude is repeated.longitude
    synthetic_case = BenchmarkCase(
        case_id="stability",
        segment="demais",
        incomplete=False,
        query="stability",
        expected_number=None,
        expected_street=None,
        expected_neighborhood=None,
        expected_city="stability",
        expected_state=None,
        expected_postcode=None,
        expected_latitude=original.latitude,
        expected_longitude=original.longitude,
        expected_inside_jurisdiction=True,
    )
    distance = _distance(synthetic_case, repeated)
    return distance is not None and distance <= 50


def _rate(observations: list[dict], key: str) -> float:
    eligible = [item[key] for item in observations if item.get(key) is not None]
    return sum(bool(value) for value in eligible) / len(eligible) if eligible else 0


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        raise ValueError("Não é possível calcular percentil sem valores.")
    rank = (len(values) - 1) * percentile
    lower = math.floor(rank)
    upper = math.ceil(rank)
    if lower == upper:
        return values[lower]
    weight = rank - lower
    return values[lower] * (1 - weight) + values[upper] * weight


def _segment_counts(cases: tuple[BenchmarkCase, ...]) -> dict[str, int]:
    return {
        segment: sum(case.segment == segment for case in cases)
        for segment in ("central", "periferia", "rural", "demais")
    }
