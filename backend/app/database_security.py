from flask import current_app
from sqlalchemy import text

from app.extensions import db


class UnsafeDatabaseRoleError(RuntimeError):
    pass


def assert_runtime_database_role() -> None:
    if current_app.config.get("TESTING") or not current_app.config["DB_ENFORCE_RUNTIME_ROLE"]:
        return
    if db.engine.dialect.name != "postgresql":
        return
    if current_app.extensions.get("runtime_database_role_validated"):
        return

    attributes = db.session.execute(
        text(
            """
            SELECT
                current_user,
                rolsuper,
                rolbypassrls,
                EXISTS (
                    SELECT 1
                    FROM pg_class
                    WHERE relname = ANY(:rag_tables)
                      AND relowner = (SELECT oid FROM pg_roles WHERE rolname = current_user)
                ) AS owns_rag_table
            FROM pg_roles
            WHERE rolname = current_user
            """
        ),
        {
            "rag_tables": [
                "rag_assistant_queries",
                "rag_chunks",
                "rag_document_versions",
                "rag_documents",
                "rag_global_entitlements",
                "rag_knowledge_sources",
                "rag_learning_artifact_feedback",
                "rag_learning_artifacts",
                "rag_learning_runs",
            ]
        },
    ).one()
    role_name, is_superuser, bypasses_rls, owns_rag_table = attributes
    if is_superuser or bypasses_rls or owns_rag_table:
        raise UnsafeDatabaseRoleError(
            f"Role PostgreSQL insegura para runtime: {role_name}. "
            "Use uma role NOSUPERUSER, NOBYPASSRLS e não proprietária das tabelas RAG."
        )
    current_app.extensions["runtime_database_role_validated"] = True
