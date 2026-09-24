"""Initial database schema with raw and enriched tables.

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-09-24 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0001_initial_schema"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Fallback JSON type for non-PostgreSQL engines (e.g. SQLite offline/unit tests)
json_type = sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql")


def upgrade() -> None:
    # 1. Table: articles
    op.create_table(
        "articles",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("source_id", sa.String(length=100), nullable=True),
        sa.Column("source_name", sa.String(length=255), nullable=False),
        sa.Column("author", sa.String(length=255), nullable=True),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("url_to_image", sa.Text(), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(op.f("ix_articles_url"), "articles", ["url"], unique=True)
    op.create_index(op.f("ix_articles_published_at"), "articles", ["published_at"], unique=False)
    op.create_index(
        "ix_articles_published_at_source",
        "articles",
        ["published_at", "source_name"],
        unique=False,
    )

    # 2. Table: filings
    op.create_table(
        "filings",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("cik", sa.String(length=10), nullable=False),
        sa.Column("company_name", sa.String(length=255), nullable=False),
        sa.Column("filing_type", sa.String(length=20), nullable=False),
        sa.Column("filing_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_of_report", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revenue", sa.Float(), nullable=True),
        sa.Column("eps", sa.Float(), nullable=True),
        sa.Column("assets", sa.Float(), nullable=True),
        sa.Column("raw_metrics", json_type, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(op.f("ix_filings_cik"), "filings", ["cik"], unique=False)
    op.create_index(op.f("ix_filings_filing_type"), "filings", ["filing_type"], unique=False)
    op.create_index(op.f("ix_filings_filing_date"), "filings", ["filing_date"], unique=False)
    op.create_index("ix_filings_cik_filing_date", "filings", ["cik", "filing_date"], unique=False)

    # 3. Table: reddit_posts
    op.create_table(
        "reddit_posts",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("post_id", sa.String(length=50), nullable=False),
        sa.Column("subreddit", sa.String(length=100), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("score", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("num_comments", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("created_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("flair", sa.String(length=100), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(op.f("ix_reddit_posts_post_id"), "reddit_posts", ["post_id"], unique=True)
    op.create_index(op.f("ix_reddit_posts_subreddit"), "reddit_posts", ["subreddit"], unique=False)
    op.create_index(
        op.f("ix_reddit_posts_created_utc"), "reddit_posts", ["created_utc"], unique=False
    )
    op.create_index(
        "ix_reddit_posts_subreddit_created",
        "reddit_posts",
        ["subreddit", "created_utc"],
        unique=False,
    )

    # 4. Table: price_data
    op.create_table(
        "price_data",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("symbol", sa.String(length=20), nullable=False),
        sa.Column("date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("open", sa.Numeric(precision=12, scale=4), nullable=False),
        sa.Column("high", sa.Numeric(precision=12, scale=4), nullable=False),
        sa.Column("low", sa.Numeric(precision=12, scale=4), nullable=False),
        sa.Column("close", sa.Numeric(precision=12, scale=4), nullable=False),
        sa.Column("adjusted_close", sa.Numeric(precision=12, scale=4), nullable=True),
        sa.Column("volume", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("symbol", "date", name="uq_price_data_symbol_date"),
    )
    op.create_index(op.f("ix_price_data_symbol"), "price_data", ["symbol"], unique=False)
    op.create_index(op.f("ix_price_data_date"), "price_data", ["date"], unique=False)
    op.create_index("ix_price_data_symbol_date", "price_data", ["symbol", "date"], unique=False)

    # 5. Table: enriched_signals
    op.create_table(
        "enriched_signals",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("source_type", sa.String(length=50), nullable=False),
        sa.Column("source_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("symbol", sa.String(length=20), nullable=False),
        sa.Column("signal_type", sa.String(length=50), nullable=False),
        sa.Column("sentiment_score", sa.Float(), nullable=True),
        sa.Column("sentiment_label", sa.String(length=50), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("entities", json_type, nullable=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        op.f("ix_enriched_signals_source_id"), "enriched_signals", ["source_id"], unique=False
    )
    op.create_index(
        op.f("ix_enriched_signals_symbol"), "enriched_signals", ["symbol"], unique=False
    )
    op.create_index(
        op.f("ix_enriched_signals_signal_type"),
        "enriched_signals",
        ["signal_type"],
        unique=False,
    )
    op.create_index(
        op.f("ix_enriched_signals_timestamp"), "enriched_signals", ["timestamp"], unique=False
    )
    op.create_index(
        "ix_enriched_signals_symbol_type",
        "enriched_signals",
        ["symbol", "signal_type"],
        unique=False,
    )


def downgrade() -> None:
    # 5. Table: enriched_signals
    op.drop_index("ix_enriched_signals_symbol_type", table_name="enriched_signals")
    op.drop_index(op.f("ix_enriched_signals_timestamp"), table_name="enriched_signals")
    op.drop_index(op.f("ix_enriched_signals_signal_type"), table_name="enriched_signals")
    op.drop_index(op.f("ix_enriched_signals_symbol"), table_name="enriched_signals")
    op.drop_index(op.f("ix_enriched_signals_source_id"), table_name="enriched_signals")
    op.drop_table("enriched_signals")

    # 4. Table: price_data
    op.drop_index("ix_price_data_symbol_date", table_name="price_data")
    op.drop_index(op.f("ix_price_data_date"), table_name="price_data")
    op.drop_index(op.f("ix_price_data_symbol"), table_name="price_data")
    op.drop_table("price_data")

    # 3. Table: reddit_posts
    op.drop_index("ix_reddit_posts_subreddit_created", table_name="reddit_posts")
    op.drop_index(op.f("ix_reddit_posts_created_utc"), table_name="reddit_posts")
    op.drop_index(op.f("ix_reddit_posts_subreddit"), table_name="reddit_posts")
    op.drop_index(op.f("ix_reddit_posts_post_id"), table_name="reddit_posts")
    op.drop_table("reddit_posts")

    # 2. Table: filings
    op.drop_index("ix_filings_cik_filing_date", table_name="filings")
    op.drop_index(op.f("ix_filings_filing_date"), table_name="filings")
    op.drop_index(op.f("ix_filings_filing_type"), table_name="filings")
    op.drop_index(op.f("ix_filings_cik"), table_name="filings")
    op.drop_table("filings")

    # 1. Table: articles
    op.drop_index("ix_articles_published_at_source", table_name="articles")
    op.drop_index(op.f("ix_articles_published_at"), table_name="articles")
    op.drop_index(op.f("ix_articles_url"), table_name="articles")
    op.drop_table("articles")
