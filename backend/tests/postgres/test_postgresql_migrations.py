from datetime import UTC, datetime

import pytest
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from flask_migrate import downgrade, upgrade
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import Citizen, RequestSource, Role, ServiceRequest, Tenant, User

pytestmark = pytest.mark.postgres
TEST_PASSWORD_HASH = "integration-test-only"  # noqa: S105


def test_real_migrations_reach_the_expected_head(postgres_app):
    migrations = ScriptDirectory("migrations")

    with postgres_app.app_context(), db.engine.connect() as connection:
        current_heads = set(MigrationContext.configure(connection).get_current_heads())
        expected_heads = set(migrations.get_heads())
        table_names = set(inspect(connection).get_table_names())

    assert current_heads == expected_heads
    assert {
        "alembic_version",
        "ai_executions",
        "audit_logs",
        "citizens",
        "document_ocrs",
        "legislative_drafts",
        "legislative_draft_requests",
        "legislative_tramitations",
        "legislative_draft_versions",
        "legislative_templates",
        "normative_sources",
        "privacy_requests",
        "rag_chunks",
        "rag_documents",
        "rag_document_versions",
        "scheduled_returns",
        "service_requests",
        "tenants",
        "users",
    }.issubset(table_names)


def test_migrations_create_native_postgresql_enums(postgres_app):
    enum_query = text(
        """
        SELECT enumlabel
        FROM pg_enum
        JOIN pg_type ON pg_type.oid = pg_enum.enumtypid
        WHERE pg_type.typname = :enum_name
        ORDER BY pg_enum.enumsortorder
        """
    )

    with postgres_app.app_context(), db.engine.connect() as connection:
        request_statuses = connection.execute(
            enum_query, {"enum_name": "request_status"}
        ).scalars().all()
        notification_types = connection.execute(
            enum_query, {"enum_name": "notification_type"}
        ).scalars().all()
        tramitation_statuses = connection.execute(
            enum_query, {"enum_name": "legislative_tramitation_status"}
        ).scalars().all()

    assert request_statuses == [
        "NOVA",
        "TRIAGEM",
        "EM_ATENDIMENTO",
        "AGUARDANDO_ORGAO",
        "AGUARDANDO_CIDADAO",
        "RESOLVIDA",
        "ENCERRADA",
        "CANCELADA",
    ]
    assert notification_types == ["ATRIBUICAO", "TAREFA", "SLA", "SISTEMA", "RETORNO"]
    assert tramitation_statuses == [
        "PROTOCOLADA",
        "DISTRIBUIDA",
        "EM_COMISSAO",
        "EM_PAUTA",
        "APROVADA",
        "REJEITADA",
        "SANCIONADA",
        "VETADA",
        "ARQUIVADA",
        "RETIRADA",
    ]


def test_postgis_generates_request_locations_and_spatial_index(postgres_app):
    with postgres_app.app_context():
        extension_enabled = db.session.execute(
            text("SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'postgis')")
        ).scalar_one()
        columns = {
            row["column_name"]: row["udt_name"]
            for row in db.session.execute(
                text(
                    """
                    SELECT column_name, udt_name
                    FROM information_schema.columns
                    WHERE table_name = 'service_requests'
                    """
                )
            ).mappings()
        }
        index_definition = db.session.execute(
            text(
                """
                SELECT indexdef
                FROM pg_indexes
                WHERE tablename = 'service_requests'
                  AND indexname = 'ix_service_requests_location_geography'
                """
            )
        ).scalar_one()

        tenant = Tenant(name="Gabinete PostGIS", slug="gabinete-postgis")
        db.session.add(tenant)
        db.session.flush()
        user = User(
            tenant_id=tenant.id,
            name="Admin PostGIS",
            email="admin@postgis.test",
            password_hash=TEST_PASSWORD_HASH,
            role=Role.ADMIN,
        )
        db.session.add(user)
        db.session.flush()
        request = ServiceRequest(
            tenant_id=tenant.id,
            protocol="GF-POSTGIS-001",
            source=RequestSource.WHATSAPP,
            title="Ponto territorial",
            description="Demanda com coordenada para teste espacial.",
            latitude=-21.7619,
            longitude=-43.3496,
            created_by_id=user.id,
        )
        db.session.add(request)
        db.session.commit()

        location = db.session.execute(
            text(
                """
                SELECT
                    ST_AsText(location_geography::geometry) AS point,
                    ST_DWithin(
                        location_geography,
                        ST_SetSRID(ST_MakePoint(-43.3496, -21.7619), 4326)::geography,
                        50
                    ) AS near_reference
                FROM service_requests
                WHERE id = CAST(:request_id AS uuid)
                """
            ),
            {"request_id": str(request.id)},
        ).mappings().one()

    assert extension_enabled is True
    assert columns["location_geography"] == "geography"
    assert "using gist" in index_definition.lower()
    assert location["point"] == "POINT(-43.3496 -21.7619)"
    assert location["near_reference"] is True


def test_latest_migration_can_be_rolled_back_and_reapplied(postgres_app):
    migrations = ScriptDirectory("migrations")
    expected_head = migrations.get_current_head()
    previous_head = migrations.get_revision(expected_head).down_revision

    with postgres_app.app_context():
        downgrade(revision="-1", directory="migrations")

        with db.engine.connect() as connection:
            rolled_back_heads = set(
                MigrationContext.configure(connection).get_current_heads()
            )
            inspector = inspect(connection)
            rolled_back_tables = set(inspector.get_table_names())
            rolled_back_service_columns = {
                column["name"] for column in inspector.get_columns("service_requests")
            }
            rolled_back_tenant_columns = {
                column["name"] for column in inspector.get_columns("tenants")
            }

        assert rolled_back_heads == {previous_head}
        assert "legislative_drafts" in rolled_back_tables
        assert "legislative_tramitations" in rolled_back_tables
        assert "normative_sources" in rolled_back_tables
        assert "rag_documents" in rolled_back_tables
        assert "rag_document_versions" in rolled_back_tables
        assert "rag_chunks" in rolled_back_tables
        assert "rag_assistant_queries" in rolled_back_tables
        assert "location_geography" in rolled_back_service_columns
        assert "jurisdiction_name" in rolled_back_tenant_columns
        assert "jurisdiction_geojson" not in rolled_back_tenant_columns

        upgrade(directory="migrations")

        with db.engine.connect() as connection:
            reapplied_heads = set(MigrationContext.configure(connection).get_current_heads())
            inspector = inspect(connection)
            reapplied_tables = set(inspector.get_table_names())
            reapplied_service_columns = {
                column["name"] for column in inspector.get_columns("service_requests")
            }
            reapplied_tenant_columns = {
                column["name"] for column in inspector.get_columns("tenants")
            }

        assert reapplied_heads == {expected_head}
        assert "legislative_drafts" in reapplied_tables
        assert "legislative_tramitations" in reapplied_tables
        assert "normative_sources" in reapplied_tables
        assert "rag_documents" in reapplied_tables
        assert "rag_document_versions" in reapplied_tables
        assert "rag_chunks" in reapplied_tables
        assert "rag_assistant_queries" in reapplied_tables
        assert "location_geography" in reapplied_service_columns
        assert "jurisdiction_name" in reapplied_tenant_columns
        assert "jurisdiction_geojson" in reapplied_tenant_columns


def test_migrated_schema_preserves_json_timezone_and_unique_constraints(postgres_app):
    aware_timestamp = datetime(2026, 7, 16, 18, 30, tzinfo=UTC)

    with postgres_app.app_context():
        tenant = Tenant(
            name="Gabinete PostgreSQL",
            slug="gabinete-postgresql",
            chamber_type="CAMARA_MUNICIPAL",
            jurisdiction_name="Brasília/DF",
            jurisdiction_city="Brasília",
            jurisdiction_state="DF",
            jurisdiction_ibge_code="5300108",
            jurisdiction_center_latitude=-15.7939,
            jurisdiction_center_longitude=-47.8828,
            jurisdiction_bounds={
                "minLatitude": -16.1,
                "maxLatitude": -15.5,
                "minLongitude": -48.2,
                "maxLongitude": -47.5,
            },
            jurisdiction_geojson={
                "type": "FeatureCollection",
                "features": [
                    {"type": "Feature", "geometry": {"type": "Polygon", "coordinates": []}}
                ],
            },
        )
        db.session.add(tenant)
        db.session.flush()

        user = User(
            tenant_id=tenant.id,
            name="Admin PostgreSQL",
            email="admin@postgresql.test",
            password_hash=TEST_PASSWORD_HASH,
            role=Role.ADMIN,
            created_at=aware_timestamp,
        )
        citizen = Citizen(
            tenant_id=tenant.id,
            name="Cidadã PostgreSQL",
            contacts=[{"tipo": "EMAIL", "valor": "cidada@postgresql.test"}],
            addresses=[{"cidade": "Brasília", "uf": "DF"}],
            legal_basis="EXECUCAO_POLITICA_PUBLICA",
            privacy_flags=["DADO_PESSOAL"],
        )
        db.session.add_all([user, citizen])
        db.session.commit()

        db.session.expire_all()
        stored_user = db.session.get(User, user.id)
        stored_citizen = db.session.get(Citizen, citizen.id)

        assert stored_user.created_at == aware_timestamp
        assert stored_user.created_at.utcoffset() is not None
        assert stored_user.tenant.jurisdiction_name == "Brasília/DF"
        assert stored_user.tenant.jurisdiction_bounds["minLatitude"] == -16.1
        assert stored_user.tenant.jurisdiction_ibge_code == "5300108"
        assert stored_user.tenant.jurisdiction_geojson["type"] == "FeatureCollection"
        assert stored_citizen.contacts[0]["valor"] == "cidada@postgresql.test"
        assert stored_citizen.addresses == [{"cidade": "Brasília", "uf": "DF"}]

        db.session.add(
            User(
                tenant_id=tenant.id,
                name="Usuário duplicado",
                email="admin@postgresql.test",
                password_hash=TEST_PASSWORD_HASH,
            )
        )
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()
