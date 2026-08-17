"""repair RAG global runtime permissions

Revision ID: e0a1b2c3d4e5
Revises: d9f0a1b2c3d4
"""

import os

import sqlalchemy as sa
from alembic import op


revision = "e0a1b2c3d4e5"
down_revision = "d9f0a1b2c3d4"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

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
    migrator = bind.execute(sa.text("SELECT current_user")).scalar_one()
    quoted_migrator = bind.dialect.identifier_preparer.quote_identifier(migrator)
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
        op.execute(
            f"ALTER DEFAULT PRIVILEGES FOR ROLE {quoted_migrator} "
            "IN SCHEMA rag_global GRANT SELECT, INSERT, UPDATE, DELETE "
            f"ON TABLES TO {quoted}"
        )
        op.execute(
            f"ALTER DEFAULT PRIVILEGES FOR ROLE {quoted_migrator} "
            "IN SCHEMA rag_global GRANT USAGE, SELECT "
            f"ON SEQUENCES TO {quoted}"
        )


def downgrade():
    # Permission repair is intentionally not revoked on downgrade because the
    # runtime roles require this access for earlier RAG migrations as well.
    pass
