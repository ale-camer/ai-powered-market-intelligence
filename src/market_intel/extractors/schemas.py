"""Extractor payloads and backward-compatible re-exports from core.schemas."""

from market_intel.core.schemas import (
    ArticleSchema,
    FilingSchema,
    FinancialMetricsSchema,
    FundamentalsSchema,
    NewsAPIResponseSchema,
    PostSchema,
    PriceSchema,
    SourceSchema,
)

__all__ = [
    "SourceSchema",
    "ArticleSchema",
    "NewsAPIResponseSchema",
    "FinancialMetricsSchema",
    "FilingSchema",
    "PostSchema",
    "PriceSchema",
    "FundamentalsSchema",
]
