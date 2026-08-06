from datetime import UTC, datetime

import pytest
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from flask_migrate import downgrade, upgrade
from sqlalchemy import inspect, select, text
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import Citizen, Mandate, RequestSource, Role, ServiceRequest, Tenant, User

pytestmark = pytest.mark.postgres
TEST_PASSWORD_HASH = "integration-test-only"  # noqa: S105


def test_real_migrations_reach_the_expected_head(postgres_app):
    migrations = ScriptDirectory("migrations")

    with postgres_app.app_context(), db.engine.connect() as connection:
        current_heads = set(MigrationContext.configure(connection).get_current_heads())
        expected_heads = set(migrations.get_heads())
        table_names = set(inspect(connection).get_table_names())
        global_table_names = set(inspect(connection).get_table_names(schema="rag_global"))

    assert current_heads == expected_heads
    assert {
        "alembic_version",
        "ai_executions",
        "audit_logs",
        "citizens",
        "document_ocrs",
        "electoral_access_delegations",
        "electoral_coverage_profiles",
        "electoral_commitment_evidence",
        "electoral_commitment_history",
        "electoral_candidates",
        "electoral_candidacies",
        "electoral_dataset_versions",
        "electoral_elections",
        "electoral_favorites",
        "electoral_generated_reports",
        "electoral_geometry_features",
        "electoral_geometry_versions",
        "electoral_identity_reviews",
        "electoral_module_settings",
        "electoral_mandate_snapshots",
        "electoral_public_commitments",
        "electoral_offices",
        "electoral_parties",
        "electoral_results",
        "electoral_report_jobs",
        "electoral_saved_comparisons",
        "electoral_staging_results",
        "electoral_territory_crosswalks",
        "electoral_territories",
        "legislative_drafts",
        "legislative_draft_requests",
        "legislative_tramitations",
        "legislative_draft_versions",
        "legislative_templates",
        "mandates",
        "normative_sources",
        "privacy_requests",
        "political_parties",
        "rag_chunks",
        "rag_documents",
        "rag_document_versions",
        "rag_evaluation_questions",
        "rag_evaluation_runs",
        "rag_feedback_source_judgments",
        "rag_knowledge_sources",
        "rag_learning_artifact_feedback",
        "rag_learning_artifacts",
        "rag_learning_runs",
        "rag_query_feedback",
        "rag_security_rescan_runs",
        "rag_output_validation_profiles",
        "rls_audit_runs",
        "rag_thematic_memories",
        "scheduled_returns",
        "service_requests",
        "tenants",
        "users",
    }.issubset(table_names)
    assert {
        "collections",
        "documents",
        "document_versions",
        "chunks",
    } == global_table_names


def test_electoral_foundation_backfills_existing_representative(postgres_app):
    with postgres_app.app_context():
        downgrade(revision="h9d4f6a1c853", directory="migrations")
        tenant = Tenant(
            name="Gabinete preexistente",
            slug="gabinete-preexistente",
            chamber_type="CAMARA_MUNICIPAL",
            jurisdiction_name="Juiz de Fora/MG",
        )
        db.session.add(tenant)
        db.session.flush()
        representative = User(
            tenant_id=tenant.id,
            name="Parlamentar preexistente",
            email="preexistente@teste.local",
            password_hash=TEST_PASSWORD_HASH,
            role=Role.REPRESENTATIVE,
        )
        db.session.add(representative)
        db.session.commit()

        upgrade(directory="migrations")

        mandate = db.session.execute(
            select(Mandate).where(Mandate.representative_user_id == representative.id)
        ).scalar_one()
        assert mandate.status.value == "active"
        assert mandate.office == "CAMARA_MUNICIPAL"
        assert mandate.jurisdiction == "Juiz de Fora/MG"

    with postgres_app.app_context(), db.engine.connect() as connection:
        inspector = inspect(connection)
        electoral_candidate_columns = {
            column["name"] for column in inspector.get_columns("electoral_candidates")
        }
        electoral_rls = {
            row.table_name: (row.rls_enabled, row.rls_forced)
            for row in connection.execute(
                text(
                    """
                    SELECT relname AS table_name,
                           relrowsecurity AS rls_enabled,
                           relforcerowsecurity AS rls_forced
                    FROM pg_class
                    WHERE relname = ANY(:tables)
                    """
                ),
                {
                    "tables": [
                        "mandates",
                        "electoral_module_settings",
                        "electoral_access_delegations",
                    ]
                },
            )
        }
        assert electoral_rls == {
            "mandates": (True, True),
            "electoral_module_settings": (True, True),
            "electoral_access_delegations": (True, True),
        }
        assert "normalized_name" in electoral_candidate_columns
        query_columns = {
            column["name"] for column in inspector.get_columns("rag_assistant_queries")
        }
        outbox_columns = {column["name"] for column in inspector.get_columns("outbox_events")}
        outbox_indexes = {index["name"] for index in inspector.get_indexes("outbox_events")}
        evaluation_question_columns = {
            column["name"] for column in inspector.get_columns("rag_evaluation_questions")
        }
        evaluation_run_columns = {
            column["name"] for column in inspector.get_columns("rag_evaluation_runs")
        }
        learning_artifact_columns = {
            column["name"] for column in inspector.get_columns("rag_learning_artifacts")
        }
        rag_chunk_columns = {column["name"] for column in inspector.get_columns("rag_chunks")}
        global_chunk_columns = {
            column["name"] for column in inspector.get_columns("chunks", schema="rag_global")
        }
        private_version_columns = {
            column["name"] for column in inspector.get_columns("rag_document_versions")
        }
        operational_source_columns = {
            column["name"] for column in inspector.get_columns("rag_knowledge_sources")
        }
        feedback_columns = {
            column["name"] for column in inspector.get_columns("rag_query_feedback")
        }
        global_version_columns = {
            column["name"]
            for column in inspector.get_columns("document_versions", schema="rag_global")
        }
        attachment_columns = {column["name"] for column in inspector.get_columns("attachments")}
        rescan_columns = {
            column["name"] for column in inspector.get_columns("rag_security_rescan_runs")
        }
        vector_extension = connection.execute(
            text(
                """
                SELECT extversion
                FROM pg_extension
                WHERE extname = 'vector'
                """
            )
        ).scalar_one()
        hybrid_indexes = {
            row
            for row in connection.execute(
                text(
                    """
                    SELECT schemaname || '.' || indexname
                    FROM pg_indexes
                    WHERE indexname IN (
                        'ix_rag_chunks_search_vector',
                        'ix_rag_chunks_embedding_hnsw_128',
                        'ix_rag_chunks_embedding_hnsw_768',
                        'ix_global_chunks_search_vector',
                        'ix_global_chunks_embedding_hnsw_128',
                        'ix_global_chunks_embedding_hnsw_768'
                    )
                    """
                )
            ).scalars()
        }
        active_artifact_index = connection.execute(
            text(
                """
                SELECT indexdef
                FROM pg_indexes
                WHERE schemaname = 'public'
                  AND indexname = 'uq_rag_learning_artifacts_one_active'
                """
            )
        ).scalar_one()
    assert "latency_ms" in query_columns
    assert {
        "method",
        "routing_reasons",
        "applied_filters",
        "structured_result",
    }.issubset(query_columns)
    assert {
        "expected_source_refs",
        "hard_negative_source_refs",
        "expected_method",
        "expected_filters",
        "source_feedback_id",
        "curated_by_id",
        "curated_at",
        "deactivation_reason",
        "case_origin",
        "failure_reasons",
        "severity",
        "tags",
        "baseline_snapshot",
        "baseline_captured_at",
        "source_query_id",
    }.issubset(evaluation_question_columns)
    assert {
        "routing_accuracy",
        "filter_accuracy",
        "hard_negative_rate",
    }.issubset(evaluation_run_columns)
    assert "learning_artifacts" in query_columns
    assert {"output_validation", "output_validation_enforced"}.issubset(query_columns)
    security_columns = {
        "security_status",
        "security_action",
        "security_score",
        "security_categories",
        "security_signals",
        "security_policy_version",
        "security_detector_version",
        "security_classifier",
        "security_content_checksum",
        "security_scanned_at",
        "security_error_code",
    }
    assert security_columns.issubset(private_version_columns)
    assert security_columns.issubset(operational_source_columns)
    assert security_columns.issubset(feedback_columns)
    assert security_columns.issubset(global_version_columns)
    quarantine_columns = {
        "security_quarantined_at",
        "security_purged_at",
        "security_review_decision",
        "security_review_checksum",
        "security_reviewed_by_id",
        "security_reviewed_at",
        "security_review_reason",
    }
    assert quarantine_columns.issubset(private_version_columns)
    assert quarantine_columns.issubset(global_version_columns)
    malware_columns = {
        "malware_scan_status",
        "malware_scan_provider",
        "malware_engine_version",
        "malware_signature_version",
        "malware_threat",
        "malware_scan_error_code",
        "malware_scanned_at",
    }
    assert malware_columns.issubset(private_version_columns)
    assert malware_columns.issubset(global_version_columns)
    encryption_columns = {
        "encryption_key_version",
        "encryption_algorithm",
        "encrypted_at",
    }
    assert encryption_columns.issubset(private_version_columns)
    assert encryption_columns.issubset(global_version_columns)
    assert encryption_columns.issubset(attachment_columns)
    assert {
        "scan_provider",
        "scan_engine_version",
        "scan_signature_version",
        "scan_threat",
        "scan_error_code",
        "scanned_at",
    }.issubset(attachment_columns)
    assert {
        "tenant_id",
        "scope",
        "status",
        "phase",
        "cursor_id",
        "cutoff_at",
        "policy_version",
        "signature_version",
        "total_targets",
        "processed_targets",
        "purged_chunks",
        "purged_ocr",
        "purged_transcriptions",
    }.issubset(rescan_columns)
    assert {
        "evaluation_details",
        "activated_by_id",
        "activation_mode",
        "rollout_percentage",
        "rollout_state",
        "rollout_stage_index",
        "rollout_started_at",
        "rollout_stage_started_at",
        "rollout_next_check_at",
        "rollout_history",
        "online_metrics",
    }.issubset(learning_artifact_columns)
    assert "UNIQUE INDEX" in active_artifact_index
    assert "status" in active_artifact_index
    assert "ATIVO" in active_artifact_index
    assert "processing_duration_ms" in outbox_columns
    assert {
        "ix_outbox_events_claim_ready",
        "ix_outbox_events_event_claim_ready",
    }.issubset(outbox_indexes)
    assert {"embedding_vector", "search_vector"}.issubset(rag_chunk_columns)
    assert {"embedding_vector", "search_vector"}.issubset(global_chunk_columns)
    assert vector_extension
    assert hybrid_indexes == {
        "public.ix_rag_chunks_search_vector",
        "public.ix_rag_chunks_embedding_hnsw_128",
        "public.ix_rag_chunks_embedding_hnsw_768",
        "rag_global.ix_global_chunks_search_vector",
        "rag_global.ix_global_chunks_embedding_hnsw_128",
        "rag_global.ix_global_chunks_embedding_hnsw_768",
    }
    with postgres_app.app_context(), db.engine.connect() as connection:
        runtime_global_access = connection.execute(
            text(
                """
                SELECT
                    has_schema_privilege('gabflow_app', 'rag_global', 'USAGE'),
                    has_table_privilege(
                        'gabflow_app',
                        'rag_global.chunks',
                        'SELECT'
                    ),
                    has_table_privilege(
                        'gabflow_worker',
                        'rag_global.tenant_published_chunks',
                        'SELECT'
                    )
                """
            )
        ).one()
    assert runtime_global_access == (True, True, True)


def test_global_catalog_schema_and_outbox_boundary(postgres_app):
    with postgres_app.app_context(), db.engine.connect() as connection:
        role_labels = connection.execute(
            text(
                """
                SELECT enumlabel
                FROM pg_enum
                JOIN pg_type ON pg_type.oid = pg_enum.enumtypid
                WHERE pg_type.typname = 'user_role'
                """
            )
        ).scalars()
        outbox_tenant = next(
            column
            for column in inspect(connection).get_columns("outbox_events")
            if column["name"] == "tenant_id"
        )
        storage_check = connection.execute(
            text(
                """
                SELECT pg_get_constraintdef(oid)
                FROM pg_constraint
                WHERE contype = 'c'
                  AND conrelid = 'rag_global.document_versions'::regclass
                  AND pg_get_constraintdef(oid) LIKE '%global/rag/%'
                """
            )
        ).scalar_one()
        entitlement_security = connection.execute(
            text(
                """
                SELECT relrowsecurity, relforcerowsecurity
                FROM pg_class
                WHERE oid = 'public.rag_global_entitlements'::regclass
                """
            )
        ).one()
        policy_expression = connection.execute(
            text(
                """
                SELECT qual::text || ' ' || with_check::text
                FROM pg_policies
                WHERE schemaname = 'public'
                  AND tablename = 'rag_global_entitlements'
                """
            )
        ).scalar_one()
        view_options = connection.execute(
            text(
                """
                SELECT reloptions
                FROM pg_class
                WHERE oid = 'rag_global.tenant_published_chunks'::regclass
                """
            )
        ).scalar_one()

    assert "GLOBAL_KNOWLEDGE_ADMIN" in set(role_labels)
    assert outbox_tenant["nullable"] is True
    assert "global/rag/" in storage_check
    assert entitlement_security == (True, True)
    assert "app.tenant_id" in policy_expression
    assert "app.global_knowledge_admin" in policy_expression
    assert "security_barrier=true" in view_options


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
        request_statuses = (
            connection.execute(enum_query, {"enum_name": "request_status"}).scalars().all()
        )
        notification_types = (
            connection.execute(enum_query, {"enum_name": "notification_type"}).scalars().all()
        )
        tramitation_statuses = (
            connection.execute(enum_query, {"enum_name": "legislative_tramitation_status"})
            .scalars()
            .all()
        )
        operational_source_statuses = (
            connection.execute(enum_query, {"enum_name": "rag_knowledge_source_status"})
            .scalars()
            .all()
        )
        feedback_statuses = (
            connection.execute(enum_query, {"enum_name": "rag_feedback_status"}).scalars().all()
        )
        feedback_judgments = (
            connection.execute(enum_query, {"enum_name": "rag_feedback_source_judgment"})
            .scalars()
            .all()
        )
        learning_artifact_types = (
            connection.execute(enum_query, {"enum_name": "rag_learning_artifact_type"})
            .scalars()
            .all()
        )

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
    assert set(operational_source_statuses) == {
        "PENDENTE",
        "ATIVA",
        "QUARENTENA",
        "INELEGIVEL",
        "EXPIRADA",
        "ERRO",
        "EXCLUIDA",
    }
    assert feedback_statuses == [
        "PENDENTE_REVISAO",
        "APROVADO",
        "QUARENTENA",
        "REJEITADO",
        "REVOGADO",
        "SUPERADO",
    ]
    assert feedback_judgments == ["RELEVANTE", "IRRELEVANTE", "AUSENTE"]
    assert learning_artifact_types == [
        "RERANK_PROFILE",
        "ROUTING_EXAMPLES",
        "EVALUATION_CASES",
        "ANSWER_EXEMPLARS",
        "QUALITY_PROFILE",
    ]


def test_electoral_private_rls_and_official_geometry_index(postgres_app):
    private_tables = {
        "electoral_identity_reviews",
        "electoral_favorites",
        "electoral_saved_comparisons",
    }
    with postgres_app.app_context(), db.engine.connect() as connection:
        policies = {
            row.table_name: (row.rls_enabled, row.rls_forced, row.expression)
            for row in connection.execute(
                text(
                    """
                    SELECT c.relname AS table_name,
                           c.relrowsecurity AS rls_enabled,
                           c.relforcerowsecurity AS rls_forced,
                           COALESCE(p.qual, '') || ' ' || COALESCE(p.with_check, '') AS expression
                    FROM pg_class c
                    JOIN pg_namespace n ON n.oid = c.relnamespace
                    JOIN pg_policies p ON p.schemaname = n.nspname AND p.tablename = c.relname
                    WHERE n.nspname = 'public' AND c.relname = ANY(:tables)
                    """
                ),
                {"tables": list(private_tables)},
            )
        }
        commitment_policy_commands = {
            row.tablename: set(row.commands)
            for row in connection.execute(
                text(
                    """
                    SELECT tablename, array_agg(cmd ORDER BY cmd) AS commands
                    FROM pg_policies
                    WHERE schemaname = 'public'
                      AND tablename = ANY(:tables)
                    GROUP BY tablename
                    """
                ),
                {
                    "tables": [
                        "electoral_public_commitments",
                        "electoral_commitment_evidence",
                        "electoral_commitment_history",
                    ]
                },
            )
        }
        geometry_type = connection.execute(
            text(
                """
                SELECT type, srid
                FROM geometry_columns
                WHERE f_table_name = 'electoral_geometry_features'
                  AND f_geometry_column = 'geometry'
                """
            )
        ).one()
        geometry_index = connection.scalar(
            text(
                """
                SELECT indexdef FROM pg_indexes
                WHERE tablename = 'electoral_geometry_features'
                  AND indexname = 'ix_electoral_geometry_features_geometry_gist'
                """
            )
        )

    assert set(policies) == private_tables
    assert all(enabled and forced for enabled, forced, _ in policies.values())
    assert all("app.tenant_id" in expression for _, _, expression in policies.values())
    assert commitment_policy_commands == {
        "electoral_public_commitments": {"SELECT", "INSERT", "UPDATE"},
        "electoral_commitment_evidence": {"SELECT", "INSERT"},
        "electoral_commitment_history": {"SELECT", "INSERT"},
    }
    assert all("app.user_id" in expression for _, _, expression in policies.values())
    assert geometry_type == ("MULTIPOLYGON", 4326)
    assert "using gist" in geometry_index.lower()


def test_electoral_export_tables_use_forced_tenant_rls(postgres_app):
    export_tables = {
        "electoral_report_jobs",
        "electoral_generated_reports",
        "electoral_coverage_profiles",
        "electoral_mandate_snapshots",
        "electoral_public_commitments",
        "electoral_commitment_evidence",
        "electoral_commitment_history",
    }
    with postgres_app.app_context(), db.engine.connect() as connection:
        policies = {
            row.table_name: (row.rls_enabled, row.rls_forced, row.expression)
            for row in connection.execute(
                text(
                    """
                    SELECT c.relname AS table_name,
                           c.relrowsecurity AS rls_enabled,
                           c.relforcerowsecurity AS rls_forced,
                           COALESCE(p.qual, '') || ' ' || COALESCE(p.with_check, '') AS expression
                    FROM pg_class c
                    JOIN pg_namespace n ON n.oid = c.relnamespace
                    JOIN pg_policies p ON p.schemaname = n.nspname AND p.tablename = c.relname
                    WHERE n.nspname = 'public' AND c.relname = ANY(:tables)
                    """
                ),
                {"tables": list(export_tables)},
            )
        }
    assert set(policies) == export_tables
    assert all(enabled and forced for enabled, forced, _ in policies.values())
    assert all("app.tenant_id" in expression for _, _, expression in policies.values())


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

        location = (
            db.session.execute(
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
            )
            .mappings()
            .one()
        )

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
            rolled_back_heads = set(MigrationContext.configure(connection).get_current_heads())
            inspector = inspect(connection)
            rolled_back_tables = set(inspector.get_table_names())
            rolled_back_service_columns = {
                column["name"] for column in inspector.get_columns("service_requests")
            }
            rolled_back_tenant_columns = {
                column["name"] for column in inspector.get_columns("tenants")
            }
            rolled_back_external_agency_columns = {
                column["name"] for column in inspector.get_columns("external_agencies")
            }
            rolled_back_query_columns = {
                column["name"] for column in inspector.get_columns("rag_assistant_queries")
            }
            rolled_back_outbox_columns = {
                column["name"] for column in inspector.get_columns("outbox_events")
            }
            rolled_back_source_columns = {
                column["name"] for column in inspector.get_columns("rag_knowledge_sources")
            }
            rolled_back_private_version_columns = {
                column["name"] for column in inspector.get_columns("rag_document_versions")
            }
            rolled_back_attachment_columns = {
                column["name"] for column in inspector.get_columns("attachments")
            }
            rolled_back_feedback_columns = {
                column["name"] for column in inspector.get_columns("rag_query_feedback")
            }
            rolled_back_global_version_columns = {
                column["name"]
                for column in inspector.get_columns("document_versions", schema="rag_global")
            }
            rolled_back_evaluation_columns = {
                column["name"] for column in inspector.get_columns("rag_evaluation_questions")
            }
            rolled_back_evaluation_run_columns = {
                column["name"] for column in inspector.get_columns("rag_evaluation_runs")
            }
            rolled_back_learning_artifact_columns = {
                column["name"] for column in inspector.get_columns("rag_learning_artifacts")
            }
            rolled_back_chunk_columns = {
                column["name"] for column in inspector.get_columns("rag_chunks")
            }
            rls_policies = connection.execute(
                text(
                    """
                    SELECT count(*) FROM pg_policies
                    WHERE schemaname = 'public' AND tablename LIKE 'rag_%'
                    """
                )
            ).scalar_one()

        assert rolled_back_heads == {previous_head}
        assert "political_parties" in rolled_back_tables
        assert "legislative_drafts" in rolled_back_tables
        assert "legislative_tramitations" in rolled_back_tables
        assert "normative_sources" in rolled_back_tables
        assert "rag_documents" in rolled_back_tables
        assert "rag_document_versions" in rolled_back_tables
        assert "rag_chunks" in rolled_back_tables
        assert "rag_assistant_queries" in rolled_back_tables
        assert "rag_knowledge_sources" in rolled_back_tables
        assert "rag_query_feedback" in rolled_back_tables
        assert "rag_feedback_source_judgments" in rolled_back_tables
        assert "rag_learning_runs" in rolled_back_tables
        assert "rag_learning_artifacts" in rolled_back_tables
        assert "rag_learning_artifact_feedback" in rolled_back_tables
        assert "learning_artifacts" in rolled_back_query_columns
        assert "activation_mode" in rolled_back_learning_artifact_columns
        assert "source_feedback_id" in rolled_back_evaluation_columns
        assert "case_origin" in rolled_back_evaluation_columns
        assert "source_query_id" in rolled_back_evaluation_columns
        assert "rollout_state" in rolled_back_learning_artifact_columns
        assert "rollout_history" in rolled_back_learning_artifact_columns
        assert "security_status" in rolled_back_private_version_columns
        assert "security_status" in rolled_back_source_columns
        assert "security_status" in rolled_back_feedback_columns
        assert "security_status" in rolled_back_global_version_columns
        assert "security_quarantined_at" in rolled_back_private_version_columns
        assert "security_quarantined_at" in rolled_back_global_version_columns
        assert "malware_scan_status" in rolled_back_private_version_columns
        assert "malware_scan_status" in rolled_back_global_version_columns
        assert "scan_provider" in rolled_back_attachment_columns
        assert "rag_security_rescan_runs" in rolled_back_tables
        assert "rag_output_validation_profiles" in rolled_back_tables
        assert "rls_audit_runs" in rolled_back_tables
        assert "electoral_coverage_profiles" in rolled_back_tables
        assert "electoral_mandate_snapshots" in rolled_back_tables
        assert "electoral_public_commitments" not in rolled_back_tables
        assert "electoral_commitment_evidence" not in rolled_back_tables
        assert "electoral_commitment_history" not in rolled_back_tables
        assert "encryption_key_version" in rolled_back_private_version_columns
        assert "encryption_key_version" in rolled_back_global_version_columns
        assert "encryption_key_version" in rolled_back_attachment_columns
        assert "embedding_vector" in rolled_back_chunk_columns
        assert "search_vector" in rolled_back_chunk_columns
        assert "routing_accuracy" in rolled_back_evaluation_run_columns
        assert "location_geography" in rolled_back_service_columns
        assert "jurisdiction_name" in rolled_back_tenant_columns
        assert "jurisdiction_geojson" in rolled_back_tenant_columns
        assert "responsible" in rolled_back_external_agency_columns
        assert "phone" in rolled_back_external_agency_columns
        assert "source" in rolled_back_external_agency_columns
        assert "latency_ms" in rolled_back_query_columns
        assert "processing_duration_ms" in rolled_back_outbox_columns
        assert "tombstone_hash" in rolled_back_source_columns
        assert "purge_completed_at" in rolled_back_source_columns
        assert rls_policies == 16

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
            reapplied_external_agency_columns = {
                column["name"] for column in inspector.get_columns("external_agencies")
            }
            reapplied_query_columns = {
                column["name"] for column in inspector.get_columns("rag_assistant_queries")
            }
            reapplied_outbox_columns = {
                column["name"] for column in inspector.get_columns("outbox_events")
            }
            reapplied_source_columns = {
                column["name"] for column in inspector.get_columns("rag_knowledge_sources")
            }
            reapplied_private_version_columns = {
                column["name"] for column in inspector.get_columns("rag_document_versions")
            }
            reapplied_attachment_columns = {
                column["name"] for column in inspector.get_columns("attachments")
            }
            reapplied_feedback_columns = {
                column["name"] for column in inspector.get_columns("rag_query_feedback")
            }
            reapplied_global_version_columns = {
                column["name"]
                for column in inspector.get_columns("document_versions", schema="rag_global")
            }
            reapplied_evaluation_columns = {
                column["name"] for column in inspector.get_columns("rag_evaluation_questions")
            }
            reapplied_evaluation_run_columns = {
                column["name"] for column in inspector.get_columns("rag_evaluation_runs")
            }
            reapplied_learning_artifact_columns = {
                column["name"] for column in inspector.get_columns("rag_learning_artifacts")
            }
            reapplied_chunk_columns = {
                column["name"] for column in inspector.get_columns("rag_chunks")
            }
            political_parties_count = connection.execute(
                text("SELECT count(*) FROM political_parties")
            ).scalar_one()
            pt_number = connection.execute(
                text("SELECT ballot_number FROM political_parties WHERE acronym = 'PT'")
            ).scalar_one()

        assert reapplied_heads == {expected_head}
        assert "political_parties" in reapplied_tables
        assert "legislative_drafts" in reapplied_tables
        assert "legislative_tramitations" in reapplied_tables
        assert "normative_sources" in reapplied_tables
        assert "rag_documents" in reapplied_tables
        assert "rag_document_versions" in reapplied_tables
        assert "rag_chunks" in reapplied_tables
        assert "rag_assistant_queries" in reapplied_tables
        assert "rag_knowledge_sources" in reapplied_tables
        assert "rag_query_feedback" in reapplied_tables
        assert "rag_feedback_source_judgments" in reapplied_tables
        assert "rag_learning_runs" in reapplied_tables
        assert "rag_learning_artifacts" in reapplied_tables
        assert "rag_learning_artifact_feedback" in reapplied_tables
        assert "rag_security_rescan_runs" in reapplied_tables
        assert "rag_output_validation_profiles" in reapplied_tables
        assert "rls_audit_runs" in reapplied_tables
        assert "electoral_coverage_profiles" in reapplied_tables
        assert "electoral_mandate_snapshots" in reapplied_tables
        assert "electoral_public_commitments" in reapplied_tables
        assert "electoral_commitment_evidence" in reapplied_tables
        assert "electoral_commitment_history" in reapplied_tables
        assert "learning_artifacts" in reapplied_query_columns
        assert "activation_mode" in reapplied_learning_artifact_columns
        assert "security_status" in reapplied_private_version_columns
        assert "security_status" in reapplied_source_columns
        assert "security_status" in reapplied_feedback_columns
        assert "security_status" in reapplied_global_version_columns
        assert "security_quarantined_at" in reapplied_private_version_columns
        assert "security_review_decision" in reapplied_private_version_columns
        assert "security_quarantined_at" in reapplied_global_version_columns
        assert "security_review_decision" in reapplied_global_version_columns
        assert "malware_scan_status" in reapplied_private_version_columns
        assert "malware_scan_status" in reapplied_global_version_columns
        assert "scan_provider" in reapplied_attachment_columns
        assert "encryption_key_version" in reapplied_private_version_columns
        assert "encryption_key_version" in reapplied_global_version_columns
        assert "encryption_key_version" in reapplied_attachment_columns
        assert "source_feedback_id" in reapplied_evaluation_columns
        assert "hard_negative_source_refs" in reapplied_evaluation_columns
        assert "case_origin" in reapplied_evaluation_columns
        assert "baseline_snapshot" in reapplied_evaluation_columns
        assert "source_query_id" in reapplied_evaluation_columns
        assert "embedding_vector" in reapplied_chunk_columns
        assert "search_vector" in reapplied_chunk_columns
        assert "routing_accuracy" in reapplied_evaluation_run_columns
        assert "hard_negative_rate" in reapplied_evaluation_run_columns
        assert "location_geography" in reapplied_service_columns
        assert "jurisdiction_name" in reapplied_tenant_columns
        assert "jurisdiction_geojson" in reapplied_tenant_columns
        assert "responsible" in reapplied_external_agency_columns
        assert "phone" in reapplied_external_agency_columns
        assert "source" in reapplied_external_agency_columns
        assert "latency_ms" in reapplied_query_columns
        assert "processing_duration_ms" in reapplied_outbox_columns
        assert "tombstone_hash" in reapplied_source_columns
        assert "purge_completed_at" in reapplied_source_columns
        assert political_parties_count == 30
        assert pt_number == 13


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
