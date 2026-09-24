"""Add pgvector extension and embedding column to enriched_signals.

Revision ID: 0002_add_vector_embeddings
Revises: 0001_initial_schema
Create Date: 2026-09-24 12:30:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

# revision identifiers, used by Alembic.
revision: str = "0002_add_vector_embeddings"
down_revision: str | None = "0001_initial_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

vector_type = Vector(1536).with_variant(sa.JSON(), "sqlite")


def upgrade() -> None:
    # 1. Enable pgvector extension on PostgreSQL
    context = op.get_context()
    if context.dialect.name == "postgresql":
        op.execute("CREATE EXTENSION IF NOT EXISTS vector;")

    # 2. Add embedding column to enriched_signals
    op.add_column(
        "enriched_signals",
        sa.Column("embedding", vector_type, nullable=True),
    )

    # 3. Create ivfflat index with cosine ops
    op.create_index(
        "ix_enriched_signals_embedding_ivfflat",
        "enriched_signals",
        ["embedding"],
        unique=False,
        postgresql_using="ivfflat",
        postgresql_with={"lists": 100},
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )


def downgrade() -> None:
    # 1. Drop ivfflat index
    op.drop_index(
        "ix_enriched_signals_embedding_ivfflat",
        table_name="enriched_signals",
    )

    # 2. Drop embedding column
    op.drop_column("enriched_signals", "embedding")
