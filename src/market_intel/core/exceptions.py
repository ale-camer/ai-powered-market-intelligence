"""Custom exception hierarchy for market_intel."""


class MarketIntelError(Exception):
    """Base exception for all market_intel domain errors."""

    def __init__(self, message: str = "", *args: object) -> None:
        super().__init__(message, *args)
        self.message = message


class ConfigurationError(MarketIntelError):
    """Raised when configuration validation or loading fails."""
