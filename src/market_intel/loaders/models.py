"""SQLAlchemy 2.0 declarative models for raw and enriched tables."""

import uuid
from datetime import datetime
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    DateTime,
    Float,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from market_intel.loaders.database import Base, TimestampMixin

# Use JSONB for PostgreSQL and generic JSON for SQLite/other engines
JSON_VARIANT = JSON().with_variant(JSONB(), "postgresql")
# Use Vector(1536) for PostgreSQL and JSON for SQLite/unit test engines
VECTOR_VARIANT = Vector(1536).with_variant(JSON(), "sqlite")


class ArticleModel(Base, TimestampMixin):
    """Raw articles ingested from NewsAPI or other news providers."""

    __tablename__ = "articles"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    source_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    source_name: Mapped[str] = mapped_column(String(255), nullable=False)
    author: Mapped[str | None] = mapped_column(String(255), nullable=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    url: Mapped[str] = mapped_column(Text, nullable=False, unique=True, index=True)
    url_to_image: Mapped[str | None] = mapped_column(Text, nullable=True)
    published_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )
    content: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (Index("ix_articles_published_at_source", "published_at", "source_name"),)


class FilingModel(Base, TimestampMixin):
    """SEC EDGAR financial filings (10-K, 10-Q) and parsed XBRL metrics."""

    __tablename__ = "filings"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    cik: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    company_name: Mapped[str] = mapped_column(String(255), nullable=False)
    filing_type: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    filing_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )
    period_of_report: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    revenue: Mapped[float | None] = mapped_column(Float, nullable=True)
    eps: Mapped[float | None] = mapped_column(Float, nullable=True)
    assets: Mapped[float | None] = mapped_column(Float, nullable=True)
    raw_metrics: Mapped[dict[str, Any] | None] = mapped_column(
        JSON_VARIANT,
        nullable=True,
    )

    __table_args__ = (Index("ix_filings_cik_filing_date", "cik", "filing_date"),)


class RedditPostModel(Base, TimestampMixin):
    """Reddit posts collected from financial subreddits."""

    __tablename__ = "reddit_posts"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    post_id: Mapped[str] = mapped_column(String(50), nullable=False, unique=True, index=True)
    subreddit: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    num_comments: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_utc: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )
    flair: Mapped[str | None] = mapped_column(String(100), nullable=True)

    __table_args__ = (Index("ix_reddit_posts_subreddit_created", "subreddit", "created_utc"),)


class PriceDataModel(Base, TimestampMixin):
    """Daily OHLCV price time-series and trading volume."""

    __tablename__ = "price_data"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    symbol: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )
    open: Mapped[float] = mapped_column(Numeric(12, 4), nullable=False)
    high: Mapped[float] = mapped_column(Numeric(12, 4), nullable=False)
    low: Mapped[float] = mapped_column(Numeric(12, 4), nullable=False)
    close: Mapped[float] = mapped_column(Numeric(12, 4), nullable=False)
    adjusted_close: Mapped[float | None] = mapped_column(Numeric(12, 4), nullable=True)
    volume: Mapped[int] = mapped_column(BigInteger, nullable=False)

    __table_args__ = (
        UniqueConstraint("symbol", "date", name="uq_price_data_symbol_date"),
        Index("ix_price_data_symbol_date", "symbol", "date"),
    )


class EnrichedSignalModel(Base, TimestampMixin):
    """Enriched signals generated by downstream NLP/anomaly pipelines."""

    __tablename__ = "enriched_signals"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    source_type: Mapped[str] = mapped_column(String(50), nullable=False)
    source_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        nullable=True,
        index=True,
    )
    symbol: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    signal_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    sentiment_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    sentiment_label: Mapped[str | None] = mapped_column(String(50), nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    entities: Mapped[dict[str, Any] | None] = mapped_column(
        JSON_VARIANT,
        nullable=True,
    )
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )
    embedding: Mapped[list[float] | None] = mapped_column(
        VECTOR_VARIANT,
        nullable=True,
    )

    __table_args__ = (
        Index("ix_enriched_signals_symbol_type", "symbol", "signal_type"),
        Index(
            "ix_enriched_signals_embedding_ivfflat",
            "embedding",
            postgresql_using="ivfflat",
            postgresql_with={"lists": 100},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )
