"""Data source extractors and ingestion models for market_intel."""

from market_intel.extractors.alpha_vantage import AlphaVantageExtractor
from market_intel.extractors.newsapi import NewsAPIExtractor
from market_intel.extractors.reddit import RedditExtractor
from market_intel.extractors.schemas import (
    ArticleSchema,
    FilingSchema,
    FundamentalsSchema,
    NewsAPIResponseSchema,
    PostSchema,
    PriceSchema,
    SourceSchema,
)
from market_intel.extractors.sec_edgar import SecEdgarExtractor

__all__ = [
    "AlphaVantageExtractor",
    "NewsAPIExtractor",
    "RedditExtractor",
    "SecEdgarExtractor",
    "ArticleSchema",
    "SourceSchema",
    "NewsAPIResponseSchema",
    "FilingSchema",
    "FundamentalsSchema",
    "PostSchema",
    "PriceSchema",
]
