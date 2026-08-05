"""Backfill electoral coverage metadata for constant-time catalog reads.

Revision ID: v5f3d0a8b2c4
Revises: u4e2c9f7a1b3
"""

import sqlalchemy as sa
from alembic import op

revision = "v5f3d0a8b2c4"
down_revision = "u4e2c9f7a1b3"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    datasets = sa.table(
        "electoral_dataset_versions",
        sa.column("id", sa.Uuid()),
        sa.column("validation_manifest", sa.JSON()),
    )
    candidacies = sa.table(
        "electoral_candidacies",
        sa.column("dataset_version_id", sa.Uuid()),
        sa.column("office_id", sa.Uuid()),
    )
    offices = sa.table(
        "electoral_offices",
        sa.column("id", sa.Uuid()),
        sa.column("code", sa.String()),
    )
    territories = sa.table(
        "electoral_territories",
        sa.column("dataset_version_id", sa.Uuid()),
        sa.column("level", sa.String()),
    )

    for dataset_id, current_manifest in bind.execute(
        sa.select(datasets.c.id, datasets.c.validation_manifest)
    ):
        office_codes = sorted(
            set(
                bind.execute(
                    sa.select(offices.c.code)
                    .join(candidacies, candidacies.c.office_id == offices.c.id)
                    .where(candidacies.c.dataset_version_id == dataset_id)
                ).scalars()
            ),
            key=int,
        )
        source_levels = {
            str(level).lower()
            for level in (
            bind.execute(
                sa.select(territories.c.level).where(
                    territories.c.dataset_version_id == dataset_id
                )
            ).scalars()
            )
        }
        if not office_codes and not source_levels:
            continue
        granularities = source_levels | ({"municipality"} if source_levels else set())
        manifest = {
            **(current_manifest or {}),
            "officeCodes": office_codes,
            "granularities": sorted(granularities),
        }
        bind.execute(
            sa.update(datasets)
            .where(datasets.c.id == dataset_id)
            .values(validation_manifest=manifest)
        )


def downgrade():
    bind = op.get_bind()
    datasets = sa.table(
        "electoral_dataset_versions",
        sa.column("id", sa.Uuid()),
        sa.column("validation_manifest", sa.JSON()),
    )
    for dataset_id, current_manifest in bind.execute(
        sa.select(datasets.c.id, datasets.c.validation_manifest)
    ):
        manifest = dict(current_manifest or {})
        manifest.pop("officeCodes", None)
        manifest.pop("granularities", None)
        bind.execute(
            sa.update(datasets)
            .where(datasets.c.id == dataset_id)
            .values(validation_manifest=manifest)
        )
