"""hierarchical RAG retrieval

Revision ID: 3b7c9e1f5a82
Revises: 2a6b8d0e4f71
Create Date: 2026-07-24 22:00:00
"""

import os

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "3b7c9e1f5a82"
down_revision = "2a6b8d0e4f71"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    entitlement_status = sa.Enum(
        "ATIVA",
        "DESATIVADA",
        "REVOGADA",
        name="rag_global_entitlement_status",
    )
    update_mode = sa.Enum(
        "AUTOMATICA",
        "FIXADA",
        name="rag_global_update_mode",
    )
    entitlement_status.create(bind, checkfirst=True)
    update_mode.create(bind, checkfirst=True)

    op.create_table(
        "rag_global_entitlements",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("collection_id", sa.Uuid(), nullable=False),
        sa.Column(
            "status",
            postgresql.ENUM(name="rag_global_entitlement_status", create_type=False),
            nullable=False,
        ),
        sa.Column(
            "update_mode",
            postgresql.ENUM(name="rag_global_update_mode", create_type=False),
            nullable=False,
        ),
        sa.Column("pinned_version_id", sa.Uuid(), nullable=True),
        sa.Column("grant_source", sa.String(length=40), nullable=False),
        sa.Column("justification", sa.Text(), nullable=True),
        sa.Column("granted_by_id", sa.Uuid(), nullable=False),
        sa.Column("valid_from", sa.Date(), nullable=True),
        sa.Column("valid_until", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "(update_mode = 'AUTOMATICA' AND pinned_version_id IS NULL) "
            "OR (update_mode = 'FIXADA' AND pinned_version_id IS NOT NULL)",
            name="ck_rag_global_entitlements_update_mode",
        ),
        sa.CheckConstraint(
            "valid_until IS NULL OR valid_from IS NULL OR valid_until >= valid_from",
            name="ck_rag_global_entitlements_validity",
        ),
        sa.ForeignKeyConstraint(
            ["collection_id"],
            ["rag_global.collections.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["granted_by_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["pinned_version_id"],
            ["rag_global.document_versions.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "collection_id",
            name="uq_rag_global_entitlements_tenant_collection",
        ),
    )
    op.create_index(
        "ix_rag_global_entitlements_tenant_id",
        "rag_global_entitlements",
        ["tenant_id"],
    )
    op.create_index(
        "ix_rag_global_entitlements_collection_id",
        "rag_global_entitlements",
        ["collection_id"],
    )
    op.create_index(
        "ix_rag_global_entitlements_status",
        "rag_global_entitlements",
        ["status"],
    )
    op.create_index(
        "ix_rag_global_entitlements_pinned_version_id",
        "rag_global_entitlements",
        ["pinned_version_id"],
    )
    op.create_index(
        "ix_rag_global_entitlements_granted_by_id",
        "rag_global_entitlements",
        ["granted_by_id"],
    )
    op.create_index(
        "ix_rag_global_entitlements_created_at",
        "rag_global_entitlements",
        ["created_at"],
    )

    op.execute("ALTER TABLE rag_global_entitlements ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE rag_global_entitlements FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY rag_global_entitlements_isolation
        ON rag_global_entitlements
        FOR ALL
        USING (
            tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
            OR current_setting('app.global_knowledge_admin', true) = 'true'
        )
        WITH CHECK (
            tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
            OR current_setting('app.global_knowledge_admin', true) = 'true'
        )
        """
    )

    op.execute(
        """
        CREATE VIEW rag_global.tenant_published_chunks
        WITH (security_barrier = true)
        AS
        SELECT
            c.id AS chunk_id,
            c.version_id,
            d.collection_id,
            NULLIF(current_setting('app.tenant_id', true), '')::uuid AS tenant_id
        FROM rag_global.chunks c
        JOIN rag_global.document_versions v ON v.id = c.version_id
        JOIN rag_global.documents d ON d.id = v.document_id
        JOIN rag_global.collections col ON col.id = d.collection_id
        LEFT JOIN rag_global_entitlements e
          ON e.collection_id = col.id
         AND e.tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
        WHERE NULLIF(current_setting('app.tenant_id', true), '') IS NOT NULL
          AND col.status = 'PUBLICADA'
          AND v.ingestion_status = 'INDEXADO'
          AND (v.valid_from IS NULL OR v.valid_from <= CURRENT_DATE)
          AND (v.valid_until IS NULL OR v.valid_until >= CURRENT_DATE)
          AND col.distribution_policy <> 'PRIVADA_PLATAFORMA'
          AND (
            col.distribution_policy IN ('OBRIGATORIA', 'RESTRITA_JURISDICAO')
            OR (
              col.distribution_policy = 'PADRAO'
              AND (e.id IS NULL OR e.status = 'ATIVA')
            )
            OR (
              col.distribution_policy = 'OPCIONAL'
              AND e.status = 'ATIVA'
            )
            OR (
              col.distribution_policy = 'DIRECIONADA'
              AND e.status = 'ATIVA'
              AND e.grant_source = 'GLOBAL_GRANT'
            )
          )
          AND (
            e.id IS NULL
            OR (
              (e.valid_from IS NULL OR e.valid_from <= CURRENT_DATE)
              AND (e.valid_until IS NULL OR e.valid_until >= CURRENT_DATE)
            )
          )
          AND (
            (
              (e.update_mode IS NULL OR e.update_mode = 'AUTOMATICA')
              AND v.publication_status = 'PUBLICADA'
            )
            OR (
              e.update_mode = 'FIXADA'
              AND (
                (
                  e.pinned_version_id = v.id
                  AND v.publication_status IN ('PUBLICADA', 'SUBSTITUIDA')
                )
                OR (
                  v.publication_status = 'PUBLICADA'
                  AND NOT EXISTS (
                    SELECT 1
                    FROM rag_global.document_versions pinned
                    WHERE pinned.id = e.pinned_version_id
                      AND pinned.document_id = v.document_id
                  )
                )
              )
            )
          )
        """
    )
    _grant_runtime_access()


def downgrade():
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.execute("DROP VIEW IF EXISTS rag_global.tenant_published_chunks")
    op.execute("DROP POLICY IF EXISTS rag_global_entitlements_isolation ON rag_global_entitlements")
    op.execute("ALTER TABLE rag_global_entitlements NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE rag_global_entitlements DISABLE ROW LEVEL SECURITY")
    op.drop_table("rag_global_entitlements")
    sa.Enum(name="rag_global_update_mode").drop(bind, checkfirst=True)
    sa.Enum(name="rag_global_entitlement_status").drop(bind, checkfirst=True)


def _grant_runtime_access() -> None:
    bind = op.get_bind()
    roles = {
        os.getenv("APP_DB_USER", "gabflow_app"),
        os.getenv("WORKER_DB_USER", "gabflow_worker"),
    }
    available = {
        row[0]
        for row in bind.execute(
            sa.text("SELECT rolname FROM pg_roles WHERE rolname = ANY(:roles)"),
            {"roles": list(roles)},
        )
    }
    for role in roles & available:
        quoted = bind.dialect.identifier_preparer.quote_identifier(role)
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON rag_global_entitlements TO {quoted}")
        op.execute(f"GRANT SELECT ON rag_global.tenant_published_chunks TO {quoted}")
