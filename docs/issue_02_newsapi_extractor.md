# Issue 2: Implement NewsAPI extractor with pagination and rate-limit handling

**Branch:** `feature/issue-2-newsapi-extractor`  
**Status:** In Progress  
**PR:** TBD  

---

## Objective

Build a production-grade, asynchronous NewsAPI connector in `src/market_intel/extractors/newsapi.py` capable of fetching articles with full pagination traversal, handling rate limits (HTTP 429) and server errors (HTTP 5xx) via exponential backoff, and returning typed `ArticleSchema` Pydantic models.

---

## Acceptance Criteria

- [x] **Async HTTP Client**: Implement `NewsAPIExtractor` using `httpx.AsyncClient` with proper lifecycle management (`async with` / context manager and `close()`).
- [x] **Pydantic Schemas**: Define `ArticleSchema`, `SourceSchema`, and `NewsAPIResponseSchema` with aliased field mappings (`publishedAt`, `urlToImage`, etc.) under `src/market_intel/extractors/schemas.py`.
- [x] **Pagination Engine**: Full pagination support to iterate through all results (or up to `max_articles`) across multiple pages.
- [x] **Resilience & Exponential Backoff**: Automatic retry logic on HTTP 429 and 5xx responses with backoff factor, respect for `Retry-After` header, and custom exceptions (`RateLimitError`, `NewsAPIError`, `AuthenticationError`).
- [x] **Unit Tests**: Complete unit test suite with mocked HTTP responses (`pytest -m issue_2` and `pytest -m issue_02`) covering success, pagination, 429 retry backoff, 5xx server errors, and 401 auth failures.
- [x] **Integration Test**: Live API integration test in `tests/integration/test_newsapi_integration.py` guarded by `NEWSAPI_API_KEY` presence.

---

## Implementation Tasks

### 1. Preparation and Branching
```bash
make start-issue ID=2 NAME=newsapi-extractor
```

### 2. Core Exceptions & Configuration
- **File**: `src/market_intel/core/exceptions.py`
  - Add `ExtractorError(MarketIntelError)`.
  - Add `RateLimitError(ExtractorError)` with `retry_after: float | None`.
  - Add `AuthenticationError(ExtractorError)`.
  - Add `NewsAPIError(ExtractorError)`.
- **File**: `pyproject.toml`
  - Add `httpx>=0.27.0` to `[project.optional-dependencies] ingestion`.
  - Add `issue_02` marker to `[tool.pytest.ini_options]`.

### 3. Data Models & Schemas
- **File**: `src/market_intel/extractors/schemas.py`
  - Define `SourceSchema(id: str | None, name: str)`.
  - Define `ArticleSchema(source, author, title, description, url, url_to_image, published_at, content)`.
  - Define `NewsAPIResponseSchema(status, total_results, articles, code, message)`.

### 4. NewsAPI Extractor Implementation
- **File**: `src/market_intel/extractors/newsapi.py`
  - Implement `NewsAPIExtractor` with configuration (`api_key`, `base_url`, `timeout`, `max_retries`, `backoff_factor`).
  - Implement `async with` context manager.
  - Implement retry loop with exponential backoff on 429 / 5xx.
  - Implement `fetch_page(endpoint, **params) -> NewsAPIResponseSchema`.
  - Implement `get_articles(query, max_articles, page_size, **params) -> list[ArticleSchema]`.
  - Implement `stream_articles(query, page_size, **params) -> AsyncGenerator[ArticleSchema, None]`.
- **File**: `src/market_intel/extractors/__init__.py`
  - Re-export `NewsAPIExtractor`, `ArticleSchema`, `SourceSchema`, `NewsAPIResponseSchema`.

### 5. Test Suite
- **File**: `tests/unit/test_newsapi_extractor.py`
  - Unit tests using `httpx.MockTransport` / mock handlers:
    - Successful single page fetch & schema parsing.
    - Multi-page pagination traversal up to `totalResults`.
    - Early stop when `max_articles` limit is reached.
    - Rate limit (429) retry backoff handling (success after retry).
    - Rate limit retry exhaustion (`RateLimitError`).
    - Server error (500) retry exhaustion (`NewsAPIError`).
    - Authentication error on 401 (`AuthenticationError`).
    - Empty results handling.
- **File**: `tests/integration/test_newsapi_integration.py`
  - Integration test guarded by `NEWSAPI_API_KEY`.

### 6. Verification
```bash
make test-issue ID=2
make check
```

### 7. Completion & PR
```bash
make finish-issue ID=2
```
