"""RAG security quarantine and review lifecycle

Revision ID: d5f9b2c7a314
Revises: c4e8a1f6d203
Create Date: 2026-07-31 14:00:00
"""

import sqlalchemy as sa
from alembic import op

revision = "d5f9b2c7a314"
down_revision = "c4e8a1f6d203"
branch_labels = None
depends_on = None

TARGETS = (
    ("rag_document_versions", None, "rag_document_versions"),
    ("document_versions", "rag_global", "rag_global_document_versions"),
)


def upgrade():
    for table, schema, prefix in TARGETS:
        op.add_column(
            table,
            sa.Column("security_quarantined_at", sa.DateTime(timezone=True)),
            schema=schema,
        )
        op.add_column(
            table,
            sa.Column("security_purged_at", sa.DateTime(timezone=True)),
            schema=schema,
        )
        op.add_column(
            table,
            sa.Column("security_review_decision", sa.String(length=20)),
            schema=schema,
        )
        op.add_column(
            table,
            sa.Column("security_review_checksum", sa.String(length=64)),
            schema=schema,
        )
        op.add_column(
            table,
            sa.Column("security_reviewed_by_id", sa.Uuid()),
            schema=schema,
        )
        op.add_column(
            table,
            sa.Column("security_reviewed_at", sa.DateTime(timezone=True)),
            schema=schema,
        )
        op.add_column(
            table,
            sa.Column("security_review_reason", sa.Text()),
            schema=schema,
        )
        op.create_check_constraint(
            f"ck_{prefix}_security_review_decision",
            table,
            "security_review_decision IN ('APPROVED', 'REJECTED')",
            schema=schema,
        )
        op.create_index(
            f"ix_{prefix}_security_quarantined_at",
            table,
            ["security_quarantined_at"],
            schema=schema,
        )
        op.create_index(
            f"ix_{prefix}_security_reviewed_by_id",
            table,
            ["security_reviewed_by_id"],
            schema=schema,
        )


def downgrade():
    for table, schema, prefix in reversed(TARGETS):
        op.drop_index(
            f"ix_{prefix}_security_reviewed_by_id",
            table_name=table,
            schema=schema,
        )
        op.drop_index(
            f"ix_{prefix}_security_quarantined_at",
            table_name=table,
            schema=schema,
        )
        op.drop_constraint(
            f"ck_{prefix}_security_review_decision",
            table,
            schema=schema,
            type_="check",
        )
        for column in (
            "security_review_reason",
            "security_reviewed_at",
            "security_reviewed_by_id",
            "security_review_checksum",
            "security_review_decision",
            "security_purged_at",
            "security_quarantined_at",
        ):
            op.drop_column(table, column, schema=schema)
