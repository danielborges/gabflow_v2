import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError

from app.extensions import db
from app.models import (
    GlobalDistributionPolicy,
    GlobalEntitlementStatus,
    GlobalKnowledgeCollection,
    GlobalKnowledgeEntitlement,
    GlobalUpdateMode,
    RagChunk,
    RagDocument,
    RagDocumentAccess,
    RagDocumentVersion,
    RagKnowledgeSource,
    RagKnowledgeSourceStatus,
    Role,
    Tenant,
    User,
)
from app.tenant_context import activate_global_knowledge_context, tenant_context

pytestmark = pytest.mark.postgres
RUNTIME_ROLE = "gabflow_rls_test"
TEST_PASSWORD_HASH = "integration-test-only"  # noqa: S105


def test_rag_rls_is_forced_and_default_deny(postgres_app):
    tenant_a, tenant_b, _chunk_a, _version_b = _seed_rag_tenants(postgres_app)
    _ensure_runtime_role(postgres_app)

    with postgres_app.app_context(), db.engine.connect() as connection:
        transaction = connection.begin()
        connection.execute(text(f"SET LOCAL ROLE {RUNTIME_ROLE}"))

        assert connection.execute(text("SELECT count(*) FROM rag_documents")).scalar_one() == 0

        connection.execute(
            text("SELECT set_config('app.tenant_id', :tenant_id, true)"),
            {"tenant_id": str(tenant_a)},
        )
        visible = (
            connection.execute(text("SELECT tenant_id FROM rag_documents ORDER BY tenant_id"))
            .scalars()
            .all()
        )
        assert visible == [tenant_a]
        visible_entitlements = (
            connection.execute(text("SELECT tenant_id FROM rag_global_entitlements"))
            .scalars()
            .all()
        )
        assert visible_entitlements == [tenant_a]

        hidden_update = connection.execute(
            text("UPDATE rag_documents SET title = 'invasao' WHERE tenant_id = :tenant_id"),
            {"tenant_id": str(tenant_b)},
        )
        assert hidden_update.rowcount == 0
        transaction.rollback()


def test_rag_composite_fk_rejects_cross_tenant_relationship(postgres_app):
    tenant_a, _tenant_b, chunk_a, version_b = _seed_rag_tenants(postgres_app)
    _ensure_runtime_role(postgres_app)

    with postgres_app.app_context(), db.engine.connect() as connection:
        transaction = connection.begin()
        connection.execute(text(f"SET LOCAL ROLE {RUNTIME_ROLE}"))
        connection.execute(
            text("SELECT set_config('app.tenant_id', :tenant_id, true)"),
            {"tenant_id": str(tenant_a)},
        )
        with pytest.raises(IntegrityError):
            connection.execute(
                text(
                    """
                    UPDATE rag_chunks
                    SET version_id = :foreign_version
                    WHERE id = :chunk_id
                    """
                ),
                {
                    "foreign_version": str(version_b),
                    "chunk_id": str(chunk_a),
                },
            )
        transaction.rollback()


def test_operational_knowledge_sources_are_tenant_isolated(postgres_app):
    tenant_a, tenant_b, _chunk_a, _version_b = _seed_rag_tenants(postgres_app)
    _ensure_runtime_role(postgres_app)
    with postgres_app.app_context():
        for tenant_id in (tenant_a, tenant_b):
            with tenant_context(tenant_id):
                db.session.add(
                    RagKnowledgeSource(
                        tenant_id=tenant_id,
                        source_module="SOLICITACOES",
                        entity_type="SERVICE_REQUEST",
                        entity_id=uuid.uuid4(),
                        purpose="MEMORIA_OPERACIONAL",
                        legal_basis="EXERCICIO_REGULAR_DE_DIREITOS",
                        access_level=RagDocumentAccess.INTERNO,
                        status=RagKnowledgeSourceStatus.ATIVA,
                    )
                )
                db.session.commit()

    with postgres_app.app_context(), db.engine.connect() as connection:
        transaction = connection.begin()
        connection.execute(text(f"SET LOCAL ROLE {RUNTIME_ROLE}"))
        assert connection.execute(
            text("SELECT count(*) FROM rag_knowledge_sources")
        ).scalar_one() == 0
        connection.execute(
            text("SELECT set_config('app.tenant_id', :tenant_id, true)"),
            {"tenant_id": str(tenant_a)},
        )
        assert connection.execute(
            text("SELECT tenant_id FROM rag_knowledge_sources")
        ).scalar_one() == tenant_a
        hidden = connection.execute(
            text(
                "UPDATE rag_knowledge_sources SET purpose = 'INVASAO' "
                "WHERE tenant_id = :tenant_id"
            ),
            {"tenant_id": str(tenant_b)},
        )
        assert hidden.rowcount == 0
        transaction.rollback()


def test_transaction_local_tenant_context_does_not_leak(postgres_app):
    tenant_a, tenant_b, _chunk_a, _version_b = _seed_rag_tenants(postgres_app)
    _ensure_runtime_role(postgres_app)

    with postgres_app.app_context(), db.engine.connect() as connection:
        with connection.begin():
            connection.execute(text(f"SET LOCAL ROLE {RUNTIME_ROLE}"))
            connection.execute(
                text("SELECT set_config('app.tenant_id', :tenant_id, true)"),
                {"tenant_id": str(tenant_a)},
            )
            assert connection.execute(text("SELECT count(*) FROM rag_documents")).scalar_one() == 1

        with connection.begin():
            connection.execute(text(f"SET LOCAL ROLE {RUNTIME_ROLE}"))
            assert connection.execute(text("SELECT count(*) FROM rag_documents")).scalar_one() == 0
            connection.execute(
                text("SELECT set_config('app.tenant_id', :tenant_id, true)"),
                {"tenant_id": str(tenant_b)},
            )
            tenants = (
                connection.execute(text("SELECT tenant_id FROM rag_documents")).scalars().all()
            )
            assert tenants == [tenant_b]


def test_runtime_role_cannot_bypass_rls(postgres_app):
    _ensure_runtime_role(postgres_app)

    with postgres_app.app_context(), db.engine.connect() as connection:
        attributes = connection.execute(
            text(
                """
                SELECT rolsuper, rolcreatedb, rolcreaterole, rolbypassrls
                FROM pg_roles
                WHERE rolname = :role
                """
            ),
            {"role": RUNTIME_ROLE},
        ).one()
        policies = (
            connection.execute(
                text(
                    """
                SELECT tablename
                FROM pg_policies
                WHERE schemaname = 'public'
                  AND tablename LIKE 'rag_%'
                ORDER BY tablename
                """
                )
            )
            .scalars()
            .all()
        )
        forced = (
            connection.execute(
                text(
                    """
                SELECT relname
                FROM pg_class
                WHERE relname = ANY(:tables)
                  AND relrowsecurity
                  AND relforcerowsecurity
                ORDER BY relname
                """
                ),
                {
                    "tables": [
                        "rag_assistant_queries",
                        "rag_chunks",
                        "rag_document_versions",
                        "rag_documents",
                        "rag_global_entitlements",
                        "rag_knowledge_sources",
                    ]
                },
            )
            .scalars()
            .all()
        )

    assert attributes == (False, False, False, False)
    assert policies == [
        "rag_assistant_queries",
        "rag_chunks",
        "rag_document_versions",
        "rag_documents",
        "rag_global_entitlements",
        "rag_knowledge_sources",
    ]
    assert forced == policies


def _seed_rag_tenants(postgres_app):
    with postgres_app.app_context():
        suffix = uuid.uuid4().hex[:8]
        tenant_a = Tenant(name=f"RLS A {suffix}", slug=f"rls-a-{suffix}")
        tenant_b = Tenant(name=f"RLS B {suffix}", slug=f"rls-b-{suffix}")
        db.session.add_all([tenant_a, tenant_b])
        db.session.flush()
        user_a = User(
            tenant_id=tenant_a.id,
            name="RLS A",
            email=f"rls-a-{suffix}@test.local",
            password_hash=TEST_PASSWORD_HASH,
            role=Role.ADMIN,
        )
        user_b = User(
            tenant_id=tenant_b.id,
            name="RLS B",
            email=f"rls-b-{suffix}@test.local",
            password_hash=TEST_PASSWORD_HASH,
            role=Role.ADMIN,
        )
        db.session.add_all([user_a, user_b])
        db.session.flush()
        collection = GlobalKnowledgeCollection(
            name=f"Catálogo RLS {suffix}",
            distribution_policy=GlobalDistributionPolicy.OPCIONAL,
            jurisdiction={},
            created_by_id=user_a.id,
        )
        db.session.add(collection)
        db.session.commit()
        activate_global_knowledge_context()
        db.session.add_all(
            [
                GlobalKnowledgeEntitlement(
                    tenant_id=tenant_a.id,
                    collection_id=collection.id,
                    status=GlobalEntitlementStatus.ATIVA,
                    update_mode=GlobalUpdateMode.AUTOMATICA,
                    grant_source="TENANT_ADESAO",
                    granted_by_id=user_a.id,
                ),
                GlobalKnowledgeEntitlement(
                    tenant_id=tenant_b.id,
                    collection_id=collection.id,
                    status=GlobalEntitlementStatus.ATIVA,
                    update_mode=GlobalUpdateMode.AUTOMATICA,
                    grant_source="TENANT_ADESAO",
                    granted_by_id=user_b.id,
                ),
            ]
        )
        db.session.commit()

        with tenant_context(tenant_a.id):
            document_a, _version_a, chunk_a = _rag_graph(tenant_a.id, user_a.id, "A")
            db.session.add(document_a)
            db.session.commit()
        with tenant_context(tenant_b.id):
            document_b, version_b, _chunk_b = _rag_graph(tenant_b.id, user_b.id, "B")
            db.session.add(document_b)
            db.session.commit()
        return tenant_a.id, tenant_b.id, chunk_a.id, version_b.id


def _rag_graph(tenant_id, user_id, label):
    document = RagDocument(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        title=f"Documento RLS {label}",
        document_type="LEGISLACAO",
        access_level=RagDocumentAccess.INTERNO,
        created_by_id=user_id,
    )
    version = RagDocumentVersion(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        document=document,
        version_number=1,
        version_label="1",
        storage_key="placeholder",
        original_name="documento.txt",
        mime_type="text/plain",
        size_bytes=20,
        checksum="a" * 64,
        created_by_id=user_id,
    )
    version.storage_key = f"tenants/{tenant_id}/rag/{document.id}/{version.id}/documento.txt"
    chunk = RagChunk(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        version=version,
        position=0,
        content=f"Conteúdo privado {label}",
        content_checksum="b" * 64,
        embedding=[1.0, 0.0],
        embedding_model="test",
    )
    return document, version, chunk


def _ensure_runtime_role(postgres_app):
    with (
        postgres_app.app_context(),
        db.engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection,
    ):
        try:
            connection.execute(
                text(
                    """
                    DO $$
                    BEGIN
                        IF NOT EXISTS (
                            SELECT 1 FROM pg_roles WHERE rolname = 'gabflow_rls_test'
                        ) THEN
                            CREATE ROLE gabflow_rls_test
                                NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS;
                        END IF;
                    END
                    $$;
                    """
                )
            )
            connection.execute(
                text(
                    """
                    ALTER ROLE gabflow_rls_test
                        NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS;
                    GRANT USAGE ON SCHEMA public TO gabflow_rls_test;
                    GRANT SELECT, INSERT, UPDATE, DELETE
                        ON rag_documents, rag_document_versions, rag_chunks,
                           rag_assistant_queries, rag_global_entitlements,
                           rag_knowledge_sources
                        TO gabflow_rls_test;
                    """
                )
            )
        except DBAPIError as error:
            pytest.fail(f"PostgreSQL test user must be able to manage test roles: {error}")
