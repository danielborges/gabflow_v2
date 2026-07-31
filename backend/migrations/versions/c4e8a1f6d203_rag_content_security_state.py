"""RAG unified content security state

Revision ID: c4e8a1f6d203
Revises: b7d3f1a8c942
Create Date: 2026-07-31 10:00:00
"""

import sqlalchemy as sa
from alembic import op

revision = "c4e8a1f6d203"
down_revision = "b7d3f1a8c942"
branch_labels = None
depends_on = None

TARGETS = (
    ("rag_document_versions", None, "rag_document_versions"),
    ("rag_knowledge_sources", None, "rag_knowledge_sources"),
    ("rag_query_feedback", None, "rag_query_feedback"),
    ("document_versions", "rag_global", "rag_global_document_versions"),
)


def upgrade():
    for table, schema, prefix in TARGETS:
        _add_security_columns(table, schema, prefix)


def downgrade():
    for table, schema, prefix in reversed(TARGETS):
        op.drop_index(
            f"ix_{prefix}_security_content_checksum",
            table_name=table,
            schema=schema,
        )
        op.drop_index(
            f"ix_{prefix}_security_status",
            table_name=table,
            schema=schema,
        )
        op.drop_constraint(
            f"ck_{prefix}_security_score",
            table,
            schema=schema,
            type_="check",
        )
        op.drop_constraint(
            f"ck_{prefix}_security_action",
            table,
            schema=schema,
            type_="check",
        )
        op.drop_constraint(
            f"ck_{prefix}_security_status",
            table,
            schema=schema,
            type_="check",
        )
        for column in reversed(_column_names()):
            op.drop_column(table, column, schema=schema)


def _add_security_columns(table: str, schema: str | None, prefix: str) -> None:
    columns = (
        sa.Column(
            "security_status",
            sa.String(length=20),
            nullable=False,
            server_default="INDETERMINATE",
        ),
        sa.Column(
            "security_action",
            sa.String(length=20),
            nullable=False,
            server_default="RETRY",
        ),
        sa.Column(
            "security_score",
            sa.Float(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "security_categories",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
        sa.Column(
            "security_signals",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
        sa.Column(
            "security_policy_version",
            sa.String(length=80),
            nullable=False,
            server_default="legacy-unassessed",
        ),
        sa.Column("security_detector_version", sa.String(length=80)),
        sa.Column(
            "security_classifier",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.Column("security_content_checksum", sa.String(length=64)),
        sa.Column("security_scanned_at", sa.DateTime(timezone=True)),
        sa.Column("security_error_code", sa.String(length=80)),
    )
    for column in columns:
        op.add_column(table, column, schema=schema)
    op.create_check_constraint(
        f"ck_{prefix}_security_status",
        table,
        "security_status IN ('CLEAN', 'SUSPICIOUS', 'MALICIOUS', 'INDETERMINATE')",
        schema=schema,
    )
    op.create_check_constraint(
        f"ck_{prefix}_security_action",
        table,
        "security_action IN ('ALLOW', 'QUARANTINE', 'BLOCK', 'RETRY')",
        schema=schema,
    )
    op.create_check_constraint(
        f"ck_{prefix}_security_score",
        table,
        "security_score >= 0 AND security_score <= 1",
        schema=schema,
    )
    op.create_index(
        f"ix_{prefix}_security_status",
        table,
        ["security_status"],
        schema=schema,
    )
    op.create_index(
        f"ix_{prefix}_security_content_checksum",
        table,
        ["security_content_checksum"],
        schema=schema,
    )


def _column_names() -> tuple[str, ...]:
    return (
        "security_status",
        "security_action",
        "security_score",
        "security_categories",
        "security_signals",
        "security_policy_version",
        "security_detector_version",
        "security_classifier",
        "security_content_checksum",
        "security_scanned_at",
        "security_error_code",
    )
