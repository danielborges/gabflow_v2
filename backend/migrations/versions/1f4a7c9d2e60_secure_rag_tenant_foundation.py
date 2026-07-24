"""secure RAG tenant foundation

Revision ID: 1f4a7c9d2e60
Revises: 0d7a8b9c1e23
Create Date: 2026-07-24 18:00:00
"""

import sqlalchemy as sa
from alembic import op

revision = "1f4a7c9d2e60"
down_revision = "0d7a8b9c1e23"
branch_labels = None
depends_on = None

RAG_TABLES = (
    "rag_documents",
    "rag_document_versions",
    "rag_chunks",
    "rag_assistant_queries",
)


def upgrade():
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    _validate_existing_tenant_links()

    op.create_unique_constraint("uq_users_tenant_id_id", "users", ["tenant_id", "id"])
    op.create_unique_constraint(
        "uq_rag_documents_tenant_id_id", "rag_documents", ["tenant_id", "id"]
    )
    op.create_unique_constraint(
        "uq_rag_document_versions_tenant_id_id",
        "rag_document_versions",
        ["tenant_id", "id"],
    )

    _drop_foreign_keys("rag_documents", {"created_by_id"})
    _drop_foreign_keys("rag_document_versions", {"document_id"})
    _drop_foreign_keys("rag_document_versions", {"created_by_id"})
    _drop_foreign_keys("rag_chunks", {"version_id"})
    _drop_foreign_keys("rag_assistant_queries", {"user_id"})
    _drop_foreign_keys("rag_assistant_queries", {"reviewed_by_id"})

    op.create_foreign_key(
        "fk_rag_documents_tenant_creator",
        "rag_documents",
        "users",
        ["tenant_id", "created_by_id"],
        ["tenant_id", "id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_rag_document_versions_tenant_document",
        "rag_document_versions",
        "rag_documents",
        ["tenant_id", "document_id"],
        ["tenant_id", "id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_rag_document_versions_tenant_creator",
        "rag_document_versions",
        "users",
        ["tenant_id", "created_by_id"],
        ["tenant_id", "id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_rag_chunks_tenant_version",
        "rag_chunks",
        "rag_document_versions",
        ["tenant_id", "version_id"],
        ["tenant_id", "id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_rag_assistant_queries_tenant_user",
        "rag_assistant_queries",
        "users",
        ["tenant_id", "user_id"],
        ["tenant_id", "id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_rag_assistant_queries_tenant_reviewer",
        "rag_assistant_queries",
        "users",
        ["tenant_id", "reviewed_by_id"],
        ["tenant_id", "id"],
        ondelete="RESTRICT",
    )

    op.create_check_constraint(
        "ck_rag_document_versions_storage_namespace",
        "rag_document_versions",
        """
        storage_key LIKE (
            'tenants/' || tenant_id::text || '/rag/' || document_id::text || '/' || id::text || '/%'
        )
        OR storage_key LIKE (tenant_id::text || '/' || id::text || '-%')
        """,
    )

    for table in RAG_TABLES:
        op.execute(sa.text(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY'))
        op.execute(sa.text(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY'))
        op.execute(
            sa.text(
                f"""
                CREATE POLICY {table}_tenant_isolation ON "{table}"
                FOR ALL
                USING (
                    tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
                )
                WITH CHECK (
                    tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
                )
                """
            )
        )


def downgrade():
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    for table in reversed(RAG_TABLES):
        op.execute(sa.text(f'DROP POLICY IF EXISTS {table}_tenant_isolation ON "{table}"'))
        op.execute(sa.text(f'ALTER TABLE "{table}" NO FORCE ROW LEVEL SECURITY'))
        op.execute(sa.text(f'ALTER TABLE "{table}" DISABLE ROW LEVEL SECURITY'))

    op.drop_constraint(
        "ck_rag_document_versions_storage_namespace",
        "rag_document_versions",
        type_="check",
    )
    op.drop_constraint(
        "fk_rag_assistant_queries_tenant_reviewer",
        "rag_assistant_queries",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_rag_assistant_queries_tenant_user",
        "rag_assistant_queries",
        type_="foreignkey",
    )
    op.drop_constraint("fk_rag_chunks_tenant_version", "rag_chunks", type_="foreignkey")
    op.drop_constraint(
        "fk_rag_document_versions_tenant_creator",
        "rag_document_versions",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_rag_document_versions_tenant_document",
        "rag_document_versions",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_rag_documents_tenant_creator", "rag_documents", type_="foreignkey"
    )

    op.create_foreign_key(
        "fk_rag_documents_created_by_id_users",
        "rag_documents",
        "users",
        ["created_by_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_rag_document_versions_document_id_rag_documents",
        "rag_document_versions",
        "rag_documents",
        ["document_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_rag_document_versions_created_by_id_users",
        "rag_document_versions",
        "users",
        ["created_by_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_rag_chunks_version_id_rag_document_versions",
        "rag_chunks",
        "rag_document_versions",
        ["version_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_rag_assistant_queries_user_id_users",
        "rag_assistant_queries",
        "users",
        ["user_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_rag_assistant_queries_reviewed_by_id_users",
        "rag_assistant_queries",
        "users",
        ["reviewed_by_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.drop_constraint(
        "uq_rag_document_versions_tenant_id_id",
        "rag_document_versions",
        type_="unique",
    )
    op.drop_constraint(
        "uq_rag_documents_tenant_id_id", "rag_documents", type_="unique"
    )
    op.drop_constraint("uq_users_tenant_id_id", "users", type_="unique")


def _drop_foreign_keys(table_name: str, constrained_columns: set[str]) -> None:
    inspector = sa.inspect(op.get_bind())
    for foreign_key in inspector.get_foreign_keys(table_name):
        if set(foreign_key["constrained_columns"]) == constrained_columns:
            op.drop_constraint(foreign_key["name"], table_name, type_="foreignkey")


def _validate_existing_tenant_links() -> None:
    checks = {
        "rag_documents.created_by_id": """
            SELECT 1 FROM rag_documents d
            JOIN users u ON u.id = d.created_by_id
            WHERE u.tenant_id IS DISTINCT FROM d.tenant_id LIMIT 1
        """,
        "rag_document_versions.document_id": """
            SELECT 1 FROM rag_document_versions v
            JOIN rag_documents d ON d.id = v.document_id
            WHERE d.tenant_id IS DISTINCT FROM v.tenant_id LIMIT 1
        """,
        "rag_document_versions.created_by_id": """
            SELECT 1 FROM rag_document_versions v
            JOIN users u ON u.id = v.created_by_id
            WHERE u.tenant_id IS DISTINCT FROM v.tenant_id LIMIT 1
        """,
        "rag_chunks.version_id": """
            SELECT 1 FROM rag_chunks c
            JOIN rag_document_versions v ON v.id = c.version_id
            WHERE v.tenant_id IS DISTINCT FROM c.tenant_id LIMIT 1
        """,
        "rag_assistant_queries.user_id": """
            SELECT 1 FROM rag_assistant_queries q
            JOIN users u ON u.id = q.user_id
            WHERE u.tenant_id IS DISTINCT FROM q.tenant_id LIMIT 1
        """,
        "rag_assistant_queries.reviewed_by_id": """
            SELECT 1 FROM rag_assistant_queries q
            JOIN users u ON u.id = q.reviewed_by_id
            WHERE q.reviewed_by_id IS NOT NULL
              AND u.tenant_id IS DISTINCT FROM q.tenant_id LIMIT 1
        """,
    }
    connection = op.get_bind()
    invalid = [
        label for label, statement in checks.items() if connection.execute(sa.text(statement)).first()
    ]
    if invalid:
        raise RuntimeError(
            "Não é possível ativar isolamento composto; vínculos cruzados encontrados: "
            + ", ".join(invalid)
        )
