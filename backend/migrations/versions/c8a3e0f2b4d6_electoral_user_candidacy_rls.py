"""Enforce user isolation on electoral candidacies.

Revision ID: c8a3e0f2b4d6
Revises: b7f2d9e1a3c5
"""

from alembic import op

revision = "c8a3e0f2b4d6"
down_revision = "b7f2d9e1a3c5"
branch_labels = None
depends_on = None

TABLE = "electoral_user_candidacies"
POLICY = "electoral_user_candidacies_tenant_isolation"


def upgrade():
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute(f"DROP POLICY IF EXISTS {POLICY} ON {TABLE}")
    op.execute(
        f"""
        CREATE POLICY {POLICY} ON {TABLE} FOR ALL
        USING (
            tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
            AND user_id = NULLIF(current_setting('app.user_id', true), '')::uuid
        )
        WITH CHECK (
            tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
            AND user_id = NULLIF(current_setting('app.user_id', true), '')::uuid
        )
        """
    )


def downgrade():
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute(f"DROP POLICY IF EXISTS {POLICY} ON {TABLE}")
    op.execute(
        f"""
        CREATE POLICY {POLICY} ON {TABLE} FOR ALL
        USING (
            tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
        )
        WITH CHECK (
            tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
        )
        """
    )
