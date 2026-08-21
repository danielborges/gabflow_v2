"""Add conversations to RAG assistant queries.

Revision ID: b3d5e7f9a1c2
Revises: a2c4e6f8b0d1
"""

import sqlalchemy as sa
from alembic import op


revision = "b3d5e7f9a1c2"
down_revision = "a2c4e6f8b0d1"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("rag_assistant_queries") as batch_op:
        batch_op.add_column(sa.Column("conversation_id", sa.Uuid()))
        batch_op.add_column(
            sa.Column("turn_index", sa.Integer(), server_default="1", nullable=False)
        )
        batch_op.add_column(
            sa.Column(
                "context_query_ids",
                sa.JSON(),
                server_default=sa.text("'[]'"),
                nullable=False,
            )
        )

    op.execute("UPDATE rag_assistant_queries SET conversation_id = id")
    with op.batch_alter_table("rag_assistant_queries") as batch_op:
        batch_op.alter_column("conversation_id", nullable=False)
        batch_op.create_index(
            "ix_rag_assistant_queries_conversation_id", ["conversation_id"]
        )
        batch_op.create_unique_constraint(
            "uq_rag_assistant_queries_conversation_turn",
            ["tenant_id", "conversation_id", "turn_index"],
        )


def downgrade():
    with op.batch_alter_table("rag_assistant_queries") as batch_op:
        batch_op.drop_constraint(
            "uq_rag_assistant_queries_conversation_turn", type_="unique"
        )
        batch_op.drop_index("ix_rag_assistant_queries_conversation_id")
        batch_op.drop_column("context_query_ids")
        batch_op.drop_column("turn_index")
        batch_op.drop_column("conversation_id")
