"""Core utilities, configuration, and base abstractions for market_intel."""

from market_intel.core.cache import (
    CACHE_HITS_TOTAL,
    CACHE_MISSES_TOTAL,
    DeduplicationCache,
    generate_fingerprint,
    normalize_url,
)
from market_intel.core.config import Settings, get_settings
from market_intel.core.exceptions import (
    AuthenticationError,
    CacheError,
    ConfigurationError,
    DatabaseError,
    ExtractorError,
    MarketIntelError,
    NewsAPIError,
    RateLimitError,
)
from market_intel.core.logger import configure_logging, get_logger

__all__ = [
    "Settings",
    "get_settings",
    "MarketIntelError",
    "ConfigurationError",
    "ExtractorError",
    "RateLimitError",
    "AuthenticationError",
    "NewsAPIError",
    "DatabaseError",
    "CacheError",
    "DeduplicationCache",
    "generate_fingerprint",
    "normalize_url",
    "CACHE_HITS_TOTAL",
    "CACHE_MISSES_TOTAL",
    "configure_logging",
    "get_logger",
]
