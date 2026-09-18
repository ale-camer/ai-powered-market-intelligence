# Issue 3: Implement SEC EDGAR XBRL extractor for financial filings

**Branch:** `feature/issue-3-sec-edgar-extractor`  
**Status:** In Progress  
**PR:** TBD  

---

## Objective

Build a `SecEdgarExtractor` in `src/market_intel/extractors/sec_edgar.py` capable of fetching 10-K and 10-Q filings via the SEC EDGAR full-text search API, parsing XBRL inline data (revenue, EPS, assets), respecting SEC rate limits (10 requests/sec, custom User-Agent), and returning typed `FilingSchema` Pydantic models.

---

## Acceptance Criteria

- [ ] **EDGAR API Integration**: Fetch 10-K and 10-Q filings via EDGAR full-text search API.
- [ ] **XBRL Parsing**: Parse inline XBRL data (revenue, EPS, assets) into structured records.
- [ ] **Rate Limiting & Compliance**: Respect SEC rate limits (maximum 10 requests/sec) and pass a valid `User-Agent` header.
- [ ] **Pydantic Schemas**: Returns typed list of `FilingSchema` Pydantic models.
- [ ] **Unit Tests**: Unit tests with fixture XML/XBRL files (`pytest -m issue_3`).

---

## Implementation Tasks

### 1. Preparation and Branching
```bash
make start-issue ID=3 NAME=sec-edgar-extractor
```

### 2. Core Exceptions & Configuration
- **File**: `pyproject.toml`
  - Ensure XML parser dependencies like `beautifulsoup4` and `lxml` are added to `[project.optional-dependencies] ingestion` if needed.
  - Add `issue_3` marker to `[tool.pytest.ini_options]`.
- **File**: `src/market_intel/core/exceptions.py`
  - Use existing `RateLimitError` or define specific SEC errors if needed.

### 3. Data Models & Schemas
- **File**: `src/market_intel/extractors/schemas.py`
  - Define `FinancialMetricsSchema` (revenue, eps, assets).
  - Define `FilingSchema(cik, company_name, filing_type, filing_date, period_of_report, metrics: FinancialMetricsSchema)`.

### 4. SEC EDGAR Extractor Implementation
- **File**: `src/market_intel/extractors/sec_edgar.py`
  - Implement `SecEdgarExtractor` with configuration for `User-Agent`.
  - Implement rate limiting logic (e.g., using `asyncio.sleep` to enforce max 10 req/s).
  - Implement `fetch_filings(query, form_type="10-K", **params)`.
  - Implement XBRL parsing logic using `beautifulsoup4`.
- **File**: `src/market_intel/extractors/__init__.py`
  - Re-export `SecEdgarExtractor` and `FilingSchema`.

### 5. Test Suite
- **File**: `tests/fixtures/`
  - Create dummy `sec_10k_sample.xml` and `sec_10q_sample.htm` with valid XBRL snippets.
- **File**: `tests/unit/test_sec_edgar_extractor.py`
  - Unit tests using mocked HTTP responses and local fixtures:
    - Successful parsing of XBRL data from local fixtures.
    - Rate limiter enforcement.
    - Handling of invalid or missing XBRL fields.

### 6. Verification
```bash
make test-issue ID=3
make check
```

### 7. Completion & PR
```bash
make finish-issue ID=3
```
