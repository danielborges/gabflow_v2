"""RAG quality profile for calibrated rollout

Revision ID: a6c9e2f4b817
Revises: f3b8c1d6e204
Create Date: 2026-07-30 00:00:00
"""

from alembic import op

revision = "a6c9e2f4b817"
down_revision = "f3b8c1d6e204"
branch_labels = None
depends_on = None


def upgrade():
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute(
        "ALTER TYPE rag_learning_artifact_type "
        "ADD VALUE IF NOT EXISTS 'QUALITY_PROFILE'"
    )


def downgrade():
    # PostgreSQL não remove um valor de enum com segurança sem reconstruir o tipo.
    # Manter o valor é compatível com versões anteriores da aplicação.
    pass
