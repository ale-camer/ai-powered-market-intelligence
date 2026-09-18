"""Asynchronous SEC EDGAR extractor with rate limiting and XBRL parsing."""

import asyncio
import time
from collections.abc import Mapping
from datetime import datetime
from types import TracebackType

import httpx
from bs4 import BeautifulSoup

from market_intel.core.exceptions import (
    RateLimitError,
    SecEdgarError,
)
from market_intel.core.logger import get_logger
from market_intel.extractors.schemas import FilingSchema, FinancialMetricsSchema

logger = get_logger(__name__)

ParamValue = str | int | float | bool | None


class SecEdgarExtractor:
    """Production-grade asynchronous connector for SEC EDGAR API.

    Features:
    - Async HTTP requests via `httpx.AsyncClient`.
    - Strict 10 requests per second rate limiting.
    - Custom User-Agent handling as required by SEC.
    - XBRL inline parsing using beautifulsoup4.
    - Typed Pydantic data validation (`FilingSchema`).
    """

    DEFAULT_BASE_URL: str = "https://data.sec.gov"
    SEC_SUBMISSIONS_URL: str = "https://data.sec.gov/submissions"
    SEC_COMPANY_FACTS_URL: str = "https://data.sec.gov/api/xbrl/companyfacts"
    RATE_LIMIT_DELAY = 0.11  # Slightly more than 1/10 to ensure safety

    def __init__(
        self,
        user_agent: str = "MarketIntel Admin admin@marketintel.com",
        timeout: float = 10.0,
        max_retries: int = 3,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        """Initialize the SEC EDGAR extractor.

        Args:
            user_agent: Required by SEC. Format: 'Company Name Contact@<domain>.com'.
            timeout: Request timeout in seconds.
            max_retries: Maximum number of retry attempts for 429 and 5xx responses.
            client: Optional pre-configured httpx.AsyncClient (e.g. for testing).
        """
        if not user_agent or not user_agent.strip():
            raise ValueError("SEC EDGAR requires a valid User-Agent header.")

        self.user_agent = user_agent.strip()
        self.timeout = timeout
        self.max_retries = max_retries

        self._injected_client = client
        self._client: httpx.AsyncClient | None = client
        self._last_request_time: float = 0.0
        self._lock = asyncio.Lock()

    async def _get_client(self) -> httpx.AsyncClient:
        """Return or lazily initialize the underlying AsyncClient."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=self.timeout,
                headers={
                    "User-Agent": self.user_agent,
                    "Accept-Encoding": "gzip, deflate",
                },
            )
        return self._client

    async def close(self) -> None:
        """Close the underlying HTTP client session."""
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    async def __aenter__(self) -> "SecEdgarExtractor":
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

    async def _rate_limit(self) -> None:
        """Enforce strict 10 requests per second limit."""
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_request_time
            if elapsed < self.RATE_LIMIT_DELAY:
                delay = self.RATE_LIMIT_DELAY - elapsed
                await asyncio.sleep(delay)
            self._last_request_time = time.monotonic()

    async def _request(
        self,
        url: str,
        params: Mapping[str, ParamValue] | None = None,
    ) -> httpx.Response:
        """Execute HTTP GET request with rate limiting and exponential backoff."""
        client = await self._get_client()
        attempt = 0

        while True:
            await self._rate_limit()
            try:
                response = await client.get(url, params=params)
                status = response.status_code

                if status == 200:
                    return response

                if status == 429:
                    if attempt >= self.max_retries:
                        raise RateLimitError("SEC EDGAR rate limit exceeded")
                    delay = 1.0 * (2**attempt)
                    logger.warning("HTTP 429 from SEC. Retrying in %.2fs", delay)
                    attempt += 1
                    await asyncio.sleep(delay)
                    continue

                if 500 <= status < 600:
                    if attempt >= self.max_retries:
                        raise SecEdgarError(f"SEC server error ({status})", status_code=status)
                    delay = 1.0 * (2**attempt)
                    logger.warning("HTTP %d from SEC. Retrying in %.2fs", status, delay)
                    attempt += 1
                    await asyncio.sleep(delay)
                    continue

                raise SecEdgarError(f"SEC request failed (HTTP {status})", status_code=status)

            except (RateLimitError, SecEdgarError):
                raise
            except httpx.TransportError as exc:
                if attempt >= self.max_retries:
                    raise SecEdgarError(f"Transport error: {exc}") from exc
                delay = 1.0 * (2**attempt)
                attempt += 1
                await asyncio.sleep(delay)

    def _parse_xbrl_html(self, html_content: str) -> dict[str, float]:
        """Parse inline XBRL tags from an HTML/XML document using beautifulsoup4."""
        parser = "xml" if html_content.lstrip().startswith("<?xml") else "lxml"
        soup = BeautifulSoup(html_content, parser)
        metrics = {}

        for tag in soup.find_all(lambda tag: tag.name and "nonfraction" in tag.name.lower()):
            raw_name = tag.get("name", "")
            name_attr = raw_name[0].lower() if isinstance(raw_name, list) else str(raw_name).lower()
            text_val = tag.get_text(strip=True).replace(",", "")
            
            try:
                val = float(text_val)
            except ValueError:
                continue

            if "revenue" in name_attr or "sales" in name_attr:
                metrics["revenue"] = val
            elif "earningspershare" in name_attr or "eps" in name_attr:
                metrics["eps"] = val
            elif "assets" in name_attr:
                metrics["assets"] = val

        return metrics

    async def fetch_filings(
        self,
        cik: str,
        form_type: str = "10-K",
    ) -> list[FilingSchema]:
        """Fetch filings for a given CIK and form type.
        
        Args:
            cik: Central Index Key (10 digit string).
            form_type: Form type to filter (e.g. "10-K" or "10-Q").
            
        Returns:
            List of parsed FilingSchema models.
        """
        padded_cik = str(cik).zfill(10)
        url = f"{self.SEC_SUBMISSIONS_URL}/CIK{padded_cik}.json"
        
        response = await self._request(url)
        data = response.json()
        
        company_name = data.get("name", "Unknown Company")
        filings_data = data.get("filings", {}).get("recent", {})
        
        results: list[FilingSchema] = []
        if not filings_data:
            return results
            
        forms = filings_data.get("form", [])
        accession_numbers = filings_data.get("accessionNumber", [])
        filing_dates = filings_data.get("filingDate", [])
        primary_documents = filings_data.get("primaryDocument", [])
        
        for idx, form in enumerate(forms):
            if form != form_type:
                continue
                
            acc_num = accession_numbers[idx]
            clean_acc_num = acc_num.replace("-", "")
            f_date_str = filing_dates[idx]
            primary_doc = primary_documents[idx]
            
            try:
                filing_date = datetime.strptime(f_date_str, "%Y-%m-%d")
            except (ValueError, TypeError):
                filing_date = datetime.now()
                
            doc_url = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{clean_acc_num}/{primary_doc}"
            try:
                doc_resp = await self._request(doc_url)
                xbrl_metrics = self._parse_xbrl_html(doc_resp.text)
            except Exception as e:
                logger.warning("Failed to fetch or parse XBRL document: %s", e)
                xbrl_metrics = {}

            metrics = FinancialMetricsSchema(
                revenue=xbrl_metrics.get("revenue"),
                eps=xbrl_metrics.get("eps"),
                assets=xbrl_metrics.get("assets"),
            )
            
            results.append(FilingSchema(
                cik=padded_cik,
                company_name=company_name,
                filing_type=form,
                filing_date=filing_date,
                metrics=metrics,
            ))
            
        return results
