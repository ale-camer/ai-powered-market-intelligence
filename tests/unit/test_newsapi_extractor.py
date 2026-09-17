"""Unit tests for NewsAPIExtractor with mocked HTTP responses."""

from collections.abc import Callable
from typing import Any

import httpx
import pytest

from market_intel.core.exceptions import (
    AuthenticationError,
    NewsAPIError,
    RateLimitError,
)
from market_intel.extractors.newsapi import NewsAPIExtractor
from market_intel.extractors.schemas import ArticleSchema, NewsAPIResponseSchema

SAMPLE_ARTICLE_DATA: dict[str, Any] = {
    "source": {"id": "wired", "name": "Wired"},
    "author": "Jane Doe",
    "title": "Quantum Computing Breakthrough",
    "description": "Scientists achieve fault-tolerant qubit scaling.",
    "url": "https://example.com/quantum",
    "urlToImage": "https://example.com/images/quantum.jpg",
    "publishedAt": "2026-09-17T08:00:00Z",
    "content": "Full story content goes here...",
}

MockHandler = Callable[[httpx.Request], httpx.Response]


def _make_client(handler: MockHandler) -> httpx.AsyncClient:
    """Create an AsyncClient with a mock transport handler."""
    transport = httpx.MockTransport(handler)
    return httpx.AsyncClient(transport=transport, base_url="https://newsapi.org/v2")


@pytest.mark.unit
@pytest.mark.issue_2
@pytest.mark.issue_02
async def test_fetch_page_success() -> None:
    """Verify single page fetch parses correctly into Pydantic models."""

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v2/everything"
        assert request.headers.get("X-Api-Key") == "test-key"
        payload = {
            "status": "ok",
            "totalResults": 1,
            "articles": [SAMPLE_ARTICLE_DATA],
        }
        return httpx.Response(200, json=payload)

    client = _make_client(handler)
    extractor = NewsAPIExtractor(api_key="test-key", client=client)

    result = await extractor.fetch_page(q="quantum")

    assert isinstance(result, NewsAPIResponseSchema)
    assert result.status == "ok"
    assert result.total_results == 1
    assert len(result.articles) == 1

    article = result.articles[0]
    assert isinstance(article, ArticleSchema)
    assert article.title == "Quantum Computing Breakthrough"
    assert article.source.name == "Wired"
    assert article.source.id == "wired"
    assert article.url_to_image == "https://example.com/images/quantum.jpg"
    assert article.published_at.year == 2026


@pytest.mark.unit
@pytest.mark.issue_2
@pytest.mark.issue_02
async def test_pagination_full_traversal() -> None:
    """Verify pagination iterates across pages until totalResults is reached."""
    requested_pages: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        page = int(request.url.params.get("page", "1"))
        requested_pages.append(page)

        article = dict(SAMPLE_ARTICLE_DATA)
        article["title"] = f"Article Page {page}"

        payload = {
            "status": "ok",
            "totalResults": 3,
            "articles": [article],
        }
        return httpx.Response(200, json=payload)

    client = _make_client(handler)
    extractor = NewsAPIExtractor(api_key="test-key", client=client)

    articles = await extractor.get_articles(query="finance", page_size=1)

    assert len(articles) == 3
    assert requested_pages == [1, 2, 3]
    assert [a.title for a in articles] == [
        "Article Page 1",
        "Article Page 2",
        "Article Page 3",
    ]


@pytest.mark.unit
@pytest.mark.issue_2
@pytest.mark.issue_02
async def test_pagination_max_articles_limit() -> None:
    """Verify pagination respects max_articles bound and stops early."""
    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        page = int(request.url.params.get("page", "1"))

        articles = [
            {**SAMPLE_ARTICLE_DATA, "title": f"Article {page}-1"},
            {**SAMPLE_ARTICLE_DATA, "title": f"Article {page}-2"},
        ]
        payload = {
            "status": "ok",
            "totalResults": 100,
            "articles": articles,
        }
        return httpx.Response(200, json=payload)

    client = _make_client(handler)
    extractor = NewsAPIExtractor(api_key="test-key", client=client)

    articles = await extractor.get_articles(query="stocks", page_size=2, max_articles=3)

    assert len(articles) == 3
    assert call_count == 2
    assert [a.title for a in articles] == [
        "Article 1-1",
        "Article 1-2",
        "Article 2-1",
    ]


@pytest.mark.unit
@pytest.mark.issue_2
@pytest.mark.issue_02
async def test_rate_limit_retry_success() -> None:
    """Verify HTTP 429 triggers exponential backoff and succeeds on subsequent attempt."""
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            return httpx.Response(429, headers={"Retry-After": "0.001"})
        return httpx.Response(
            200,
            json={
                "status": "ok",
                "totalResults": 1,
                "articles": [SAMPLE_ARTICLE_DATA],
            },
        )

    client = _make_client(handler)
    extractor = NewsAPIExtractor(
        api_key="test-key",
        client=client,
        max_retries=3,
        backoff_factor=0.001,
    )

    result = await extractor.fetch_page(q="market")
    assert attempts == 3
    assert result.status == "ok"
    assert len(result.articles) == 1


@pytest.mark.unit
@pytest.mark.issue_2
@pytest.mark.issue_02
async def test_rate_limit_retry_exhaustion() -> None:
    """Verify exceeding max_retries on HTTP 429 raises RateLimitError with retry_after."""
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(429, headers={"Retry-After": "2.5"})

    client = _make_client(handler)
    extractor = NewsAPIExtractor(
        api_key="test-key",
        client=client,
        max_retries=2,
        backoff_factor=0.001,
    )

    with pytest.raises(RateLimitError) as exc_info:
        await extractor.fetch_page(q="market")

    assert attempts == 3  # Initial + 2 retries
    assert exc_info.value.retry_after == 2.5
    assert "rate limit exceeded" in str(exc_info.value).lower()


@pytest.mark.unit
@pytest.mark.issue_2
@pytest.mark.issue_02
async def test_rate_limit_payload_error() -> None:
    """Verify NewsAPI 200 responses with rateLimited error payload trigger backoff."""
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return httpx.Response(
                200,
                json={
                    "status": "error",
                    "code": "rateLimited",
                    "message": "You have been rate limited.",
                },
            )
        return httpx.Response(
            200,
            json={
                "status": "ok",
                "totalResults": 1,
                "articles": [SAMPLE_ARTICLE_DATA],
            },
        )

    client = _make_client(handler)
    extractor = NewsAPIExtractor(
        api_key="test-key",
        client=client,
        max_retries=2,
        backoff_factor=0.001,
    )

    result = await extractor.fetch_page(q="market")
    assert attempts == 2
    assert result.status == "ok"


@pytest.mark.unit
@pytest.mark.issue_2
@pytest.mark.issue_02
async def test_server_error_retry_exhaustion() -> None:
    """Verify HTTP 500 errors trigger retry and raise NewsAPIError on exhaustion."""
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(500, text="Internal Server Error")

    client = _make_client(handler)
    extractor = NewsAPIExtractor(
        api_key="test-key",
        client=client,
        max_retries=2,
        backoff_factor=0.001,
    )

    with pytest.raises(NewsAPIError) as exc_info:
        await extractor.fetch_page(q="market")

    assert attempts == 3
    assert exc_info.value.status_code == 500


@pytest.mark.unit
@pytest.mark.issue_2
@pytest.mark.issue_02
async def test_authentication_error_on_401() -> None:
    """Verify HTTP 401 raises AuthenticationError immediately without retrying."""
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(
            401,
            json={
                "status": "error",
                "code": "apiKeyInvalid",
                "message": "Your API key is invalid.",
            },
        )

    client = _make_client(handler)
    extractor = NewsAPIExtractor(api_key="bad-key", client=client, max_retries=3)

    with pytest.raises(AuthenticationError) as exc_info:
        await extractor.fetch_page(q="market")

    assert attempts == 1  # No retries on 401
    assert "apiKeyInvalid" in str(exc_info.value) or "invalid" in str(exc_info.value).lower()


@pytest.mark.unit
@pytest.mark.issue_2
@pytest.mark.issue_02
def test_missing_api_key_raises_auth_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify initialization without API key raises AuthenticationError."""
    monkeypatch.setenv("NEWSAPI_API_KEY", "")
    from market_intel.core.config import get_settings

    get_settings.cache_clear()

    with pytest.raises(AuthenticationError):
        NewsAPIExtractor(api_key="")


@pytest.mark.unit
@pytest.mark.issue_2
@pytest.mark.issue_02
async def test_client_error_400() -> None:
    """Verify HTTP 400 bad request raises NewsAPIError with API code and message."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            400,
            json={
                "status": "error",
                "code": "parameterInvalid",
                "message": "The parameter is invalid.",
            },
        )

    client = _make_client(handler)
    extractor = NewsAPIExtractor(api_key="test-key", client=client)

    with pytest.raises(NewsAPIError) as exc_info:
        await extractor.fetch_page(invalid_param="foo")

    assert exc_info.value.status_code == 400
    assert exc_info.value.error_code == "parameterInvalid"


@pytest.mark.unit
@pytest.mark.issue_2
@pytest.mark.issue_02
async def test_validation_errors() -> None:
    """Verify empty queries or invalid page_size raise ValueError."""
    client = _make_client(lambda r: httpx.Response(200, json={}))
    extractor = NewsAPIExtractor(api_key="test-key", client=client)

    with pytest.raises(ValueError, match="empty"):
        await extractor.get_articles(query="")

    with pytest.raises(ValueError, match="page_size"):
        await extractor.get_articles(query="test", page_size=0)

    with pytest.raises(ValueError, match="page_size"):
        await extractor.get_articles(query="test", page_size=150)


@pytest.mark.unit
@pytest.mark.issue_2
@pytest.mark.issue_02
async def test_stream_articles() -> None:
    """Verify stream_articles yields articles incrementally."""

    def handler(request: httpx.Request) -> httpx.Response:
        page = int(request.url.params.get("page", "1"))
        payload = {
            "status": "ok",
            "totalResults": 2,
            "articles": [{**SAMPLE_ARTICLE_DATA, "title": f"Streamed {page}"}],
        }
        return httpx.Response(200, json=payload)

    client = _make_client(handler)
    extractor = NewsAPIExtractor(api_key="test-key", client=client)

    streamed: list[ArticleSchema] = []
    async for article in extractor.stream_articles(query="test", page_size=1):
        streamed.append(article)

    assert len(streamed) == 2
    assert streamed[0].title == "Streamed 1"
    assert streamed[1].title == "Streamed 2"


@pytest.mark.unit
@pytest.mark.issue_2
@pytest.mark.issue_02
async def test_context_manager() -> None:
    """Verify async context manager creates and closes client cleanly."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "status": "ok",
                "totalResults": 0,
                "articles": [],
            },
        )

    transport = httpx.MockTransport(handler)

    async with NewsAPIExtractor(api_key="test-key") as extractor:
        # Patch client to use mock transport for this test
        extractor._client = httpx.AsyncClient(
            transport=transport, base_url="https://newsapi.org/v2"
        )
        res = await extractor.fetch_page(q="test")
        assert res.total_results == 0

    assert extractor._client is None or extractor._client.is_closed
