"""Unit tests for canonical Pydantic v2 schemas and ORM adapters."""

import uuid
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from market_intel.core.schemas import (
    ArticleSchema,
    EnrichedSignalSchema,
    FilingSchema,
    FinancialMetricsSchema,
    FundamentalsSchema,
    NewsAPIResponseSchema,
    PostSchema,
    PriceSchema,
    SourceSchema,
    ensure_utc_datetime,
)
from market_intel.loaders.models import (
    ArticleModel,
)


@pytest.mark.unit
@pytest.mark.issue_9
def test_ensure_utc_datetime_helper() -> None:
    """Validate ensure_utc_datetime parses ISO strings and standardizes timezones to UTC."""
    # ISO string with Z
    dt_z = ensure_utc_datetime("2026-09-24T12:00:00Z")
    assert dt_z.tzinfo == UTC
    assert dt_z.hour == 12

    # Naive datetime gets converted to UTC
    naive_dt = datetime(2026, 9, 24, 15, 30, 0)
    aware_dt = ensure_utc_datetime(naive_dt)
    assert aware_dt.tzinfo == UTC

    # Non-UTC timezone gets converted to UTC
    offset_dt = datetime.fromisoformat("2026-09-24T14:00:00+02:00")
    utc_dt = ensure_utc_datetime(offset_dt)
    assert utc_dt.tzinfo == UTC
    assert utc_dt.hour == 12

    # Invalid input raises ValueError
    with pytest.raises(ValueError, match="Expected datetime or ISO string"):
        ensure_utc_datetime(12345)


@pytest.mark.unit
@pytest.mark.issue_9
def test_article_schema_validation_and_url_normalization() -> None:
    """Validate ArticleSchema normalizes tracking URLs and validates fields."""
    article = ArticleSchema(
        source=SourceSchema(id="nyt", name="New York Times"),
        title="Fed Signals Further Rate Cuts",
        url="https://nytimes.com/markets/fed/?utm_source=twitter&utm_medium=social&ticker=SPY",
        published_at="2026-09-24T10:00:00Z",
    )

    assert article.url == "https://nytimes.com/markets/fed?ticker=SPY"
    assert article.published_at.tzinfo == UTC
    assert article.source.name == "New York Times"

    # Strict validation rejects invalid URL types
    with pytest.raises(ValidationError):
        ArticleSchema(
            title="Invalid",
            url=12345,  # type: ignore[arg-type]
            published_at=datetime.now(UTC),
        )


@pytest.mark.unit
@pytest.mark.issue_9
def test_article_schema_orm_bidirectional_conversion() -> None:
    """Validate ArticleSchema conversion to and from ArticleModel."""
    uid = uuid.uuid4()
    orm_model = ArticleModel(
        id=uid,
        source_id="wsj",
        source_name="Wall Street Journal",
        author="Jane Doe",
        title="Tech Rally Continues",
        description="Nasdaq gains 2% led by AI chipmakers.",
        url="https://wsj.com/articles/tech-rally",
        url_to_image="https://wsj.com/img.png",
        published_at=datetime(2026, 9, 24, 9, 0, 0, tzinfo=UTC),
        content="Full story...",
    )

    # Convert from ORM
    schema = ArticleSchema.from_orm(orm_model)
    assert schema.id == uid
    assert schema.source.id == "wsj"
    assert schema.source.name == "Wall Street Journal"
    assert schema.title == "Tech Rally Continues"

    # Convert back to ORM
    converted_orm = schema.to_orm()
    assert converted_orm.id == uid
    assert converted_orm.source_id == "wsj"
    assert converted_orm.source_name == "Wall Street Journal"
    assert converted_orm.url == "https://wsj.com/articles/tech-rally"


@pytest.mark.unit
@pytest.mark.issue_9
def test_filing_schema_cik_validation_and_orm_conversion() -> None:
    """Validate FilingSchema pads CIK, parses dates, and converts to/from FilingModel."""
    filing = FilingSchema(
        cik="320193",  # Needs padding to 10 digits
        company_name="Apple Inc.",
        filing_type="10-K",
        filing_date="2023-11-03T00:00:00Z",
        period_of_report=None,
        metrics=FinancialMetricsSchema(
            revenue=383285000000.0,
            eps=6.13,
            assets=352583000000.0,
            raw_metrics={"source": "xbrl"},
        ),
    )
    assert filing.cik == "0000320193"
    assert filing.filing_date.tzinfo == UTC

    # Non-numeric CIK raises ValidationError
    with pytest.raises(ValidationError):
        FilingSchema(
            cik="AAPL-CIK",
            company_name="Apple Inc.",
            filing_type="10-K",
            filing_date=datetime.now(UTC),
            metrics=FinancialMetricsSchema(),
        )

    # Conversion to ORM
    orm_model = filing.to_orm()
    assert orm_model.cik == "0000320193"
    assert orm_model.revenue == 383285000000.0
    assert orm_model.raw_metrics == {"source": "xbrl"}

    # Conversion from ORM
    converted_schema = FilingSchema.from_orm(orm_model)
    assert converted_schema.cik == "0000320193"
    assert converted_schema.metrics.revenue == 383285000000.0


@pytest.mark.unit
@pytest.mark.issue_9
def test_post_schema_validation_and_orm_conversion() -> None:
    """Validate PostSchema defaults, date parsing, and ORM conversion."""
    post = PostSchema(
        post_id="t3_abc123",
        subreddit="stocks",
        title="Bullish case for renewable energy",
        created_utc="2026-09-24T08:00:00Z",
    )
    assert post.score == 0
    assert post.num_comments == 0
    assert post.created_utc.tzinfo == UTC

    # ORM conversion
    orm_model = post.to_orm()
    assert orm_model.post_id == "t3_abc123"
    assert orm_model.subreddit == "stocks"

    converted = PostSchema.from_orm(orm_model)
    assert converted.post_id == "t3_abc123"
    assert converted.title == post.title


@pytest.mark.unit
@pytest.mark.issue_9
def test_price_schema_symbol_uppercase_and_orm_conversion() -> None:
    """Validate PriceSchema symbol uppercase normalization and ORM conversion."""
    price = PriceSchema(
        symbol="  nvda  ",
        date="2026-09-24T00:00:00Z",
        open=120.0,
        high=125.0,
        low=119.5,
        close=124.2,
        volume=45000000,
    )
    assert price.symbol == "NVDA"
    assert price.volume == 45000000

    # Negative volume or empty symbol raises ValidationError
    with pytest.raises(ValidationError):
        PriceSchema(
            symbol="NVDA",
            date=datetime.now(UTC),
            open=100.0,
            high=105.0,
            low=95.0,
            close=102.0,
            volume=-10,
        )

    with pytest.raises(ValidationError):
        PriceSchema(
            symbol="   ",
            date=datetime.now(UTC),
            open=100.0,
            high=105.0,
            low=95.0,
            close=102.0,
            volume=100,
        )

    # ORM conversion
    orm_model = price.to_orm()
    assert orm_model.symbol == "NVDA"
    assert float(orm_model.close) == 124.2

    converted = PriceSchema.from_orm(orm_model)
    assert converted.symbol == "NVDA"
    assert converted.close == 124.2


@pytest.mark.unit
@pytest.mark.issue_9
def test_enriched_signal_schema_validation_and_orm_conversion() -> None:
    """Validate EnrichedSignalSchema score bounds, embeddings, and ORM conversion."""
    signal = EnrichedSignalSchema(
        source_type="article",
        symbol="msft",
        signal_type="sentiment",
        sentiment_score=0.75,
        confidence=0.90,
        summary="Azure revenue accelerates growth.",
        entities={"companies": ["Microsoft"]},
        embedding=[0.1, -0.2, 0.3],
        timestamp="2026-09-24T12:00:00Z",
    )
    assert signal.symbol == "MSFT"
    assert signal.sentiment_score == 0.75
    assert signal.embedding == [0.1, -0.2, 0.3]

    # Out of bounds sentiment score or confidence
    with pytest.raises(ValidationError):
        EnrichedSignalSchema(
            source_type="article",
            symbol="MSFT",
            signal_type="sentiment",
            sentiment_score=1.5,  # Must be <= 1.0
            timestamp=datetime.now(UTC),
        )

    with pytest.raises(ValidationError):
        EnrichedSignalSchema(
            source_type="article",
            symbol="MSFT",
            signal_type="sentiment",
            confidence=-0.1,  # Must be >= 0.0
            timestamp=datetime.now(UTC),
        )

    # Invalid embedding type
    with pytest.raises(ValidationError):
        EnrichedSignalSchema(
            source_type="article",
            symbol="MSFT",
            signal_type="sentiment",
            embedding="invalid_vector",  # type: ignore[arg-type]
            timestamp=datetime.now(UTC),
        )

    # ORM conversion
    orm_model = signal.to_orm()
    assert orm_model.symbol == "MSFT"
    assert orm_model.embedding == [0.1, -0.2, 0.3]

    converted = EnrichedSignalSchema.from_orm(orm_model)
    assert converted.symbol == "MSFT"
    assert converted.embedding == [0.1, -0.2, 0.3]


@pytest.mark.unit
@pytest.mark.issue_9
def test_fundamentals_and_newsapi_response_schemas() -> None:
    """Validate FundamentalsSchema and NewsAPIResponseSchema."""
    fund = FundamentalsSchema(
        symbol="tsla",
        market_cap=800000000000.0,
        PERatio=65.4,
    )
    assert fund.symbol == "TSLA"
    assert fund.pe_ratio == 65.4

    news_resp = NewsAPIResponseSchema(
        status="ok",
        totalResults=1,
        articles=[
            ArticleSchema(
                title="Test Article",
                url="https://example.com/test",
                publishedAt="2026-09-24T12:00:00Z",
            )
        ],
    )
    assert news_resp.total_results == 1
    assert len(news_resp.articles) == 1
    assert news_resp.articles[0].title == "Test Article"


@pytest.mark.unit
@pytest.mark.issue_9
def test_json_schema_extra_examples_present() -> None:
    """Verify that json_schema_extra examples are defined on all core models."""
    models_to_check = [
        SourceSchema,
        ArticleSchema,
        FinancialMetricsSchema,
        FilingSchema,
        PostSchema,
        PriceSchema,
        EnrichedSignalSchema,
        FundamentalsSchema,
    ]
    for model_cls in models_to_check:
        config = model_cls.model_config
        assert "json_schema_extra" in config
        assert "example" in config["json_schema_extra"]
