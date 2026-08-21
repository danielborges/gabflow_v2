from sqlalchemy import select

from app.directory.addresses import resolve_address
from app.extensions import db
from app.models import Tenant, Territory, TerritoryNeighborhood
from app.territory_import import TerritoryImportResult, import_official_territories
from app.territory_suggestions import reload_suggested_territories


def _polygon(min_longitude, min_latitude, max_longitude, max_latitude):
    return {
        "type": "Polygon",
        "coordinates": [
            [
                [min_longitude, min_latitude],
                [max_longitude, min_latitude],
                [max_longitude, max_latitude],
                [min_longitude, max_latitude],
                [min_longitude, min_latitude],
            ]
        ],
    }


def test_official_import_is_idempotent_and_links_neighborhood(app, monkeypatch):
    territory_features = [
        {
            "type": "Feature",
            "properties": {"nro": "5", "nome": "Centro", "ano": "2018"},
            "geometry": _polygon(-43.40, -21.80, -43.30, -21.70),
        },
        {
            "type": "Feature",
            "properties": {"nro": "1", "nome": "Norte", "ano": "2018"},
            "geometry": _polygon(-43.40, -21.70, -43.30, -21.60),
        },
    ]
    neighborhoods = [
        {
            "name": "Granbery",
            "external_code": "3136702018",
            "geometry": _polygon(-43.36, -21.77, -43.34, -21.75),
            "source_url": "https://ibge.test/MG_bairros.zip",
            "source_version": "CENSO_2022",
        }
    ]
    monkeypatch.setattr(
        "app.territory_import._fetch_arcgis_features", lambda _url: territory_features
    )
    monkeypatch.setattr(
        "app.territory_import._fetch_ibge_neighborhoods", lambda _tenant: neighborhoods
    )

    with app.app_context():
        tenant = db.session.execute(
            select(Tenant).where(Tenant.slug == "gabinete-a")
        ).scalar_one()
        tenant.jurisdiction_city = "Juiz de Fora"
        tenant.jurisdiction_state = "MG"
        tenant.jurisdiction_ibge_code = "3136702"
        db.session.add(Territory(tenant_id=tenant.id, name="Zona Norte"))
        db.session.flush()

        first = import_official_territories(tenant)
        second = import_official_territories(tenant)

        assert first.territory_count == second.territory_count == 2
        assert first.neighborhood_count == first.matched_neighborhood_count == 1
        territories = list(
            db.session.execute(
                select(Territory).where(Territory.tenant_id == tenant.id)
            ).scalars()
        )
        assert len(territories) == 2
        assert next(item for item in territories if item.name == "Zona Norte").geometry
        centro = next(item for item in territories if item.name == "Centro")
        assert centro.source_name == "PJF_SISURB_REGIOES_PLANEJAMENTO"
        assert centro.source_ref == "5"
        assert centro.source_version == "2018"

        stored = db.session.execute(
            select(TerritoryNeighborhood).where(
                TerritoryNeighborhood.tenant_id == tenant.id
            )
        ).scalar_one()
        assert stored.name == "Granbery"
        assert stored.territory_id == centro.id

        by_name = resolve_address(
            tenant.id,
            {"endereco": "Granbery, Juiz de Fora", "bairro": "granbery"},
        )
        assert by_name["territorio"] == "Centro"
        assert by_name["metodoResolucao"] == "BAIRRO_OFICIAL"

        by_point = resolve_address(
            tenant.id,
            {
                "endereco": "Rua no Granbery",
                "bairro": "Nome divergente",
                "latitude": -21.76,
                "longitude": -43.35,
            },
        )
        assert by_point["territorio"] == "Centro"
        assert by_point["metodoResolucao"] == "POLIGONO"


def test_official_import_uses_ibge_districts_as_generic_fallback(app, monkeypatch):
    district_source = {
        "name": "IBGE_CENSO_2022_DISTRITOS",
        "version": "CENSO_2022",
        "url": "https://ibge.test/XX_distritos.zip",
        "name_field": "name",
        "id_field": "external_code",
        "version_field": "source_version",
    }
    district_features = [
        {
            "type": "Feature",
            "properties": {
                "name": "Distrito Sede",
                "external_code": "999999905",
                "source_version": "CENSO_2022",
            },
            "geometry": _polygon(-44.0, -22.0, -43.0, -21.0),
        }
    ]
    neighborhoods = [
        {
            "name": "Centro",
            "external_code": "9999999001",
            "geometry": _polygon(-43.6, -21.6, -43.4, -21.4),
            "source_url": "https://ibge.test/XX_bairros.zip",
            "source_version": "CENSO_2022",
        }
    ]
    monkeypatch.setattr(
        "app.territory_import._fetch_ibge_districts",
        lambda _tenant: (district_source, district_features),
    )
    monkeypatch.setattr(
        "app.territory_import._fetch_ibge_neighborhoods", lambda _tenant: neighborhoods
    )

    with app.app_context():
        tenant = db.session.execute(
            select(Tenant).where(Tenant.slug == "gabinete-a")
        ).scalar_one()
        tenant.jurisdiction_city = "Município de Teste"
        tenant.jurisdiction_state = "XX"
        tenant.jurisdiction_ibge_code = "9999999"

        result = import_official_territories(tenant)

        assert result.source_name == "IBGE_CENSO_2022_DISTRITOS"
        assert result.territory_count == 1
        assert result.neighborhood_count == result.matched_neighborhood_count == 1
        territory = db.session.execute(
            select(Territory).where(Territory.tenant_id == tenant.id)
        ).scalar_one()
        assert territory.name == "Distrito Sede"
        assert territory.source_ref == "999999905"
        neighborhood = db.session.execute(
            select(TerritoryNeighborhood).where(
                TerritoryNeighborhood.tenant_id == tenant.id
            )
        ).scalar_one()
        assert neighborhood.territory_id == territory.id


def test_reload_prioritizes_official_geometries_over_legacy_names(app, monkeypatch):
    def fake_import(tenant):
        db.session.add(
            Territory(
                tenant_id=tenant.id,
                name="Território Oficial",
                geometry=_polygon(-44.0, -22.0, -43.0, -21.0),
                source_name="FONTE_OFICIAL",
                source_ref="1",
            )
        )
        db.session.flush()
        return TerritoryImportResult(
            source_name="FONTE_OFICIAL",
            territory_count=1,
            neighborhood_count=0,
            matched_neighborhood_count=0,
        )

    monkeypatch.setattr("app.territory_suggestions.import_official_territories", fake_import)
    monkeypatch.setattr(
        "app.territory_suggestions.suggested_territory_names",
        lambda _tenant: (_ for _ in ()).throw(AssertionError("fallback indevido")),
    )

    with app.app_context():
        app.config["TERRITORY_OFFICIAL_IMPORT_ENABLED"] = True
        tenant = db.session.execute(
            select(Tenant).where(Tenant.slug == "gabinete-a")
        ).scalar_one()

        items, suggestions = reload_suggested_territories(tenant)

        assert suggestions == ["Território Oficial"]
        assert [item.name for item in items] == ["Território Oficial"]
