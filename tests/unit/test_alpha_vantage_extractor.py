"""Unit tests for the AlphaVantageExtractor."""

from collections.abc import AsyncGenerator, Generator
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from market_intel.core.exceptions import AlphaVantageError
from market_intel.extractors.alpha_vantage import AlphaVantageExtractor


@pytest.fixture
def mock_httpx_client() -> Generator[AsyncMock, None, None]:
    """Mock the httpx.AsyncClient."""
    with patch("market_intel.extractors.alpha_vantage.httpx.AsyncClient") as mock_client:
        mock_instance = AsyncMock()
        mock_client.return_value = mock_instance
        yield mock_instance


@pytest.fixture
async def extractor(
    mock_httpx_client: AsyncMock,
) -> AsyncGenerator[AlphaVantageExtractor, None]:
    """Return an AlphaVantageExtractor instance with mocked httpx."""
    ext = AlphaVantageExtractor(api_key="test_key")
    yield ext
    await ext.close()


@pytest.mark.asyncio
@pytest.mark.issue_5
async def test_fetch_daily_adjusted_success(
    extractor: AlphaVantageExtractor, mock_httpx_client: AsyncMock
) -> None:
    """Test successful fetching and mapping of daily adjusted prices."""
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "Meta Data": {"2. Symbol": "AAPL"},
        "Time Series (Daily)": {
            "2023-10-01": {
                "1. open": "170.00",
                "2. high": "172.00",
                "3. low": "169.50",
                "4. close": "171.00",
                "5. adjusted close": "171.00",
                "6. volume": "50000000",
            }
        },
    }
    mock_httpx_client.get.return_value = mock_response

    prices = await extractor.fetch_daily_adjusted("AAPL")

    assert len(prices) == 1
    price = prices[0]
    assert price.symbol == "AAPL"
    assert price.date == datetime(2023, 10, 1, tzinfo=UTC)
    assert price.open == 170.00
    assert price.high == 172.00
    assert price.low == 169.50
    assert price.close == 171.00
    assert price.adjusted_close == 171.00
    assert price.volume == 50000000


@pytest.mark.asyncio
@pytest.mark.issue_5
async def test_fetch_overview_success(
    extractor: AlphaVantageExtractor, mock_httpx_client: AsyncMock
) -> None:
    """Test successful fetching and mapping of company overview."""
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "Symbol": "AAPL",
        "AssetType": "Common Stock",
        "Name": "Apple Inc",
        "Description": "Apple designs consumer electronics...",
        "MarketCapitalization": "2800000000000",
        "EBITDA": "125000000000",
        "PERatio": "28.5",
        "EPS": "6.12",
    }
    mock_httpx_client.get.return_value = mock_response

    fundamentals = await extractor.fetch_overview("AAPL")

    assert fundamentals is not None
    assert fundamentals.symbol == "AAPL"
    assert fundamentals.market_cap == 2800000000000.0
    assert fundamentals.ebitda == 125000000000.0
    assert fundamentals.pe_ratio == 28.5
    assert fundamentals.eps == 6.12


@pytest.mark.asyncio
@pytest.mark.issue_5
async def test_fetch_overview_missing_fields(
    extractor: AlphaVantageExtractor, mock_httpx_client: AsyncMock
) -> None:
    """Test overview fetching gracefully handles missing or 'None' fields."""
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "Symbol": "AAPL",
        "MarketCapitalization": "None",
        "EBITDA": "-",
    }
    mock_httpx_client.get.return_value = mock_response

    fundamentals = await extractor.fetch_overview("AAPL")

    assert fundamentals is not None
    assert fundamentals.symbol == "AAPL"
    assert fundamentals.market_cap is None
    assert fundamentals.ebitda is None
    assert fundamentals.pe_ratio is None
    assert fundamentals.eps is None


@pytest.mark.asyncio
@pytest.mark.issue_5
async def test_rate_limit_exceeded_raises_error(
    extractor: AlphaVantageExtractor, mock_httpx_client: AsyncMock
) -> None:
    """Test that rate limit API response raises AlphaVantageError."""
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "Information": (
            "Thank you for using Alpha Vantage! Our standard API call frequency is "
            "5 calls per minute and 500 calls per day."
        )
    }
    mock_httpx_client.get.return_value = mock_response

    with pytest.raises(AlphaVantageError, match="Rate limit exceeded"):
        await extractor.fetch_overview("AAPL")


@pytest.mark.asyncio
@pytest.mark.issue_5
async def test_http_error_raises_alpha_vantage_error(
    extractor: AlphaVantageExtractor, mock_httpx_client: AsyncMock
) -> None:
    """Test that HTTPError is mapped to AlphaVantageError."""
    mock_response = MagicMock()
    mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
        "404 Not Found", request=MagicMock(), response=MagicMock()
    )
    mock_httpx_client.get.return_value = mock_response

    with pytest.raises(AlphaVantageError, match="HTTP Error: 404"):
        await extractor.fetch_overview("AAPL")


@pytest.mark.asyncio
@pytest.mark.issue_5
async def test_caching_behavior(
    extractor: AlphaVantageExtractor, mock_httpx_client: AsyncMock
) -> None:
    """Test that subsequent calls to the same endpoint use cache."""
    mock_response = MagicMock()
    mock_response.json.return_value = {"Symbol": "AAPL", "PERatio": "28.5"}
    mock_httpx_client.get.return_value = mock_response

    res1 = await extractor.fetch_overview("AAPL")
    res2 = await extractor.fetch_overview("AAPL")

    # Asserting these are safe since we mock success response which shouldn't be None
    assert res1 is not None and res1.pe_ratio == 28.5
    assert res2 is not None and res2.pe_ratio == 28.5
    assert mock_httpx_client.get.call_count == 1  # Should only be called once
