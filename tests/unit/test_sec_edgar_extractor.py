"""Unit tests for SEC EDGAR Extractor."""

from pathlib import Path

import httpx
import pytest

from market_intel.core.exceptions import RateLimitError
from market_intel.extractors.sec_edgar import SecEdgarExtractor

pytestmark = pytest.mark.issue_3


@pytest.fixture
def mock_submissions_data() -> dict:
    return {
        "cik": "0000320193",
        "name": "Apple Inc.",
        "filings": {
            "recent": {
                "form": ["10-K", "10-Q", "8-K"],
                "accessionNumber": [
                    "0000320193-21-000105", 
                    "0000320193-21-000106", 
                    "0000320193-21-000107"
                ],
                "filingDate": ["2021-10-29", "2021-12-30", "2021-09-29"],
                "primaryDocument": ["apple-10k.htm", "apple-10q.htm", "apple-8k.htm"]
            }
        }
    }


@pytest.fixture
def html_10k() -> str:
    fixture_path = Path(__file__).parent.parent / "fixtures" / "sec_10k_sample.xml"
    if fixture_path.exists():
        return fixture_path.read_text()
    return ""


@pytest.mark.asyncio
async def test_fetch_filings_success(mock_submissions_data: dict, html_10k: str) -> None:
    def handle_request(request: httpx.Request) -> httpx.Response:
        if "submissions/CIK" in str(request.url):
            return httpx.Response(200, json=mock_submissions_data)
        elif "apple-10k.htm" in str(request.url):
            return httpx.Response(200, text=html_10k)
        return httpx.Response(404, text="Not Found")

    transport = httpx.MockTransport(handle_request)
    client = httpx.AsyncClient(transport=transport)

    extractor = SecEdgarExtractor(client=client)
    filings = await extractor.fetch_filings(cik="320193", form_type="10-K")

    assert len(filings) == 1
    f = filings[0]
    assert f.company_name == "Apple Inc."
    assert f.filing_type == "10-K"
    if html_10k:
        assert f.metrics.revenue == 5000000.0
        assert f.metrics.eps == 1.25
        assert f.metrics.assets == 10000000.0


@pytest.mark.asyncio
async def test_rate_limit_retry() -> None:
    request_count = 0

    def handle_request(request: httpx.Request) -> httpx.Response:
        nonlocal request_count
        request_count += 1
        if request_count < 3:
            return httpx.Response(429, text="Too Many Requests")
        return httpx.Response(200, json={"name": "Test", "filings": {"recent": {}}})

    transport = httpx.MockTransport(handle_request)
    client = httpx.AsyncClient(transport=transport)

    extractor = SecEdgarExtractor(client=client, max_retries=3)
    await extractor.fetch_filings(cik="1234567890", form_type="10-K")

    # The request should succeed on the 3rd try
    assert request_count == 3


@pytest.mark.asyncio
async def test_rate_limit_exceeded() -> None:
    def handle_request(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, text="Too Many Requests")

    transport = httpx.MockTransport(handle_request)
    client = httpx.AsyncClient(transport=transport)

    extractor = SecEdgarExtractor(client=client, max_retries=1)
    
    with pytest.raises(RateLimitError):
        await extractor.fetch_filings(cik="1234567890", form_type="10-K")
