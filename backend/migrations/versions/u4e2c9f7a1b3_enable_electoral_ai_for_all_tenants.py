"""Enable electoral AI permanently for every tenant.

Revision ID: u4e2c9f7a1b3
Revises: t3d1b8f5a7c9
"""

from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

revision = "u4e2c9f7a1b3"
down_revision = "t3d1b8f5a7c9"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    tenants = sa.table("tenants", sa.column("id", sa.Uuid()))
    settings = sa.table(
        "electoral_module_settings",
        sa.column("tenant_id", sa.Uuid()),
        sa.column("privacy_threshold", sa.Integer()),
        sa.column("feature_flags", sa.JSON()),
        sa.column("updated_by_id", sa.Uuid()),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    existing = {
        row.tenant_id: dict(row.feature_flags or {})
        for row in bind.execute(
            sa.select(settings.c.tenant_id, settings.c.feature_flags)
        ).all()
    }
    now = datetime.now(UTC)
    for tenant_id in bind.execute(sa.select(tenants.c.id)).scalars():
        if tenant_id in existing:
            flags = {**existing[tenant_id], "ia": True}
            bind.execute(
                sa.update(settings)
                .where(settings.c.tenant_id == tenant_id)
                .values(feature_flags=flags, updated_at=now)
            )
        else:
            bind.execute(
                sa.insert(settings).values(
                    tenant_id=tenant_id,
                    privacy_threshold=10,
                    feature_flags={"ia": True},
                    updated_by_id=None,
                    updated_at=now,
                )
            )


def downgrade():
    # A capacidade passou a ser invariavel de produto. O downgrade estrutural nao deve
    # reintroduzir uma configuracao que desabilite IA em gabinetes existentes.
    pass
