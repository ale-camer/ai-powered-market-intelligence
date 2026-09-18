# Issue 5: Implement Alpha Vantage financial metrics extractor

**Branch:** `feature/issue-5-alpha-vantage-extractor`  
**Status:** In Progress  
**PR:** TBD  

---

## Objective

Build `src/market_intel/extractors/alpha_vantage.py` to extract price, OHLCV, and fundamentals data using the Alpha Vantage API.

---

## Acceptance Criteria

- [ ] **Endpoints**: Support `TIME_SERIES_DAILY_ADJUSTED`, `OVERVIEW`, and `EARNINGS` endpoints.
- [ ] **Async & Caching**: Use asynchronous requests (via `httpx`) with a basic caching mechanism to avoid redundant API calls.
- [ ] **Rate Limiting**: Enforce a strict rate limit of 5 calls per minute (to respect the free tier restrictions).
- [ ] **Pydantic Schemas**: Extract and return typed `PriceSchema` and `FundamentalsSchema` Pydantic models.
- [ ] **Unit Tests**: Implement unit tests with mocked responses (`pytest -m issue_5`).

---

## Open Questions

> [!WARNING]
> **Caching Strategy**: Para el caché ("caching to avoid redundant API calls"), ¿te parece bien usar un simple diccionario en memoria dentro de la clase `AlphaVantageExtractor` (ej: `self._cache = {}`), o preferís que agregue una dependencia como `aiocache` para manejar TTLs o usar Redis? Voy a asumir un diccionario en memoria por simplicidad, a menos que me indiques lo contrario.

---

## Implementation Tasks

### 1. Preparation and Branching
```bash
make start-issue ID=5 NAME=alpha-vantage-extractor
```

### 2. Configuration & Core Dependencies
- **File**: `pyproject.toml`
  - Ensure `httpx` is in the `ingestion` optional dependencies (it already is).
  - Add `issue_5` marker to pytest configuration.
- **File**: `src/market_intel/core/config.py`
  - `alpha_vantage_api_key` is already present. 
- **File**: `src/market_intel/core/exceptions.py`
  - Add `AlphaVantageError` extending `ExtractorError`.

### 3. Data Models & Schemas
- **File**: `src/market_intel/extractors/schemas.py`
  - Define `PriceSchema` (symbol, date, open, high, low, close, adjusted_close, volume).
  - Define `FundamentalsSchema` (symbol, market_cap, per, ebitda, eps).

### 4. Extractor Implementation
- **File**: `src/market_intel/extractors/alpha_vantage.py`
  - Create `AlphaVantageExtractor` class.
  - Implement async methods: `fetch_daily_adjusted(symbol: str)`, `fetch_overview(symbol: str)`, and `fetch_earnings(symbol: str)`.
  - Implement rate limiting logic (e.g. keeping track of the timestamps of the last 5 calls and sleeping if necessary).
  - Implement basic async caching (e.g. storing responses keyed by endpoint and symbol).
- **File**: `src/market_intel/extractors/__init__.py`
  - Re-export `AlphaVantageExtractor`, `PriceSchema`, and `FundamentalsSchema`.

### 5. Test Suite
- **File**: `tests/unit/test_alpha_vantage_extractor.py`
  - Unit tests using `unittest.mock` to mock `httpx.AsyncClient`.
  - Test rate limiting, caching behavior, and correct parsing into Pydantic schemas.

### 6. Verification
```bash
make test-issue ID=5
make check
```

### 7. Completion & PR
```bash
make finish-issue ID=5
```

### 8. Milestone M1 Completion
```bash
make finish-milestone MILESTONE=M1
```
