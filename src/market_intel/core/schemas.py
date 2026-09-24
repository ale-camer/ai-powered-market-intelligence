"""Canonical Pydantic v2 domain schemas and validation layer."""

import uuid
from datetime import UTC, datetime
from typing import Self

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator

from market_intel.core.cache import normalize_url
from market_intel.loaders.models import (
    ArticleModel,
    EnrichedSignalModel,
    FilingModel,
    PriceDataModel,
    RedditPostModel,
)


def ensure_utc_datetime(v: object) -> datetime:
    """Ensure datetime is converted to timezone-aware UTC datetime."""
    if isinstance(v, str):
        # Handle trailing 'Z' if present
        cleaned_str = v.replace("Z", "+00:00")
        dt = datetime.fromisoformat(cleaned_str)
    elif isinstance(v, datetime):
        dt = v
    else:
        raise ValueError(f"Expected datetime or ISO string, got {type(v).__name__}")

    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


class SourceSchema(BaseModel):
    """Source information for an ingested article."""

    model_config = ConfigDict(
        strict=True,
        from_attributes=True,
        populate_by_name=True,
        json_schema_extra={
            "example": {
                "id": "bloomberg",
                "name": "Bloomberg Markets",
            }
        },
    )

    id: str | None = None
    name: str = ""


class ArticleSchema(BaseModel):
    """Standardized article schema representing an ingested news item."""

    model_config = ConfigDict(
        strict=True,
        from_attributes=True,
        populate_by_name=True,
        json_schema_extra={
            "example": {
                "id": "123e4567-e89b-12d3-a456-426614174000",
                "source": {"id": "reuters", "name": "Reuters"},
                "author": "John Doe",
                "title": "Fed Announces Interest Rate Cut",
                "description": "The Federal Reserve lowered benchmark interest rates by 25 bps.",
                "url": "https://reuters.com/markets/rates",
                "url_to_image": "https://reuters.com/images/fed.jpg",
                "published_at": "2026-09-24T10:00:00Z",
                "content": "Full text of the news article...",
            }
        },
    )

    id: uuid.UUID | None = None
    source: SourceSchema = Field(default_factory=SourceSchema)
    author: str | None = None
    title: str = Field(min_length=1)
    description: str | None = None
    url: str
    url_to_image: str | None = Field(
        default=None,
        validation_alias=AliasChoices("urlToImage", "url_to_image"),
        serialization_alias="urlToImage",
    )
    published_at: datetime = Field(
        validation_alias=AliasChoices("publishedAt", "published_at"),
        serialization_alias="publishedAt",
    )
    content: str | None = None

    @field_validator("url", mode="before")
    @classmethod
    def validate_and_normalize_url(cls, v: object) -> str:
        """Strip tracking parameters and normalize URL format."""
        if not isinstance(v, str):
            raise ValueError(f"URL must be a string, got {type(v).__name__}")
        return normalize_url(v)

    @field_validator("published_at", mode="before")
    @classmethod
    def validate_published_at(cls, v: object) -> datetime:
        """Parse datetime ensuring UTC timezone."""
        return ensure_utc_datetime(v)

    @classmethod
    def from_orm(cls, obj: object) -> Self:
        """Adapter converting an ArticleModel ORM instance to ArticleSchema."""
        if hasattr(obj, "source_name") and not hasattr(obj, "source"):
            source = SourceSchema(
                id=getattr(obj, "source_id", None),
                name=getattr(obj, "source_name", ""),
            )
            pub_date_val = getattr(obj, "published_at", None)
            pub_date = pub_date_val if isinstance(pub_date_val, datetime) else datetime.now(UTC)
            return cls(
                id=getattr(obj, "id", None),
                source=source,
                author=getattr(obj, "author", None),
                title=getattr(obj, "title", ""),
                description=getattr(obj, "description", None),
                url=getattr(obj, "url", ""),
                url_to_image=getattr(obj, "url_to_image", None),
                published_at=pub_date,
                content=getattr(obj, "content", None),
            )
        return cls.model_validate(obj, from_attributes=True)

    def to_orm(self) -> ArticleModel:
        """Convert this schema to an ArticleModel ORM instance."""
        return ArticleModel(
            id=self.id or uuid.uuid4(),
            source_id=self.source.id,
            source_name=self.source.name,
            author=self.author,
            title=self.title,
            description=self.description,
            url=self.url,
            url_to_image=self.url_to_image,
            published_at=self.published_at,
            content=self.content,
        )


class FinancialMetricsSchema(BaseModel):
    """Extracted financial metrics from an SEC filing."""

    model_config = ConfigDict(
        strict=True,
        from_attributes=True,
        populate_by_name=True,
        json_schema_extra={
            "example": {
                "revenue": 383285000000.0,
                "eps": 6.13,
                "assets": 352583000000.0,
                "raw_metrics": {"fiscal_year": 2023},
            }
        },
    )

    revenue: float | None = None
    eps: float | None = None
    assets: float | None = None
    raw_metrics: dict[str, object] | None = None


class FilingSchema(BaseModel):
    """Standardized schema for SEC EDGAR filings."""

    model_config = ConfigDict(
        strict=True,
        from_attributes=True,
        populate_by_name=True,
        json_schema_extra={
            "example": {
                "id": "123e4567-e89b-12d3-a456-426614174001",
                "cik": "0000320193",
                "company_name": "Apple Inc.",
                "filing_type": "10-K",
                "filing_date": "2023-11-03T00:00:00Z",
                "period_of_report": "2023-09-30T00:00:00Z",
                "metrics": {
                    "revenue": 383285000000.0,
                    "eps": 6.13,
                    "assets": 352583000000.0,
                },
            }
        },
    )

    id: uuid.UUID | None = None
    cik: str
    company_name: str
    filing_type: str
    filing_date: datetime
    period_of_report: datetime | None = None
    metrics: FinancialMetricsSchema

    @field_validator("cik", mode="before")
    @classmethod
    def validate_cik(cls, v: object) -> str:
        """Ensure CIK is 10 digits padded with leading zeroes."""
        if not isinstance(v, str):
            raise ValueError(f"CIK must be string, got {type(v).__name__}")
        cleaned = v.strip()
        if not cleaned.isdigit():
            raise ValueError(f"CIK must be numeric digits, got '{cleaned}'")
        return cleaned.zfill(10)

    @field_validator("filing_date", "period_of_report", mode="before")
    @classmethod
    def validate_filing_dates(cls, v: object) -> datetime | None:
        """Parse datetime ensuring UTC timezone."""
        if v is None:
            return None
        return ensure_utc_datetime(v)

    @classmethod
    def from_orm(cls, obj: object) -> Self:
        """Adapter converting a FilingModel ORM instance to FilingSchema."""
        if hasattr(obj, "revenue") and not hasattr(obj, "metrics"):
            metrics = FinancialMetricsSchema(
                revenue=getattr(obj, "revenue", None),
                eps=getattr(obj, "eps", None),
                assets=getattr(obj, "assets", None),
                raw_metrics=getattr(obj, "raw_metrics", None),
            )
            filing_date_val = getattr(obj, "filing_date", None)
            filing_date = (
                filing_date_val if isinstance(filing_date_val, datetime) else datetime.now(UTC)
            )
            return cls(
                id=getattr(obj, "id", None),
                cik=getattr(obj, "cik", ""),
                company_name=getattr(obj, "company_name", ""),
                filing_type=getattr(obj, "filing_type", ""),
                filing_date=filing_date,
                period_of_report=getattr(obj, "period_of_report", None),
                metrics=metrics,
            )
        return cls.model_validate(obj, from_attributes=True)

    def to_orm(self) -> FilingModel:
        """Convert this schema to a FilingModel ORM instance."""
        return FilingModel(
            id=self.id or uuid.uuid4(),
            cik=self.cik,
            company_name=self.company_name,
            filing_type=self.filing_type,
            filing_date=self.filing_date,
            period_of_report=self.period_of_report,
            revenue=self.metrics.revenue,
            eps=self.metrics.eps,
            assets=self.metrics.assets,
            raw_metrics=self.metrics.raw_metrics,
        )


class PostSchema(BaseModel):
    """Standardized schema for Reddit posts."""

    model_config = ConfigDict(
        strict=True,
        from_attributes=True,
        populate_by_name=True,
        json_schema_extra={
            "example": {
                "id": "123e4567-e89b-12d3-a456-426614174002",
                "post_id": "t3_123xyz",
                "subreddit": "wallstreetbets",
                "title": "Deep Dive into NVDA Valuation",
                "body": "Analysis on data center revenue and guidance.",
                "score": 1500,
                "num_comments": 230,
                "created_utc": "2026-09-24T11:00:00Z",
                "flair": "DD",
            }
        },
    )

    id: uuid.UUID | None = None
    post_id: str = ""
    subreddit: str
    title: str = Field(min_length=1)
    body: str | None = None
    score: int = 0
    num_comments: int = 0
    created_utc: datetime
    flair: str | None = None

    @field_validator("created_utc", mode="before")
    @classmethod
    def validate_created_utc(cls, v: object) -> datetime:
        """Parse datetime ensuring UTC timezone."""
        return ensure_utc_datetime(v)

    @classmethod
    def from_orm(cls, obj: object) -> Self:
        """Adapter converting a RedditPostModel ORM instance to PostSchema."""
        return cls.model_validate(obj, from_attributes=True)

    def to_orm(self) -> RedditPostModel:
        """Convert this schema to a RedditPostModel ORM instance."""
        return RedditPostModel(
            id=self.id or uuid.uuid4(),
            post_id=self.post_id,
            subreddit=self.subreddit,
            title=self.title,
            body=self.body,
            score=self.score,
            num_comments=self.num_comments,
            created_utc=self.created_utc,
            flair=self.flair,
        )


class PriceSchema(BaseModel):
    """Standardized schema for daily OHLCV price data."""

    model_config = ConfigDict(
        strict=True,
        from_attributes=True,
        populate_by_name=True,
        json_schema_extra={
            "example": {
                "id": "123e4567-e89b-12d3-a456-426614174003",
                "symbol": "AAPL",
                "date": "2026-09-24T00:00:00Z",
                "open": 225.50,
                "high": 228.10,
                "low": 224.90,
                "close": 227.35,
                "adjusted_close": 227.35,
                "volume": 55000000,
            }
        },
    )

    id: uuid.UUID | None = None
    symbol: str
    date: datetime
    open: float
    high: float
    low: float
    close: float
    adjusted_close: float | None = None
    volume: int = Field(ge=0)

    @field_validator("symbol", mode="before")
    @classmethod
    def validate_symbol_uppercase(cls, v: object) -> str:
        """Convert ticker symbol to uppercase."""
        if not isinstance(v, str):
            raise ValueError(f"Ticker symbol must be a string, got {type(v).__name__}")
        cleaned = v.strip().upper()
        if not cleaned:
            raise ValueError("Ticker symbol cannot be empty")
        return cleaned

    @field_validator("date", mode="before")
    @classmethod
    def validate_date(cls, v: object) -> datetime:
        """Parse datetime ensuring UTC timezone."""
        return ensure_utc_datetime(v)

    @classmethod
    def from_orm(cls, obj: object) -> Self:
        """Adapter converting a PriceDataModel ORM instance to PriceSchema."""
        return cls.model_validate(obj, from_attributes=True)

    def to_orm(self) -> PriceDataModel:
        """Convert this schema to a PriceDataModel ORM instance."""
        return PriceDataModel(
            id=self.id or uuid.uuid4(),
            symbol=self.symbol,
            date=self.date,
            open=self.open,
            high=self.high,
            low=self.low,
            close=self.close,
            adjusted_close=self.adjusted_close,
            volume=self.volume,
        )


class EnrichedSignalSchema(BaseModel):
    """Enriched signal generated by downstream NLP/analysis pipelines."""

    model_config = ConfigDict(
        strict=True,
        from_attributes=True,
        populate_by_name=True,
        json_schema_extra={
            "example": {
                "id": "123e4567-e89b-12d3-a456-426614174004",
                "source_type": "article",
                "source_id": "123e4567-e89b-12d3-a456-426614174000",
                "symbol": "AAPL",
                "signal_type": "sentiment",
                "sentiment_score": 0.85,
                "sentiment_label": "bullish",
                "confidence": 0.92,
                "summary": "Record quarterly revenue drives bullish guidance.",
                "entities": {"companies": ["Apple Inc."], "tickers": ["AAPL"]},
                "embedding": [0.012, -0.045, 0.128],
                "timestamp": "2026-09-24T12:00:00Z",
            }
        },
    )

    id: uuid.UUID | None = None
    source_type: str
    source_id: uuid.UUID | None = None
    symbol: str
    signal_type: str
    sentiment_score: float | None = Field(default=None, ge=-1.0, le=1.0)
    sentiment_label: str | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    summary: str | None = None
    entities: dict[str, object] | None = None
    embedding: list[float] | None = None
    timestamp: datetime

    @field_validator("symbol", mode="before")
    @classmethod
    def validate_symbol_uppercase(cls, v: object) -> str:
        """Convert ticker symbol to uppercase."""
        if not isinstance(v, str):
            raise ValueError(f"Ticker symbol must be a string, got {type(v).__name__}")
        cleaned = v.strip().upper()
        if not cleaned:
            raise ValueError("Ticker symbol cannot be empty")
        return cleaned

    @field_validator("timestamp", mode="before")
    @classmethod
    def validate_timestamp(cls, v: object) -> datetime:
        """Parse datetime ensuring UTC timezone."""
        return ensure_utc_datetime(v)

    @field_validator("embedding", mode="before")
    @classmethod
    def validate_embedding_dimensions(cls, v: object) -> list[float] | None:
        """Validate embedding list of floats."""
        if v is None:
            return None
        if not isinstance(v, list):
            raise ValueError(f"Embedding must be a list of floats, got {type(v).__name__}")
        return [float(x) for x in v]

    @classmethod
    def from_orm(cls, obj: object) -> Self:
        """Adapter converting an EnrichedSignalModel ORM instance to EnrichedSignalSchema."""
        return cls.model_validate(obj, from_attributes=True)

    def to_orm(self) -> EnrichedSignalModel:
        """Convert this schema to an EnrichedSignalModel ORM instance."""
        return EnrichedSignalModel(
            id=self.id or uuid.uuid4(),
            source_type=self.source_type,
            source_id=self.source_id,
            symbol=self.symbol,
            signal_type=self.signal_type,
            sentiment_score=self.sentiment_score,
            sentiment_label=self.sentiment_label,
            confidence=self.confidence,
            summary=self.summary,
            entities=self.entities,
            embedding=self.embedding,
            timestamp=self.timestamp,
        )


class FundamentalsSchema(BaseModel):
    """Standardized schema for company fundamentals."""

    model_config = ConfigDict(
        strict=True,
        from_attributes=True,
        populate_by_name=True,
        json_schema_extra={
            "example": {
                "symbol": "AAPL",
                "market_cap": 3500000000000.0,
                "pe_ratio": 33.5,
                "ebitda": 130000000000.0,
                "eps": 6.13,
            }
        },
    )

    symbol: str
    market_cap: float | None = None
    pe_ratio: float | None = Field(default=None, alias="PERatio")
    ebitda: float | None = None
    eps: float | None = None

    @field_validator("symbol", mode="before")
    @classmethod
    def validate_symbol_uppercase(cls, v: object) -> str:
        """Convert ticker symbol to uppercase."""
        if not isinstance(v, str):
            raise ValueError(f"Ticker symbol must be a string, got {type(v).__name__}")
        cleaned = v.strip().upper()
        if not cleaned:
            raise ValueError("Ticker symbol cannot be empty")
        return cleaned


class NewsAPIResponseSchema(BaseModel):
    """Payload response schema returned by the NewsAPI service."""

    model_config = ConfigDict(
        strict=True,
        from_attributes=True,
        populate_by_name=True,
    )

    status: str
    total_results: int = Field(default=0, alias="totalResults")
    articles: list[ArticleSchema] = Field(default_factory=list)
    code: str | None = None
    message: str | None = None
