"""Pydantic data models for extractor payloads and normalized schemas."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class SourceSchema(BaseModel):
    """Source information for an extracted article."""

    model_config = ConfigDict(populate_by_name=True)

    id: str | None = None
    name: str = ""


class ArticleSchema(BaseModel):
    """Standardized article schema representing an ingested news item."""

    model_config = ConfigDict(populate_by_name=True)

    source: SourceSchema
    author: str | None = None
    title: str
    description: str | None = None
    url: str
    url_to_image: str | None = Field(default=None, alias="urlToImage")
    published_at: datetime = Field(alias="publishedAt")
    content: str | None = None


class NewsAPIResponseSchema(BaseModel):
    """Payload response schema returned by the NewsAPI service."""

    model_config = ConfigDict(populate_by_name=True)

    status: str
    total_results: int = Field(default=0, alias="totalResults")
    articles: list[ArticleSchema] = Field(default_factory=list)
    code: str | None = None
    message: str | None = None


class FinancialMetricsSchema(BaseModel):
    """Extracted financial metrics from an SEC filing."""

    model_config = ConfigDict(populate_by_name=True)

    revenue: float | None = None
    eps: float | None = None
    assets: float | None = None


class FilingSchema(BaseModel):
    """Standardized schema for SEC EDGAR filings."""

    model_config = ConfigDict(populate_by_name=True)

    cik: str
    company_name: str
    filing_type: str
    filing_date: datetime
    period_of_report: datetime | None = None
    metrics: FinancialMetricsSchema


class PostSchema(BaseModel):
    """Standardized schema for Reddit posts."""

    model_config = ConfigDict(populate_by_name=True)

    subreddit: str
    title: str
    body: str | None = None
    score: int
    num_comments: int
    created_utc: datetime
    flair: str | None = None
