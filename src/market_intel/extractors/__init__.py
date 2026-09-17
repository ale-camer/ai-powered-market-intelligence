"""Data source extractors and ingestion models for market_intel."""

from market_intel.extractors.newsapi import NewsAPIExtractor
from market_intel.extractors.schemas import (
    ArticleSchema,
    NewsAPIResponseSchema,
    SourceSchema,
)

__all__ = [
    "NewsAPIExtractor",
    "ArticleSchema",
    "SourceSchema",
    "NewsAPIResponseSchema",
]
