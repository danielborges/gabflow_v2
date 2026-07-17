from datetime import UTC, datetime

import pytest
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from flask_migrate import downgrade, upgrade
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import Citizen, Role, Tenant, User

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
        "privacy_requests",
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

        assert rolled_back_heads == {previous_head}
        assert "ai_executions" not in rolled_back_tables

        upgrade(directory="migrations")

        with db.engine.connect() as connection:
            reapplied_heads = set(MigrationContext.configure(connection).get_current_heads())
            reapplied_tables = set(inspect(connection).get_table_names())

        assert reapplied_heads == {expected_head}
        assert "ai_executions" in reapplied_tables


def test_migrated_schema_preserves_json_timezone_and_unique_constraints(postgres_app):
    aware_timestamp = datetime(2026, 7, 16, 18, 30, tzinfo=UTC)

    with postgres_app.app_context():
        tenant = Tenant(name="Gabinete PostgreSQL", slug="gabinete-postgresql")
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
