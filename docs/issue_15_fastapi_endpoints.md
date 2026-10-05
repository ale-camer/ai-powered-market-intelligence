# Issue 15: FastAPI REST endpoints for signals, summaries, and alerts

**Branch:** `feature/issue-15-fastapi-endpoints`  
**Status:** Completed (Ready for Verification)  
**PR:** TBD  
**Milestone:** M4 — Orchestration & Delivery Layer  

---

## Objective

Build `src/market_intel/api/app.py` providing a production-ready asynchronous FastAPI REST API for external querying of market intelligence signals, company summaries, active anomaly alerts, and system health status, complete with OpenAPI documentation and `httpx.AsyncClient` integration tests.

---

## Acceptance Criteria

- [x] **Enriched Signals Endpoint**: `GET /signals?ticker=AAPL&limit=20` returning paginated signals with filtering by ticker and signal type.
- [x] **Company Summary Endpoint**: `GET /summary/{ticker}` returning latest AI-generated executive summaries and metrics (with 404 on missing ticker).
- [x] **Anomaly Alerts Endpoint**: `GET /alerts` returning active statistical and machine-learning anomaly alerts.
- [x] **Health Check Endpoint**: `GET /health` returning service health status, application version, and environment.
- [x] **OpenAPI Documentation**: Automatically generated interactive API documentation accessible at `/docs` and schema at `/openapi.json`.
- [x] **Integration Tests**: Comprehensive test suite using `httpx.AsyncClient` (`pytest -m issue_15`) validating endpoints, query parameter validation, status codes, and JSON payloads.

---

## Implementation Tasks

### 1. Preparation & Branching
```bash
make start-issue ID=15 NAME=fastapi-endpoints
```

### 2. Configuration & Dependencies
- **File**: `pyproject.toml`
  - Add `fastapi>=0.111.0` and `uvicorn>=0.30.0` to `[project.optional-dependencies] orchestration`.
  - Verify marker `issue_15: tests for Issue #15` is registered.
- **File**: `src/market_intel/core/config.py`
  - Add API settings: `api_title`, `api_version`, `api_prefix`.
- **File**: `src/market_intel/core/schemas.py`
  - Define API response schemas: `HealthResponse`, `SignalsQueryResponse`, `CompanySummaryResponse`, `AlertItem`, `AlertsResponse`.
- **File**: `src/market_intel/core/__init__.py`
  - Re-export API schemas.

### 3. FastAPI Application & Endpoints
- **File**: `src/market_intel/api/app.py`
  - Implement FastAPI factory `create_app()` and singleton `app`.
  - Endpoints:
    - `GET /health`
    - `GET /signals` (query params: `ticker`, `signal_type`, `limit`, `offset`)
    - `GET /summary/{ticker}` (path param: `ticker`)
    - `GET /alerts` (query params: `ticker`, `severity`, `limit`)
  - Error handlers for 404, 422, and 500.
  - Dependency injection for database repository and cache.
  - Fallback ASGI compatibility layer ensuring seamless testing in environments with or without FastAPI installed.
- **File**: `src/market_intel/api/__init__.py`
  - Re-export `app` and `create_app`.

### 4. Test Suite
- **File**: `tests/integration/test_api_endpoints.py`
  - Tests marked with `@pytest.mark.integration` and `@pytest.mark.issue_15`.
  - Verify `GET /health` returns 200 and healthy metadata.
  - Verify `GET /signals` pagination, filtering by ticker, and default limit.
  - Verify `GET /signals` validates limits (`limit <= 100`, `offset >= 0`).
  - Verify `GET /summary/{ticker}` returns summary for valid ticker.
  - Verify `GET /summary/{ticker}` returns 404 for unknown ticker.
  - Verify `GET /alerts` returns active anomaly alerts.
  - Verify `/openapi.json` returns valid schema with required endpoints.

### 5. Verification
```bash
make test-issue ID=15
make check
```

### 6. Git & Finish
```bash
make finish-issue ID=15 MSG="feat(delivery): implement FastAPI REST endpoints for signals, summaries, and alerts"
```
