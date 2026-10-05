"""Unit tests for SEC EDGAR Extractor (enhanced for Issue #19)."""

from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock

import httpx
import pytest

from market_intel.core.exceptions import RateLimitError, SecEdgarError
from market_intel.extractors.sec_edgar import SecEdgarExtractor

pytestmark = [pytest.mark.issue_3, pytest.mark.issue_19]


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
                    "0000320193-21-000107",
                ],
                "filingDate": ["2021-10-29", "2021-12-30", "2021-09-29"],
                "primaryDocument": ["apple-10k.htm", "apple-10q.htm", "apple-8k.htm"],
            }
        },
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


def test_invalid_user_agent_raises_error() -> None:
    with pytest.raises(ValueError, match="valid User-Agent"):
        SecEdgarExtractor(user_agent="")
    with pytest.raises(ValueError, match="valid User-Agent"):
        SecEdgarExtractor(user_agent="   ")


@pytest.mark.asyncio
async def test_async_context_manager_lifecycle() -> None:
    async with SecEdgarExtractor(user_agent="TestCompany test@example.com") as extractor:
        assert extractor._client is not None
        assert not extractor._client.is_closed
    # After exiting context, client should be closed
    assert extractor._client is None or extractor._client.is_closed


@pytest.mark.asyncio
async def test_server_error_500_retry_and_exhaustion() -> None:
    def handle_request(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="Service Unavailable")

    transport = httpx.MockTransport(handle_request)
    client = httpx.AsyncClient(transport=transport)

    extractor = SecEdgarExtractor(client=client, max_retries=1)
    with pytest.raises(SecEdgarError) as exc_info:
        await extractor.fetch_filings(cik="0000000001", form_type="10-K")
    assert exc_info.value.status_code == 503


@pytest.mark.asyncio
async def test_client_error_400_raises_immediately() -> None:
    def handle_request(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, text="Bad Request")

    transport = httpx.MockTransport(handle_request)
    client = httpx.AsyncClient(transport=transport)

    extractor = SecEdgarExtractor(client=client, max_retries=2)
    with pytest.raises(SecEdgarError) as exc_info:
        await extractor.fetch_filings(cik="0000000001", form_type="10-K")
    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_transport_error_retry_and_exhaustion() -> None:
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.is_closed = False
    mock_client.get.side_effect = httpx.ConnectError("Connection failed")

    extractor = SecEdgarExtractor(client=mock_client, max_retries=1)
    with pytest.raises(SecEdgarError, match="Transport error"):
        await extractor.fetch_filings(cik="0000000001", form_type="10-K")


def test_parse_xbrl_html_with_xml_and_malformed_tags() -> None:
    extractor = SecEdgarExtractor()

    # XML document with nonfraction tags and invalid float value
    xml_content = """<?xml version="1.0" encoding="UTF-8"?>
    <xbrl>
        <ix:nonFraction name="us-gaap:Revenues">1,250,000</ix:nonFraction>
        <ix:nonFraction name="us-gaap:EarningsPerShareDiluted">2.45</ix:nonFraction>
        <ix:nonFraction name="us-gaap:Assets">invalid_number</ix:nonFraction>
        <div name="ignored">999</div>
    </xbrl>
    """
    metrics = extractor._parse_xbrl_html(xml_content)
    assert metrics["revenue"] == 1250000.0
    assert metrics["eps"] == 2.45
    assert "assets" not in metrics  # Malformed float gracefully skipped


@pytest.mark.asyncio
async def test_fetch_filings_date_parsing_fallback(mock_submissions_data: dict) -> None:
    # Corrupt the filingDate
    corrupted_data = dict(mock_submissions_data)
    corrupted_data["filings"]["recent"]["filingDate"] = [
        "not-a-valid-date",
        "2021-12-30",
        "2021-09-29",
    ]

    def handle_request(request: httpx.Request) -> httpx.Response:
        if "submissions/CIK" in str(request.url):
            return httpx.Response(200, json=corrupted_data)
        return httpx.Response(200, text="<html></html>")

    transport = httpx.MockTransport(handle_request)
    client = httpx.AsyncClient(transport=transport)

    extractor = SecEdgarExtractor(client=client)
    filings = await extractor.fetch_filings(cik="320193", form_type="10-K")

    assert len(filings) == 1
    # Fallback date was assigned
    assert isinstance(filings[0].filing_date, datetime)


@pytest.mark.asyncio
async def test_fetch_filings_document_fetch_failure_handling(mock_submissions_data: dict) -> None:
    def handle_request(request: httpx.Request) -> httpx.Response:
        if "submissions/CIK" in str(request.url):
            return httpx.Response(200, json=mock_submissions_data)
        # Fail the document retrieval
        return httpx.Response(404, text="Document Not Found")

    transport = httpx.MockTransport(handle_request)
    client = httpx.AsyncClient(transport=transport)

    extractor = SecEdgarExtractor(client=client)
    filings = await extractor.fetch_filings(cik="320193", form_type="10-K")

    assert len(filings) == 1
    assert filings[0].metrics.revenue is None
    assert filings[0].metrics.eps is None


@pytest.mark.asyncio
async def test_fetch_filings_empty_recent_filings() -> None:
    empty_submissions = {"name": "Empty Corp", "filings": {"recent": {}}}

    def handle_request(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=empty_submissions)

    transport = httpx.MockTransport(handle_request)
    client = httpx.AsyncClient(transport=transport)

    extractor = SecEdgarExtractor(client=client)
    filings = await extractor.fetch_filings(cik="0000000000", form_type="10-K")
    assert filings == []
