"""Loaders package: database management, schema definitions, and migrations."""

from market_intel.loaders.database import (
    Base,
    TimestampMixin,
    get_async_engine,
    get_async_session,
    get_async_session_factory,
)
from market_intel.loaders.models import (
    ArticleModel,
    EnrichedSignalModel,
    FilingModel,
    PriceDataModel,
    RedditPostModel,
)
from market_intel.loaders.repository import (
    EmbeddingRepository,
    compute_cosine_similarity,
)

__all__ = [
    "Base",
    "TimestampMixin",
    "get_async_engine",
    "get_async_session",
    "get_async_session_factory",
    "ArticleModel",
    "FilingModel",
    "RedditPostModel",
    "PriceDataModel",
    "EnrichedSignalModel",
    "EmbeddingRepository",
    "compute_cosine_similarity",
]
