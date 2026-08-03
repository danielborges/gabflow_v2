import csv
import io
import json
import zipfile

import pytest
from sqlalchemy import func, select

from app.auth.security import hash_password
from app.electoral.geography import IBGE_GEOMETRY_SOURCE, import_geometry_geojson
from app.electoral.ingestion import ElectoralImportError, import_dataset_archive
from app.electoral.service import sync_active_mandate
from app.extensions import db
from app.models import (
    AuditLog,
    ElectoralDatasetStatus,
    ElectoralDatasetVersion,
    ElectoralElection,
    ElectoralFavorite,
    ElectoralGeneratedReport,
    ElectoralModuleSettings,
    ElectoralResult,
    ElectoralSavedComparison,
    OutboxEvent,
    Role,
    Tenant,
    User,
)
from app.modules import DEFAULT_MODULES
from app.outbox.service import process_batch

PASSWORD = "SenhaForte123!"  # noqa: S105
SOURCE_URL = (
    "https://cdn.tse.jus.br/estatistica/sead/odsele/votacao_candidato_munzona/"
    "votacao_candidato_munzona_2022.zip"
)
FIELDS = [
    "ANO_ELEICAO",
    "NR_TURNO",
    "CD_ELEICAO",
    "DS_ELEICAO",
    "DT_ELEICAO",
    "SG_UF",
    "CD_MUNICIPIO",
    "NM_MUNICIPIO",
    "NR_ZONA",
    "CD_CARGO",
    "DS_CARGO",
    "SQ_CANDIDATO",
    "NR_CANDIDATO",
    "NM_CANDIDATO",
    "NM_URNA_CANDIDATO",
    "DS_SITUACAO_CANDIDATURA",
    "NR_PARTIDO",
    "SG_PARTIDO",
    "NM_PARTIDO",
    "QT_VOTOS_NOMINAIS",
]


def _row(
    *,
    votes="123",
    candidate="1001",
    year="2022",
    election_code="546",
    election_name="Eleicoes Gerais 2022",
    election_date="02/10/2022",
    party_number="13",
    party_acronym="PT",
    party_name="PARTIDO DOS TRABALHADORES",
):
    return {
        "ANO_ELEICAO": year,
        "NR_TURNO": "1",
        "CD_ELEICAO": election_code,
        "DS_ELEICAO": election_name,
        "DT_ELEICAO": election_date,
        "SG_UF": "MG",
        "CD_MUNICIPIO": "47333",
        "NM_MUNICIPIO": "JUIZ DE FORA",
        "NR_ZONA": "315",
        "CD_CARGO": "6",
        "DS_CARGO": "DEPUTADO FEDERAL",
        "SQ_CANDIDATO": candidate,
        "NR_CANDIDATO": "1313",
        "NM_CANDIDATO": "CANDIDATA TESTE",
        "NM_URNA_CANDIDATO": "TESTE",
        "DS_SITUACAO_CANDIDATURA": "APTO",
        "NR_PARTIDO": party_number,
        "SG_PARTIDO": party_acronym,
        "NM_PARTIDO": party_name,
        "QT_VOTOS_NOMINAIS": votes,
    }


def _archive(tmp_path, rows, name="tse.zip", *, include_national_partition=False):
    path = tmp_path / name
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=FIELDS, delimiter=";", lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("votacao_mg.csv", buffer.getvalue().encode("latin-1"))
        if include_national_partition:
            archive.writestr("votacao_BRASIL.csv", buffer.getvalue().encode("latin-1"))
    return path


def _prepare_representative(
    app,
    *,
    tenant_slug="gabinete-a",
    email="parlamentar-catalogo@teste.local",
):
    with app.app_context():
        tenant = db.session.execute(select(Tenant).where(Tenant.slug == tenant_slug)).scalar_one()
        tenant.plan = "premium"
        tenant.enabled_modules = [*DEFAULT_MODULES, "inteligencia_eleitoral"]
        tenant.chamber_type = "CAMARA_MUNICIPAL"
        tenant.jurisdiction_name = "Juiz de Fora/MG"
        representative = User(
            tenant_id=tenant.id,
            name="Parlamentar Catalogo",
            email=email,
            password_hash=hash_password(PASSWORD),
            role=Role.REPRESENTATIVE,
        )
        db.session.add(representative)
        db.session.flush()
        sync_active_mandate(tenant)
        db.session.commit()


def _login(client, email="parlamentar-catalogo@teste.local"):
    response = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": PASSWORD},
    )
    assert response.status_code == 200


def test_import_is_validated_published_and_idempotent(app, tmp_path):
    path = _archive(
        tmp_path,
        [_row(), _row(votes="77", candidate="1002")],
        include_national_partition=True,
    )
    with app.app_context():
        dataset, repeated = import_dataset_archive(
            path,
            source_url=SOURCE_URL,
            election_year=2022,
            election_scope="general",
            uf="MG",
            office_code="6",
            expected_total_votes=200,
        )
        assert repeated is False
        assert dataset.status == ElectoralDatasetStatus.PUBLISHED
        assert dataset.row_count == 2
        assert dataset.total_votes == 200
        assert dataset.quality_score == 1
        assert dataset.validation_manifest["totalizationChecked"] is True
        assert db.session.scalar(select(func.count()).select_from(ElectoralResult)) == 2
        assert set(db.session.scalars(select(OutboxEvent.event_type))) >= {
            "electoral.dataset.imported",
            "electoral.dataset.published",
        }
        repeated_dataset, repeated = import_dataset_archive(
            path,
            source_url=SOURCE_URL,
            election_year=2022,
            election_scope="general",
            uf="MG",
            office_code="6",
        )
        assert repeated is True
        assert repeated_dataset.id == dataset.id
        assert db.session.scalar(select(func.count()).select_from(ElectoralDatasetVersion)) == 1


def test_invalid_or_inconsistent_load_is_rejected(app, tmp_path):
    path = _archive(tmp_path, [_row(votes="-1")], "invalid.zip")
    with app.app_context(), pytest.raises(ElectoralImportError):
        import_dataset_archive(
            path,
            source_url=SOURCE_URL,
            election_year=2022,
            election_scope="general",
            uf="MG",
            office_code="6",
        )
    with app.app_context():
        dataset = db.session.execute(select(ElectoralDatasetVersion)).scalar_one()
        assert dataset.status == ElectoralDatasetStatus.REJECTED
        assert dataset.validation_manifest["blockingErrors"]
        assert db.session.scalar(select(func.count()).select_from(ElectoralResult)) == 0


def test_new_version_supersedes_previous_and_catalog_is_consultable(app, client, tmp_path):
    first = _archive(tmp_path, [_row(votes="100")], "first.zip")
    second = _archive(tmp_path, [_row(votes="101")], "second.zip")
    with app.app_context():
        old, _ = import_dataset_archive(
            first,
            source_url=SOURCE_URL,
            election_year=2022,
            election_scope="general",
            uf="MG",
            office_code="6",
        )
        current, _ = import_dataset_archive(
            second,
            source_url=SOURCE_URL,
            election_year=2022,
            election_scope="general",
            uf="MG",
            office_code="6",
        )
        assert (
            db.session.get(ElectoralDatasetVersion, old.id).status
            == ElectoralDatasetStatus.SUPERSEDED
        )
        assert current.status == ElectoralDatasetStatus.PUBLISHED
        assert current.validation_manifest["totalizationChecked"] is False
        assert current.validation_manifest["totalizationConsistent"] is None

    _prepare_representative(app)
    _login(client)
    elections = client.get("/api/v1/electoral/elections?year=2022&uf=mg")
    coverage = client.get("/api/v1/electoral/coverage")
    quality = client.get("/api/v1/electoral/quality")
    datasets = client.get("/api/v1/electoral/datasets")

    assert elections.status_code == 200
    assert elections.json["total"] == 1
    assert elections.json["items"][0]["dataset_version"] == str(current.id)
    assert coverage.json["content"][0]["votos"] == 101
    assert quality.json["qualidadeMedia"] == 1
    assert len(datasets.json["content"]) == 2
    with app.app_context():
        assert (
            db.session.scalar(
                select(func.count())
                .select_from(AuditLog)
                .where(AuditLog.action.like("electoral.catalog.%"))
            )
            == 4
        )


def test_candidate_search_and_territorial_results_are_reproducible(app, client, tmp_path):
    path = _archive(tmp_path, [_row(), _row(votes="77", candidate="1002")])
    with app.app_context():
        import_dataset_archive(
            path,
            source_url=SOURCE_URL,
            election_year=2022,
            election_scope="general",
            uf="MG",
            office_code="6",
            expected_total_votes=200,
        )
        election_id = db.session.scalar(select(ElectoralElection.id))

    _prepare_representative(app)
    _login(client)
    search_response = client.get(
        f"/api/v1/electoral/candidates?election_id={election_id}&q=candidáta"
    )

    assert search_response.status_code == 200
    assert search_response.json["total"] == 2
    assert {item["external_id"] for item in search_response.json["items"]} == {
        "1001",
        "1002",
    }
    candidate = next(
        item for item in search_response.json["items"] if item["external_id"] == "1001"
    )
    assert candidate["number"] == "1313"
    assert candidate["party"]["acronym"] == "PT"

    results_response = client.get(
        f"/api/v1/electoral/candidates/{candidate['id']}/results"
        f"?election_id={election_id}&level=municipality"
    )
    assert results_response.status_code == 200
    result = results_response.json["items"][0]
    assert result["votes"] == 123
    assert result["denominator_value"] == 200
    assert result["share"] == 0.615
    assert result["rank"] == 1
    assert results_response.json["denominator"]["type"] == "valid_nominal_votes"
    assert results_response.json["candidate_total_votes"] == 123

    zone_response = client.get(
        f"/api/v1/electoral/candidates/{candidate['id']}/results"
        f"?election_id={election_id}&level=electoral_zone"
    )
    assert zone_response.status_code == 200
    assert zone_response.json["items"][0]["territory_name"].endswith("Zona 315")

    unsupported = client.get(
        f"/api/v1/electoral/candidates/{candidate['id']}/results"
        f"?election_id={election_id}&level=neighborhood"
    )
    assert unsupported.status_code == 422
    assert unsupported.json["availableLevels"] == ["municipality", "electoral_zone"]
    with app.app_context():
        audit = db.session.execute(
            select(AuditLog).where(AuditLog.action == "electoral.catalog.candidates_searched")
        ).scalar_one()
        assert audit.after["filters"]["queryLength"] == 9
        assert "q" not in audit.after["filters"]


def test_comparison_enforces_limit_and_uses_shared_denominator(app, client, tmp_path):
    path = _archive(tmp_path, [_row(), _row(votes="77", candidate="1002")])
    with app.app_context():
        import_dataset_archive(
            path,
            source_url=SOURCE_URL,
            election_year=2022,
            election_scope="general",
            uf="MG",
            office_code="6",
            expected_total_votes=200,
        )
        election_id = db.session.scalar(select(ElectoralElection.id))

    _prepare_representative(app)
    _login(client)
    candidates = client.get(
        f"/api/v1/electoral/candidates?election_id={election_id}&q=candidata"
    ).json["items"]
    csrf = client.get_cookie("csrf_access_token").value
    response = client.post(
        "/api/v1/electoral/comparisons",
        json={
            "election_id": str(election_id),
            "candidate_ids": [item["id"] for item in candidates],
            "level": "municipality",
        },
        headers={"X-CSRF-TOKEN": csrf},
    )
    assert response.status_code == 200
    assert response.json["comparability"]["compatible"] is True
    assert response.json["items"][0]["denominator_value"] == 200
    assert {item["votes"] for item in response.json["items"][0]["series"]} == {77, 123}

    too_many = client.post(
        "/api/v1/electoral/comparisons",
        json={
            "election_id": str(election_id),
            "candidate_ids": [str(index).zfill(32) for index in range(6)],
        },
        headers={"X-CSRF-TOKEN": csrf},
    )
    assert too_many.status_code == 422
    assert "entre 2 e 5" in too_many.json["message"]


def test_candidate_history_flags_party_and_boundary_review(app, client, tmp_path):
    current = _archive(tmp_path, [_row()], "current.zip")
    previous = _archive(
        tmp_path,
        [
            _row(
                candidate="9001",
                year="2020",
                election_code="426",
                election_name="Eleicoes Municipais 2020",
                election_date="15/11/2020",
                party_number="25",
                party_acronym="DEM",
                party_name="DEMOCRATAS",
            )
        ],
        "previous.zip",
    )
    with app.app_context():
        import_dataset_archive(
            current,
            source_url=SOURCE_URL,
            election_year=2022,
            election_scope="general",
            uf="MG",
            office_code="6",
        )
        import_dataset_archive(
            previous,
            source_url=SOURCE_URL.replace("2022", "2020"),
            election_year=2020,
            election_scope="municipal",
            uf="MG",
            office_code="6",
        )
        current_election = db.session.scalar(
            select(ElectoralElection.id).where(ElectoralElection.year == 2022)
        )

    _prepare_representative(app)
    _login(client)
    candidate = client.get(
        f"/api/v1/electoral/candidates?election_id={current_election}&q=candidata"
    ).json["items"][0]
    response = client.get(f"/api/v1/electoral/candidates/{candidate['id']}/history")
    assert response.status_code == 200
    assert len(response.json["items"]) == 2
    assert response.json["identity"]["reviewed"] is False
    assert {warning["code"] for warning in response.json["warnings"]} == {
        "PARTY_CHANGED",
        "BOUNDARY_REVIEW_REQUIRED",
    }


def test_private_identity_favorites_and_saved_comparisons_are_user_isolated(
    app, client, tmp_path
):
    path = _archive(tmp_path, [_row(), _row(votes="77", candidate="1002")])
    with app.app_context():
        import_dataset_archive(
            path,
            source_url=SOURCE_URL,
            election_year=2022,
            election_scope="general",
            uf="MG",
            office_code="6",
        )
        election_id = db.session.scalar(select(ElectoralElection.id))

    _prepare_representative(app)
    _login(client)
    candidates = client.get(
        f"/api/v1/electoral/candidates?election_id={election_id}&q=candidata"
    ).json["items"]
    csrf = client.get_cookie("csrf_access_token").value
    identity = client.put(
        f"/api/v1/electoral/candidates/{candidates[0]['id']}/identity-review",
        json={
            "linked_candidate_ids": [candidates[1]["id"]],
            "decision": "CONFIRMED",
        },
        headers={"X-CSRF-TOKEN": csrf},
    )
    assert identity.status_code == 200
    history = client.get(f"/api/v1/electoral/candidates/{candidates[0]['id']}/history")
    assert history.json["identity"]["reviewed"] is True
    assert history.json["identity"]["method"] == "human_review"

    favorite = client.post(
        "/api/v1/electoral/favorites",
        json={
            "target_type": "candidate",
            "target_id": candidates[0]["id"],
            "label": candidates[0]["ballot_name"],
            "snapshot": {"number": candidates[0]["number"]},
        },
        headers={"X-CSRF-TOKEN": csrf},
    )
    assert favorite.status_code == 201
    saved = client.post(
        "/api/v1/electoral/saved-comparisons",
        json={
            "name": "Comparativo privado",
            "election_id": str(election_id),
            "candidate_ids": [item["id"] for item in candidates],
            "level": "municipality",
        },
        headers={"X-CSRF-TOKEN": csrf},
    )
    assert saved.status_code == 201
    assert len(client.get("/api/v1/electoral/favorites").json["content"]) == 1
    assert len(client.get("/api/v1/electoral/saved-comparisons").json["content"]) == 1

    second_email = "parlamentar-b-catalogo@teste.local"
    _prepare_representative(app, tenant_slug="gabinete-b", email=second_email)
    second_client = app.test_client()
    _login(second_client, second_email)
    assert second_client.get("/api/v1/electoral/favorites").json["content"] == []
    assert second_client.get("/api/v1/electoral/saved-comparisons").json["content"] == []
    with app.app_context():
        assert db.session.scalar(select(func.count()).select_from(ElectoralFavorite)) == 1
        assert db.session.scalar(select(func.count()).select_from(ElectoralSavedComparison)) == 1


def test_official_geometry_is_versioned_and_map_never_invents_zone_polygons(
    app, client, tmp_path
):
    path = _archive(tmp_path, [_row(), _row(votes="77", candidate="1002")])
    with app.app_context():
        import_dataset_archive(
            path,
            source_url=SOURCE_URL,
            election_year=2022,
            election_scope="general",
            uf="MG",
            office_code="6",
        )
        election_id = db.session.scalar(select(ElectoralElection.id))
        geometry = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "properties": {"codarea": "3136702"},
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [
                            [
                                [-43.5, -21.9],
                                [-43.1, -21.9],
                                [-43.1, -21.6],
                                [-43.5, -21.6],
                                [-43.5, -21.9],
                            ]
                        ],
                    },
                }
            ],
        }
        localities = [{"id": 3136702, "nome": "Juiz de Fora"}]
        version, repeated, manifest = import_geometry_geojson(
            json.dumps(geometry).encode(),
            json.dumps(localities).encode(),
            source_url=IBGE_GEOMETRY_SOURCE,
            reference_year=2024,
            uf="MG",
        )
        assert repeated is False
        assert version.feature_count == 1
        assert manifest["crosswalkMatched"] == 1

    _prepare_representative(app)
    _login(client)
    candidate = client.get(
        f"/api/v1/electoral/candidates?election_id={election_id}&q=candidata"
    ).json["items"][0]
    municipality_map = client.get(
        f"/api/v1/electoral/candidates/{candidate['id']}/map"
        f"?election_id={election_id}&level=municipality"
    )
    assert municipality_map.status_code == 200
    assert municipality_map.json["official"] is True
    assert municipality_map.json["features"][0]["properties"]["votes"] == 123
    assert municipality_map.json["features"][0]["properties"]["geometry_official"] is True

    zone_map = client.get(
        f"/api/v1/electoral/candidates/{candidate['id']}/map"
        f"?election_id={election_id}&level=electoral_zone"
    )
    assert zone_map.status_code == 200
    assert zone_map.json["geometry_available"] is False
    assert zone_map.json["features"] == []
    assert "polígonos oficiais" in zone_map.json["warning"]


def test_auditable_async_exports_generate_protected_pdf_csv_and_xlsx(
    app, client, tmp_path
):
    path = _archive(tmp_path, [_row(), _row(votes="77", candidate="1002")])
    with app.app_context():
        import_dataset_archive(
            path,
            source_url=SOURCE_URL,
            election_year=2022,
            election_scope="general",
            uf="MG",
            office_code="6",
            expected_total_votes=200,
        )
        election_id = db.session.scalar(select(ElectoralElection.id))

    _prepare_representative(app)
    with app.app_context():
        tenant = db.session.execute(select(Tenant).where(Tenant.slug == "gabinete-a")).scalar_one()
        db.session.add(
            ElectoralModuleSettings(
                tenant_id=tenant.id,
                feature_flags={"catalogo": True, "exportacoes": True, "delegacao": True},
            )
        )
        db.session.commit()
    _login(client)
    candidates = client.get(
        f"/api/v1/electoral/candidates?election_id={election_id}&q=candidata"
    ).json["items"]
    csrf = client.get_cookie("csrf_access_token").value

    created = []
    for report_format in ("PDF", "CSV", "XLSX"):
        response = client.post(
            "/api/v1/electoral/report-jobs",
            json={
                "format": report_format,
                "report_type": "candidate",
                "purpose": "Planejamento territorial interno do gabinete",
                "election_id": str(election_id),
                "candidate_ids": [candidates[0]["id"]],
                "level": "municipality",
            },
            headers={"X-CSRF-TOKEN": csrf},
        )
        assert response.status_code == 202
        assert response.json["status"] == "QUEUED"
        created.append(response.json)

    with app.app_context():
        result = process_batch("electoral-export-test-worker")
        assert result.failed == 0
        assert db.session.scalar(select(func.count()).select_from(ElectoralGeneratedReport)) == 3

    downloads = {}
    for job in created:
        status = client.get(f"/api/v1/electoral/report-jobs/{job['id']}")
        assert status.status_code == 200
        assert status.json["status"] == "COMPLETED"
        assert status.json["report"]["available"] is True
        shared = client.post(
            f"/api/v1/electoral/report-jobs/{job['id']}/share",
            headers={"X-CSRF-TOKEN": csrf},
        )
        assert shared.status_code == 200
        download = client.get(shared.json["download_url"])
        assert download.status_code == 200
        downloads[job["format"]] = download.data

    assert downloads["PDF"].startswith(b"%PDF")
    assert b"Territorio" in downloads["CSV"]
    with zipfile.ZipFile(io.BytesIO(downloads["XLSX"])) as workbook:
        assert "xl/worksheets/sheet1.xml" in workbook.namelist()
        assert b"Planejamento territorial" in workbook.read("xl/worksheets/sheet1.xml")

    revoked = client.delete(
        f"/api/v1/electoral/report-jobs/{created[0]['id']}",
        headers={"X-CSRF-TOKEN": csrf},
    )
    assert revoked.status_code == 204
    with app.app_context():
        assert set(
            db.session.scalars(
                select(AuditLog.action).where(AuditLog.action.like("electoral.report.%"))
            )
        ) >= {
            "electoral.report.requested",
            "electoral.report.generated",
            "electoral.report.shared",
            "electoral.report.downloaded",
            "electoral.report.revoked",
        }
