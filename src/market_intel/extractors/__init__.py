"""Data source extractors and ingestion models for market_intel."""

from market_intel.extractors.newsapi import NewsAPIExtractor
from market_intel.extractors.reddit import RedditExtractor
from market_intel.extractors.schemas import (
    ArticleSchema,
    FilingSchema,
    NewsAPIResponseSchema,
    PostSchema,
    SourceSchema,
)
from market_intel.extractors.sec_edgar import SecEdgarExtractor

__all__ = [
    "NewsAPIExtractor",
    "RedditExtractor",
    "SecEdgarExtractor",
    "ArticleSchema",
    "SourceSchema",
    "NewsAPIResponseSchema",
    "FilingSchema",
    "PostSchema",
]

