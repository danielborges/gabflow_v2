from sqlalchemy import select

from app.extensions import db
from app.geocoding.contract import (
    CanonicalGeocodeResult,
    GeocodeGranularity,
    GeocodeStatus,
    NormalizedAddress,
)
from app.models import AuditLog, Tenant

PASSWORD = "SenhaForte123!"  # noqa: S105


def _login(client):
    client.post(
        "/api/v1/auth/login",
        json={"tenant": "gabinete-a", "email": "admin@teste.local", "password": PASSWORD},
    )
    return client.get_cookie("csrf_access_token").value


def _post(client, path, csrf, payload):
    return client.post(path, json=payload, headers={"X-CSRF-TOKEN": csrf})


def _request(client, csrf):
    response = _post(
        client,
        "/api/v1/solicitacoes",
        csrf,
        {
            "origem": "PRESENCIAL",
            "titulo": "Localização de homologação",
            "descricao": "Registro sintético para validar a geocodificação.",
            "endereco": "Rua Halfeld, 10, Centro",
        },
    )
    assert response.status_code == 201
    return response.json


class _GeoapifyStub:
    def __init__(self, *_args, **_kwargs):
        pass

    def geocode(self, query):
        return CanonicalGeocodeResult(
            provider="GEOAPIFY",
            provider_version="geocoding-v1",
            query_fingerprint=query.fingerprint,
            status=GeocodeStatus.VERIFIED,
            latitude=-21.76,
            longitude=-43.35,
            confidence=0.98,
            granularity=GeocodeGranularity.ADDRESS,
            address=NormalizedAddress(
                formatted="Rua Halfeld, 10, Centro, Juiz de Fora - MG",
                number="10",
                street="Rua Halfeld",
                neighborhood="Centro",
                city="Juiz de Fora",
                state="MG",
                country_code="BR",
            ),
            provider_result_id="geoapify-test",
            candidate_count=1,
            attribution=("Geoapify", "OpenStreetMap contributors"),
            retention_policy="PERSIST_WITH_SOURCE_ATTRIBUTION",
            metadata={"matchType": "building"},
        )


def _enable(app, monkeypatch, daily_limit=1):
    app.config.update(
        APP_ENV="homologation",
        GEOAPIFY_API_KEY="homologation-secret",
        GEOCODING_HOMOLOGATION_ENABLED=True,
        GEOCODING_HOMOLOGATION_DAILY_LIMIT=daily_limit,
    )
    monkeypatch.setattr("app.requests.routes.GeoapifyAdapter", _GeoapifyStub)
    with app.app_context():
        tenant = db.session.execute(select(Tenant).where(Tenant.slug == "gabinete-a")).scalar_one()
        tenant.jurisdiction_city = "Juiz de Fora"
        tenant.jurisdiction_state = "MG"
        tenant.jurisdiction_bounds = {
            "minLatitude": -21.9,
            "maxLatitude": -21.6,
            "minLongitude": -43.5,
            "maxLongitude": -43.2,
        }
        tenant.jurisdiction_geojson = {
            "type": "Polygon",
            "coordinates": [
                [
                    [-43.5, -21.9],
                    [-43.2, -21.9],
                    [-43.2, -21.6],
                    [-43.5, -21.6],
                    [-43.5, -21.9],
                ]
            ],
        }
        db.session.commit()


def test_geoapify_homologation_requires_flag_and_non_production(app, client, monkeypatch):
    csrf = _login(client)
    item = _request(client, csrf)
    _enable(app, monkeypatch)
    app.config["APP_ENV"] = "production"

    response = _post(
        client,
        f"/api/v1/solicitacoes/{item['id']}/geocodificacao/geoapify",
        csrf,
        {"confirmacaoDadosTeste": True},
    )

    assert response.status_code == 403
    assert response.json["error"] == "geocoding_homologation_disabled"
    assert "proibida em produção" in response.json["message"]


def test_geoapify_homologation_enforces_quota_and_human_review(
    app, client, monkeypatch
):
    csrf = _login(client)
    item = _request(client, csrf)
    _enable(app, monkeypatch, daily_limit=1)
    endpoint = f"/api/v1/solicitacoes/{item['id']}/geocodificacao/geoapify"

    missing_confirmation = _post(client, endpoint, csrf, {})
    assert missing_confirmation.status_code == 422
    assert missing_confirmation.json["error"] == "test_data_confirmation_required"

    geocoded = _post(client, endpoint, csrf, {"confirmacaoDadosTeste": True})
    assert geocoded.status_code == 200
    assert geocoded.json["latitude"] == -21.76
    assert geocoded.json["longitude"] == -43.35
    assert geocoded.json["qualidadeGeografica"] == {
        "origem": "GEOAPIFY",
        "metodo": "HOMOLOGATION_EXTERNAL",
        "confianca": 0.98,
        "verificada": False,
        "status": "APPROXIMATE",
        "atualizadaEm": geocoded.json["qualidadeGeografica"]["atualizadaEm"],
        "atribuicoes": ["Geoapify", "OpenStreetMap contributors"],
        "revisaoPendente": True,
    }
    assert geocoded.json["geocodificacaoHomologacao"]["restantesHoje"] == 0

    quota = _post(client, endpoint, csrf, {"confirmacaoDadosTeste": True})
    assert quota.status_code == 429
    assert quota.json["error"] == "geocoding_quota_exceeded"

    reviewed = _post(
        client,
        f"/api/v1/solicitacoes/{item['id']}/geocodificacao/revisao",
        csrf,
        {"decisao": "APROVAR", "justificativa": "Conferido na malha oficial."},
    )
    assert reviewed.status_code == 200
    assert reviewed.json["qualidadeGeografica"]["status"] == "VERIFIED"
    assert reviewed.json["qualidadeGeografica"]["verificada"] is True
    assert reviewed.json["qualidadeGeografica"]["revisaoPendente"] is False

    with app.app_context():
        audit = db.session.execute(
            select(AuditLog).where(AuditLog.action == "request.geocoding.geoapify.executed")
        ).scalar_one()
        assert "Rua Halfeld" not in str(audit.before)
        assert "Rua Halfeld" not in str(audit.after)
