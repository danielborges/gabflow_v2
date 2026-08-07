import csv
import json
from dataclasses import replace
from io import StringIO

import pytest

from app.geocoding.benchmark import (
    BenchmarkCase,
    evaluate_result,
    load_benchmark_dataset,
    run_benchmark,
    write_benchmark_report,
)
from app.geocoding.contract import (
    CanonicalGeocodeResult,
    GeocodeGranularity,
    GeocodeQuery,
    GeocodeStatus,
    NormalizedAddress,
)
from app.geocoding.providers import (
    GeoapifyAdapter,
    GeocodeEarthAdapter,
    GoogleMapsAdapter,
    MapboxAdapter,
)


class FakeTransport:
    def __init__(self, payload):
        self.payload = payload
        self.urls = []

    def get(self, url, *, timeout_seconds):
        self.urls.append((url, timeout_seconds))
        return self.payload


def test_geoapify_adapter_maps_response_and_enforces_jurisdiction():
    transport = FakeTransport(
        {
            "features": [
                {
                    "properties": {
                        "lat": -21.76,
                        "lon": -43.35,
                        "formatted": "Rua Halfeld, 10, Juiz de Fora",
                        "housenumber": "10",
                        "street": "Rua Halfeld",
                        "suburb": "Centro",
                        "city": "Juiz de Fora",
                        "state_code": "MG",
                        "postcode": "36010-000",
                        "country_code": "br",
                        "result_type": "building",
                        "place_id": "geo-1",
                        "rank": {"confidence": 0.97},
                    }
                }
            ]
        }
    )
    adapter = GeoapifyAdapter("secret", transport=transport)
    result = adapter.geocode(
        GeocodeQuery(
            "Rua Halfeld 10, Juiz de Fora, MG",
            jurisdiction_bbox=(-43.6, -22.0, -43.1, -21.5),
        )
    )

    assert result.status == GeocodeStatus.VERIFIED
    assert result.address.city == "Juiz de Fora"
    assert result.retention_policy == "PERSIST_WITH_SOURCE_ATTRIBUTION"
    assert "apiKey=secret" in transport.urls[0][0]

    outside = replace(
        result,
        status=GeocodeStatus.OUTSIDE_JURISDICTION,
        latitude=-20,
        longitude=-40,
    )
    assert outside.to_dict()["status"] == "OUTSIDE_JURISDICTION"


def test_google_adapter_uses_conservative_status_for_partial_match():
    transport = FakeTransport(
        {
            "status": "OK",
            "results": [
                {
                    "place_id": "google-1",
                    "formatted_address": "Rua São João, Juiz de Fora - MG",
                    "partial_match": True,
                    "types": ["route"],
                    "geometry": {
                        "location": {"lat": -21.75, "lng": -43.34},
                        "location_type": "GEOMETRIC_CENTER",
                    },
                    "address_components": [
                        {
                            "long_name": "Rua São João",
                            "short_name": "R. São João",
                            "types": ["route"],
                        },
                        {
                            "long_name": "Juiz de Fora",
                            "short_name": "Juiz de Fora",
                            "types": ["administrative_area_level_2"],
                        },
                    ],
                }
            ],
        }
    )
    result = GoogleMapsAdapter("secret", transport=transport).geocode(
        GeocodeQuery("Rua São João, Juiz de Fora")
    )

    assert result.status == GeocodeStatus.AMBIGUOUS
    assert result.granularity == GeocodeGranularity.STREET
    assert result.metadata["partialMatch"] is True


def test_mapbox_and_geocode_earth_adapters_normalize_provider_specific_payloads():
    mapbox_transport = FakeTransport(
        {
            "features": [
                {
                    "id": "address.1",
                    "geometry": {"coordinates": [-43.35, -21.76]},
                    "properties": {
                        "mapbox_id": "mbx-1",
                        "feature_type": "address",
                        "full_address": "Rua Halfeld, 10, Juiz de Fora",
                        "address_number": "10",
                        "name": "Rua Halfeld",
                        "coordinates": {"accuracy": "rooftop"},
                        "match_code": {"confidence": "exact"},
                        "context": {
                            "place": {"name": "Juiz de Fora"},
                            "region": {"region_code": "MG"},
                            "country": {"country_code": "BR"},
                        },
                    },
                }
            ]
        }
    )
    mapbox = MapboxAdapter("secret", transport=mapbox_transport).geocode(
        GeocodeQuery("Rua Halfeld 10")
    )
    assert mapbox.status == GeocodeStatus.VERIFIED
    assert "permanent=true" in mapbox_transport.urls[0][0]

    earth_transport = FakeTransport(
        {
            "features": [
                {
                    "geometry": {"coordinates": [-43.35, -21.76]},
                    "properties": {
                        "gid": "oa:address:1",
                        "confidence": 0.94,
                        "layer": "address",
                        "label": "Rua Halfeld, 10, Juiz de Fora",
                        "housenumber": "10",
                        "street": "Rua Halfeld",
                        "neighbourhood": "Centro",
                        "locality": "Juiz de Fora",
                        "region_a": "MG",
                        "postalcode": "36010-000",
                        "country_a": "BR",
                    },
                }
            ]
        }
    )
    earth = GeocodeEarthAdapter("secret", transport=earth_transport).geocode(
        GeocodeQuery("Rua Halfeld 10")
    )
    assert earth.status == GeocodeStatus.VERIFIED
    assert earth.address.neighborhood == "Centro"


def test_dataset_loader_validates_schema_size_and_stable_checksum(tmp_path):
    path = tmp_path / "benchmark.csv"
    path.write_text(_csv_payload(), encoding="utf-8")

    loaded = load_benchmark_dataset(path, allow_small_sample=True)

    assert [case.case_id for case in loaded.cases] == ["case-1", "case-2"]
    assert len(loaded.checksum) == 64
    assert loaded.checksum == load_benchmark_dataset(path, allow_small_sample=True).checksum
    with pytest.raises(ValueError, match="pelo menos 500"):
        load_benchmark_dataset(path)


class StubProvider:
    name = "STUB"
    version = "v1"

    def geocode(self, query):
        outside = "Rural" in query.text
        return CanonicalGeocodeResult(
            provider=self.name,
            provider_version=self.version,
            query_fingerprint=query.fingerprint,
            status=(
                GeocodeStatus.OUTSIDE_JURISDICTION if outside else GeocodeStatus.VERIFIED
            ),
            latitude=-20 if outside else -21.76,
            longitude=-40 if outside else -43.35,
            confidence=0.98,
            granularity=GeocodeGranularity.ADDRESS,
            address=NormalizedAddress(
                formatted="Endereço de referência",
                number="10" if not outside else None,
                street="Rua Halfeld" if not outside else "Estrada Rural",
                neighborhood="Centro" if not outside else None,
                city="Juiz de Fora",
                state="MG",
                postcode="36010-000" if not outside else None,
                country_code="BR",
            ),
            provider_result_id="stub-1",
            candidate_count=1,
            attribution=("Stub",),
            retention_policy="TEST_ONLY",
            metadata={},
        )


def test_benchmark_is_ordered_scored_and_does_not_persist_input_text(tmp_path):
    dataset_path = tmp_path / "benchmark.csv"
    dataset_path.write_text(_csv_payload(), encoding="utf-8")
    dataset = load_benchmark_dataset(dataset_path, allow_small_sample=True)

    report = run_benchmark(
        dataset,
        (StubProvider(),),
        jurisdiction_bbox=(-43.6, -22.0, -43.1, -21.5),
        delay_ms=0,
        cost_per_thousand={"stub": 2.5},
        clock=lambda: 1.0,
    )
    output = tmp_path / "report.json"
    write_benchmark_report(report, output)
    serialized = output.read_text(encoding="utf-8")

    assert report["dataset"]["sha256"] == dataset.checksum
    assert report["providers"][0]["approved"] is True
    assert report["providers"][0]["statuses"]["VERIFIED"] == 1
    assert report["providers"][0]["distanceMeters"]["sampleCount"] == 1
    assert report["providers"][0]["cost"]["estimatedRun"] == 0.0075
    assert [item["caseId"] for item in report["results"]] == ["case-1", "case-2"]
    assert "Rua Segredo" not in serialized
    assert json.loads(serialized)["benchmarkVersion"] == "geocoding-benchmark-v1"


def test_evaluation_normalizes_accents_and_reports_distance():
    case = BenchmarkCase(
        case_id="1",
        segment="central",
        incomplete=False,
        query="consulta",
        expected_number="10",
        expected_street="Avenida Getúlio Vargas",
        expected_neighborhood="São Mateus|Sao Matheus",
        expected_city="Juiz de Fora",
        expected_state="MG",
        expected_postcode="36000-000",
        expected_latitude=-21.76,
        expected_longitude=-43.35,
        expected_inside_jurisdiction=True,
    )
    result = StubProvider().geocode(GeocodeQuery("consulta"))
    result = replace(
        result,
        address=replace(
            result.address,
            street="Av Getulio Vargas",
            neighborhood="Sao Mateus",
        ),
    )

    evaluation = evaluate_result(case, result)

    assert evaluation["streetMatch"] is True
    assert evaluation["neighborhoodMatch"] is True
    assert evaluation["distanceMeters"] == 0


def test_cli_executes_small_smoke_dataset(app, tmp_path, monkeypatch):
    dataset = tmp_path / "benchmark.csv"
    output = tmp_path / "report.json"
    dataset.write_text(_csv_payload(), encoding="utf-8")
    monkeypatch.setattr(
        "app.cli.provider_from_environment",
        lambda *_args, **_kwargs: StubProvider(),
    )

    result = app.test_cli_runner().invoke(
        args=[
            "geocoding-benchmark",
            "--dataset",
            str(dataset),
            "--output",
            str(output),
            "--provider",
            "geoapify",
            "--bbox=-43.6,-22.0,-43.1,-21.5",
            "--delay-ms",
            "0",
            "--allow-small-sample",
        ]
    )

    assert result.exit_code == 0, result.output
    assert "Benchmark concluído" in result.output
    assert json.loads(output.read_text(encoding="utf-8"))["providers"][0]["provider"] == "STUB"


def _csv_payload():
    output = StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=[
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
        ],
        lineterminator="\n",
    )
    writer.writeheader()
    writer.writerow(
        {
            "case_id": "case-2",
            "segment": "rural",
            "incomplete": "true",
            "query": "Estrada Rural sem número",
            "expected_street": "Estrada Rural",
            "expected_city": "Juiz de Fora",
            "expected_state": "MG",
            "expected_inside_jurisdiction": "false",
        }
    )
    writer.writerow(
        {
            "case_id": "case-1",
            "segment": "central",
            "incomplete": "false",
            "query": "Rua Segredo 10",
            "expected_number": "10",
            "expected_street": "Rua Halfeld",
            "expected_neighborhood": "Centro",
            "expected_city": "Juiz de Fora",
            "expected_state": "MG",
            "expected_postcode": "36010-000",
            "expected_latitude": "-21.76",
            "expected_longitude": "-43.35",
            "expected_inside_jurisdiction": "true",
        }
    )
    return output.getvalue()
