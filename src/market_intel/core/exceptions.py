"""Custom exception hierarchy for market_intel."""


class MarketIntelError(Exception):
    """Base exception for all market_intel domain errors."""

    def __init__(self, message: str = "", *args: object) -> None:
        super().__init__(message, *args)
        self.message = message


class ConfigurationError(MarketIntelError):
    """Raised when configuration validation or loading fails."""


class ExtractorError(MarketIntelError):
    """Base exception for data extractor errors."""


class RateLimitError(ExtractorError):
    """Raised when an external API rate limit is exceeded."""

    def __init__(
        self,
        message: str = "Rate limit exceeded",
        retry_after: float | None = None,
        *args: object,
    ) -> None:
        super().__init__(message, *args)
        self.retry_after = retry_after


class AuthenticationError(ExtractorError):
    """Raised when authentication with an external service fails."""


class NewsAPIError(ExtractorError):
    """Raised when NewsAPI returns an error response or request fails."""

    def __init__(
        self,
        message: str = "",
        status_code: int | None = None,
        error_code: str | None = None,
        *args: object,
    ) -> None:
        super().__init__(message, *args)
        self.status_code = status_code
        self.error_code = error_code


class SecEdgarError(ExtractorError):
    """Raised when SEC EDGAR returns an error response or request fails."""

    def __init__(
        self,
        message: str = "",
        status_code: int | None = None,
        *args: object,
    ) -> None:
        super().__init__(message, *args)
        self.status_code = status_code


class RedditError(ExtractorError):
    """Raised when Reddit PRAW returns an error response or request fails."""


class AlphaVantageError(ExtractorError):
    """Raised when Alpha Vantage returns an error response or request fails."""

    def __init__(
        self,
        message: str = "",
        status_code: int | None = None,
        *args: object,
    ) -> None:
        super().__init__(message, *args)
        self.status_code = status_code


class DatabaseError(MarketIntelError):
    """Base exception for database, session, and loader errors."""


class CacheError(MarketIntelError):
    """Raised when caching or deduplication operations fail."""
