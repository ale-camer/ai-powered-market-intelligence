"""Asynchronous NewsAPI extractor with pagination and exponential backoff retry logic."""

import asyncio
import contextlib
from collections.abc import AsyncGenerator, Mapping
from types import TracebackType

import httpx

from market_intel.core.config import get_settings
from market_intel.core.exceptions import (
    AuthenticationError,
    NewsAPIError,
    RateLimitError,
)
from market_intel.core.logger import get_logger
from market_intel.extractors.schemas import ArticleSchema, NewsAPIResponseSchema

logger = get_logger(__name__)

ParamValue = str | int | float | bool | None


class NewsAPIExtractor:
    """Production-grade asynchronous connector for NewsAPI.

    Features:
    - Async HTTP requests via `httpx.AsyncClient`.
    - Automatic retries with exponential backoff on HTTP 429 and 5xx responses.
    - Respects `Retry-After` response headers when available.
    - Full pagination traversal with optional `max_articles` bounds.
    - Asynchronous streaming generator for articles.
    - Typed Pydantic data validation (`ArticleSchema`).
    """

    DEFAULT_BASE_URL: str = "https://newsapi.org/v2"

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = 10.0,
        max_retries: int = 3,
        backoff_factor: float = 1.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        """Initialize the NewsAPI extractor.

        Args:
            api_key: NewsAPI API key. If omitted, loaded from settings.
            base_url: Base URL for NewsAPI v2 endpoints.
            timeout: Request timeout in seconds.
            max_retries: Maximum number of retry attempts for 429 and 5xx responses.
            backoff_factor: Multiplier for exponential backoff calculations.
            client: Optional pre-configured httpx.AsyncClient (e.g. for testing).
        """
        resolved_key = api_key if api_key is not None else get_settings().newsapi_api_key
        if not resolved_key or not resolved_key.strip():
            raise AuthenticationError(
                "NewsAPI API key is missing. Provide it via constructor or NEWSAPI_API_KEY env var."
            )

        self.api_key = resolved_key.strip()
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        self.backoff_factor = backoff_factor

        self._injected_client = client
        self._client: httpx.AsyncClient | None = client

    async def _get_client(self) -> httpx.AsyncClient:
        """Return or lazily initialize the underlying AsyncClient."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=self.timeout,
                headers={
                    "X-Api-Key": self.api_key,
                    "User-Agent": "MarketIntel/0.1",
                    "Accept": "application/json",
                },
            )
        return self._client

    async def close(self) -> None:
        """Close the underlying HTTP client session."""
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    async def __aenter__(self) -> "NewsAPIExtractor":
        """Support asynchronous context management."""
        await self._get_client()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Close client on context exit if not externally injected."""
        if self._injected_client is None:
            await self.close()

    def _calculate_backoff(self, attempt: int, response: httpx.Response | None = None) -> float:
        """Calculate wait delay in seconds using Retry-After header or exponential backoff."""
        if response is not None:
            retry_after_header = response.headers.get("Retry-After")
            if retry_after_header:
                with contextlib.suppress(ValueError):
                    return max(0.0, float(retry_after_header))
        return float(self.backoff_factor * (2**attempt))

    @property
    def _headers(self) -> dict[str, str]:
        """Default request headers including API key authentication."""
        return {
            "X-Api-Key": self.api_key,
            "User-Agent": "MarketIntel/0.1",
            "Accept": "application/json",
        }

    async def _request(
        self,
        endpoint: str,
        params: Mapping[str, ParamValue],
    ) -> NewsAPIResponseSchema:
        """Execute HTTP GET request with exponential backoff and error classification."""
        client = await self._get_client()
        clean_endpoint = endpoint.lstrip("/")
        attempt = 0

        while True:
            try:
                response = await client.get(
                    clean_endpoint,
                    params=params,
                    headers=self._headers,
                )
                status = response.status_code

                if status == 200:
                    payload = response.json()
                    parsed = NewsAPIResponseSchema.model_validate(payload)
                    if parsed.status == "error":
                        if parsed.code in {"rateLimited", "rateLimitExceeded"}:
                            if attempt >= self.max_retries:
                                raise RateLimitError(
                                    parsed.message or "Rate limit exceeded from NewsAPI payload"
                                )
                            delay = self._calculate_backoff(attempt)
                            logger.warning(
                                "Rate limit reported in payload. Retrying in %.2fs (attempt %d/%d)",
                                delay,
                                attempt + 1,
                                self.max_retries,
                            )
                            attempt += 1
                            await asyncio.sleep(delay)
                            continue
                        raise NewsAPIError(
                            parsed.message or "NewsAPI error reported in payload",
                            status_code=200,
                            error_code=parsed.code,
                        )
                    return parsed

                if status in {401, 403}:
                    try:
                        err_payload = response.json()
                        msg = err_payload.get("message", response.text)
                    except Exception:
                        msg = response.text
                    raise AuthenticationError(f"Authentication failed (HTTP {status}): {msg}")

                if status == 429:
                    retry_after: float | None = None
                    hdr = response.headers.get("Retry-After")
                    if hdr:
                        with contextlib.suppress(ValueError):
                            retry_after = float(hdr)

                    if attempt >= self.max_retries:
                        raise RateLimitError(
                            f"NewsAPI rate limit exceeded after {self.max_retries} retries",
                            retry_after=retry_after,
                        )

                    delay = self._calculate_backoff(attempt, response)
                    logger.warning(
                        "NewsAPI HTTP 429 received. Backing off for %.2fs (attempt %d/%d)",
                        delay,
                        attempt + 1,
                        self.max_retries,
                    )
                    attempt += 1
                    await asyncio.sleep(delay)
                    continue

                if 500 <= status < 600:
                    if attempt >= self.max_retries:
                        raise NewsAPIError(
                            f"NewsAPI server error ({status}) after {self.max_retries} retries",
                            status_code=status,
                        )

                    delay = self._calculate_backoff(attempt, response)
                    logger.warning(
                        "NewsAPI HTTP %d server error. Retrying in %.2fs (attempt %d/%d)",
                        status,
                        delay,
                        attempt + 1,
                        self.max_retries,
                    )
                    attempt += 1
                    await asyncio.sleep(delay)
                    continue

                # Unhandled 4xx or unexpected status
                try:
                    err_json = response.json()
                    err_msg = err_json.get("message", response.text)
                    err_code = err_json.get("code")
                except Exception:
                    err_msg = response.text
                    err_code = None

                raise NewsAPIError(
                    f"NewsAPI request failed (HTTP {status}): {err_msg}",
                    status_code=status,
                    error_code=err_code,
                )

            except (RateLimitError, AuthenticationError, NewsAPIError):
                raise
            except httpx.TransportError as exc:
                if attempt >= self.max_retries:
                    err_text = (
                        f"Transport error connecting to NewsAPI "
                        f"after {self.max_retries} retries: {exc}"
                    )
                    raise NewsAPIError(err_text) from exc

                delay = self._calculate_backoff(attempt)
                logger.warning(
                    "Transport error: %s. Retrying in %.2fs (attempt %d/%d)",
                    exc,
                    delay,
                    attempt + 1,
                    self.max_retries,
                )
                attempt += 1
                await asyncio.sleep(delay)

    async def fetch_page(
        self,
        endpoint: str = "everything",
        **params: ParamValue,
    ) -> NewsAPIResponseSchema:
        """Fetch a single page of results from the specified endpoint.

        Args:
            endpoint: NewsAPI endpoint ("everything" or "top-headlines").
            **params: Query parameters passed to NewsAPI (q, sources, page, pageSize, etc.).

        Returns:
            Validated NewsAPIResponseSchema.
        """
        clean_params = {k: v for k, v in params.items() if v is not None}
        return await self._request(endpoint=endpoint, params=clean_params)

    async def get_articles(
        self,
        query: str,
        *,
        endpoint: str = "everything",
        from_date: str | None = None,
        to_date: str | None = None,
        language: str | None = "en",
        sort_by: str | None = "publishedAt",
        page_size: int = 100,
        max_articles: int | None = None,
        **extra_params: ParamValue,
    ) -> list[ArticleSchema]:
        """Fetch and aggregate articles with full pagination traversal.

        Args:
            query: Keyword or phrase to search for.
            endpoint: NewsAPI endpoint (default: "everything").
            from_date: ISO 8601 date string (YYYY-MM-DD).
            to_date: ISO 8601 date string (YYYY-MM-DD).
            language: 2-letter ISO-639-1 code (default: "en").
            sort_by: Sorting order ("relevancy", "popularity", "publishedAt").
            page_size: Results per page (1 to 100, default: 100).
            max_articles: Maximum total number of articles to return (None for all available).
            **extra_params: Additional query parameters (domains, sources, etc.).

        Returns:
            List of validated ArticleSchema models.
        """
        if not query or not query.strip():
            raise ValueError("Query string cannot be empty")

        if page_size < 1 or page_size > 100:
            raise ValueError("page_size must be between 1 and 100")

        articles: list[ArticleSchema] = []
        page = 1

        while True:
            params: dict[str, ParamValue] = {
                "q": query.strip(),
                "page": page,
                "pageSize": page_size,
                "from": from_date,
                "to": to_date,
                "language": language,
                "sortBy": sort_by,
                **extra_params,
            }

            response = await self.fetch_page(endpoint=endpoint, **params)
            page_articles = response.articles

            if not page_articles:
                break

            articles.extend(page_articles)

            # Check if max limit reached
            if max_articles is not None and len(articles) >= max_articles:
                articles = articles[:max_articles]
                break

            # Stop if all available results collected
            if len(articles) >= response.total_results:
                break

            # If page returned fewer articles than requested page_size, no further pages exist
            if len(page_articles) < page_size:
                break

            page += 1

        return articles

    async def stream_articles(
        self,
        query: str,
        *,
        endpoint: str = "everything",
        from_date: str | None = None,
        to_date: str | None = None,
        language: str | None = "en",
        sort_by: str | None = "publishedAt",
        page_size: int = 100,
        max_articles: int | None = None,
        **extra_params: ParamValue,
    ) -> AsyncGenerator[ArticleSchema, None]:
        """Asynchronously stream articles one-by-one with lazy page fetching.

        Args:
            query: Keyword or phrase to search for.
            endpoint: NewsAPI endpoint (default: "everything").
            from_date: ISO 8601 date string (YYYY-MM-DD).
            to_date: ISO 8601 date string (YYYY-MM-DD).
            language: 2-letter ISO-639-1 code (default: "en").
            sort_by: Sorting order ("relevancy", "popularity", "publishedAt").
            page_size: Results per page (1 to 100, default: 100).
            max_articles: Maximum total number of articles to yield.
            **extra_params: Additional query parameters.

        Yields:
            ArticleSchema items sequentially.
        """
        if not query or not query.strip():
            raise ValueError("Query string cannot be empty")

        if page_size < 1 or page_size > 100:
            raise ValueError("page_size must be between 1 and 100")

        yielded = 0
        page = 1

        while True:
            params: dict[str, ParamValue] = {
                "q": query.strip(),
                "page": page,
                "pageSize": page_size,
                "from": from_date,
                "to": to_date,
                "language": language,
                "sortBy": sort_by,
                **extra_params,
            }

            response = await self.fetch_page(endpoint=endpoint, **params)
            page_articles = response.articles

            if not page_articles:
                break

            for article in page_articles:
                yield article
                yielded += 1
                if max_articles is not None and yielded >= max_articles:
                    return

            if yielded >= response.total_results or len(page_articles) < page_size:
                break

            page += 1
