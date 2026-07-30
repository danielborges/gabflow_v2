"""RAG hybrid retrieval with PostgreSQL FTS and pgvector

Revision ID: f3b8c1d6e204
Revises: e2a4b7c9d105
Create Date: 2026-07-30 00:00:00
"""

# ruff: noqa: S608

import os

import sqlalchemy as sa
from alembic import op

revision = "f3b8c1d6e204"
down_revision = "e2a4b7c9d105"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    for table in ("public.rag_chunks", "rag_global.chunks"):
        op.execute(f"ALTER TABLE {table} ADD COLUMN embedding_vector vector")
        op.execute(  # noqa: S608
            f"""
            ALTER TABLE {table}
            ADD COLUMN search_vector tsvector
            GENERATED ALWAYS AS (
                to_tsvector(
                    'portuguese'::regconfig,
                    coalesce(content, '') || ' ' || coalesce(section, '')
                )
            ) STORED
            """
        )
        op.execute(  # noqa: S608
            f"""
            UPDATE {table}
            SET embedding_vector = embedding::text::vector
            WHERE json_typeof(embedding) = 'array'
              AND json_array_length(embedding) BETWEEN 1 AND 2000
            """
        )

    op.execute(
        """
        CREATE FUNCTION public.sync_rag_embedding_vector()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            IF NEW.embedding IS NULL
               OR json_typeof(NEW.embedding) <> 'array'
               OR json_array_length(NEW.embedding) NOT BETWEEN 1 AND 2000 THEN
                NEW.embedding_vector := NULL;
            ELSE
                NEW.embedding_vector := NEW.embedding::text::vector;
            END IF;
            RETURN NEW;
        EXCEPTION
            WHEN data_exception THEN
                NEW.embedding_vector := NULL;
                RETURN NEW;
        END
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_rag_chunks_embedding_vector
        BEFORE INSERT OR UPDATE OF embedding ON public.rag_chunks
        FOR EACH ROW EXECUTE FUNCTION public.sync_rag_embedding_vector()
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_global_chunks_embedding_vector
        BEFORE INSERT OR UPDATE OF embedding ON rag_global.chunks
        FOR EACH ROW EXECUTE FUNCTION public.sync_rag_embedding_vector()
        """
    )

    op.execute(
        """
        CREATE INDEX ix_rag_chunks_search_vector
        ON public.rag_chunks USING gin (search_vector)
        """
    )
    op.execute(
        """
        CREATE INDEX ix_global_chunks_search_vector
        ON rag_global.chunks USING gin (search_vector)
        """
    )
    for dimensions in (128, 768):
        op.execute(
            f"""
            CREATE INDEX ix_rag_chunks_embedding_hnsw_{dimensions}
            ON public.rag_chunks
            USING hnsw ((embedding_vector::vector({dimensions})) vector_cosine_ops)
            WHERE vector_dims(embedding_vector) = {dimensions}
            """
        )
        op.execute(
            f"""
            CREATE INDEX ix_global_chunks_embedding_hnsw_{dimensions}
            ON rag_global.chunks
            USING hnsw ((embedding_vector::vector({dimensions})) vector_cosine_ops)
            WHERE vector_dims(embedding_vector) = {dimensions}
            """
        )
    _grant_runtime_access()


def downgrade():
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    for dimensions in (768, 128):
        op.execute(
            f"DROP INDEX IF EXISTS rag_global.ix_global_chunks_embedding_hnsw_{dimensions}"
        )
        op.execute(
            f"DROP INDEX IF EXISTS public.ix_rag_chunks_embedding_hnsw_{dimensions}"
        )
    op.execute("DROP INDEX IF EXISTS rag_global.ix_global_chunks_search_vector")
    op.execute("DROP INDEX IF EXISTS public.ix_rag_chunks_search_vector")
    op.execute(
        "DROP TRIGGER IF EXISTS trg_global_chunks_embedding_vector "
        "ON rag_global.chunks"
    )
    op.execute(
        "DROP TRIGGER IF EXISTS trg_rag_chunks_embedding_vector "
        "ON public.rag_chunks"
    )
    op.execute("DROP FUNCTION IF EXISTS public.sync_rag_embedding_vector()")
    for table in ("rag_global.chunks", "public.rag_chunks"):
        op.execute(f"ALTER TABLE {table} DROP COLUMN IF EXISTS search_vector")
        op.execute(f"ALTER TABLE {table} DROP COLUMN IF EXISTS embedding_vector")
    op.execute("DROP EXTENSION IF EXISTS vector")


def _grant_runtime_access():
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
        op.execute(f"GRANT USAGE ON SCHEMA rag_global TO {quoted}")
        op.execute(
            "GRANT SELECT, INSERT, UPDATE, DELETE "
            f"ON ALL TABLES IN SCHEMA rag_global TO {quoted}"
        )
        op.execute(
            "GRANT USAGE, SELECT "
            f"ON ALL SEQUENCES IN SCHEMA rag_global TO {quoted}"
        )
