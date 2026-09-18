"""Alpha Vantage extractor for fetching financial metrics."""

import asyncio
from datetime import UTC, datetime
from typing import Any

import httpx

from market_intel.core.config import get_settings
from market_intel.core.exceptions import AlphaVantageError
from market_intel.extractors.schemas import FundamentalsSchema, PriceSchema


class AlphaVantageExtractor:
    """Client for extracting data from Alpha Vantage."""

    BASE_URL = "https://www.alphavantage.co/query"

    def __init__(self, api_key: str | None = None) -> None:
        """Initialize the Alpha Vantage client."""
        settings = get_settings()
        self.api_key = api_key or settings.alpha_vantage_api_key
        if not self.api_key:
            raise AlphaVantageError("Missing Alpha Vantage API key.")
        
        self.client = httpx.AsyncClient()
        self._cache: dict[str, dict[str, Any]] = {}
        
        # Rate limiting state
        self._call_timestamps: list[float] = []
        self._calls_per_minute = 5

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self.client.aclose()

    async def _enforce_rate_limit(self) -> None:
        """Enforce the 5 calls per minute rate limit."""
        now = asyncio.get_event_loop().time()
        
        # Remove timestamps older than 60 seconds
        self._call_timestamps = [t for t in self._call_timestamps if now - t < 60.0]
        
        if len(self._call_timestamps) >= self._calls_per_minute:
            # We need to wait until the oldest call is 60 seconds old
            sleep_time = 60.0 - (now - self._call_timestamps[0])
            if sleep_time > 0:
                await asyncio.sleep(sleep_time)
            
            # Re-evaluate after sleeping
            now = asyncio.get_event_loop().time()
            self._call_timestamps = [t for t in self._call_timestamps if now - t < 60.0]

        self._call_timestamps.append(now)

    async def _request(self, function: str, symbol: str, **kwargs: str) -> dict[str, Any]:
        """Make an async request to Alpha Vantage with caching and rate limiting."""
        cache_key = f"{function}_{symbol}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        await self._enforce_rate_limit()

        params = {
            "function": function,
            "symbol": symbol,
            "apikey": self.api_key,
            **kwargs,
        }

        try:
            response = await self.client.get(self.BASE_URL, params=params)
            response.raise_for_status()
            data: dict[str, Any] = response.json()

            if "Error Message" in data:
                raise AlphaVantageError(data["Error Message"])
            info = data.get("Information", "").lower()
            if "rate limit" in info or "call frequency" in info:
                raise AlphaVantageError("Rate limit exceeded returned by API.")

            self._cache[cache_key] = data
            return data
            
        except httpx.HTTPError as e:
            raise AlphaVantageError(f"HTTP Error: {e}") from e
        except ValueError as e:
            raise AlphaVantageError(f"JSON Decode Error: {e}") from e

    async def fetch_daily_adjusted(self, symbol: str) -> list[PriceSchema]:
        """Fetch daily adjusted time series data."""
        data = await self._request("TIME_SERIES_DAILY_ADJUSTED", symbol, outputsize="compact")
        
        time_series = data.get("Time Series (Daily)", {})
        if not time_series:
            return []

        prices = []
        for date_str, metrics in time_series.items():
            date_obj = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=UTC)
            prices.append(
                PriceSchema(
                    symbol=symbol,
                    date=date_obj,
                    open=float(metrics.get("1. open", 0.0)),
                    high=float(metrics.get("2. high", 0.0)),
                    low=float(metrics.get("3. low", 0.0)),
                    close=float(metrics.get("4. close", 0.0)),
                    adjusted_close=float(metrics.get("5. adjusted close", 0.0)),
                    volume=int(metrics.get("6. volume", 0)),
                )
            )
        return prices

    async def fetch_overview(self, symbol: str) -> FundamentalsSchema | None:
        """Fetch company overview and fundamentals."""
        data = await self._request("OVERVIEW", symbol)
        
        if not data or not data.get("Symbol"):
            return None

        def _safe_float(val: str | None) -> float | None:
            if not val or val.lower() == "none":
                return None
            try:
                return float(val)
            except ValueError:
                return None

        return FundamentalsSchema(
            symbol=data["Symbol"],
            market_cap=_safe_float(data.get("MarketCapitalization")),
            PERatio=_safe_float(data.get("PERatio")),
            ebitda=_safe_float(data.get("EBITDA")),
            eps=_safe_float(data.get("EPS")),
        )

    async def fetch_earnings(self, symbol: str) -> dict[str, Any]:
        """Fetch earnings data. For now, returning raw dict to satisfy requirements."""
        data = await self._request("EARNINGS", symbol)
        return data
