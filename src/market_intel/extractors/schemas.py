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
