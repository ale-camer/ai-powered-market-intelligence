# Issue 19: Full test suite: unit, integration, and e2e test coverage

**Branch:** `feature/issue-19-full-test-suite`  
**Status:** Completed  
**PR:** TBD  
**Milestone:** M5 — Quality, Security & Release (FIRST ISSUE OF M5)  

---

## Objective

Achieve $\ge 80\%$ test coverage across all modules with comprehensive unit, integration, and end-to-end (E2E) tests. Ensure all modules in `src/market_intel` are properly covered with mocks, integrate database and caching flows in integration tests, implement a full pipeline E2E smoke test (`ingest → enrich → store → serve`), enforce `--cov-fail-under=80`, and verify that all individual issue test markers (`pytest -m issue_N`) pass.

---

## Acceptance Criteria

- [x] **Unit Tests Expansion (`tests/unit/`)**: Ensure all modules achieve $\ge 80\%$ statement coverage (specifically expanding unit coverage for `sec_edgar.py`, `sentiment.py`, and `loaders/migrations/env.py`).
- [x] **Integration Tests Suite (`tests/integration/`)**: Integration tests validating the interplay between components:
  - Database persistence + vector similarity retrieval using async repository and SQLite/PostgreSQL.
  - Redis cache operations and deduplication handling (`DeduplicationCache`).
  - Celery background task worker dispatch, retry logic, and DLQ routing.
  - FastAPI REST endpoints and WebSocket alert subscriptions.
- [x] **End-to-End Pipeline Smoke Test (`tests/e2e/`)**:
  - Implemented in `tests/e2e/test_pipeline_e2e.py` marked `@pytest.mark.e2e` and `@pytest.mark.issue_19`.
  - Simulates the complete end-to-end data lifecycle:
    1. **Ingest**: Multi-source data generation (Articles, SEC Filings, Reddit Posts, Price Data).
    2. **Transform & Enrich**: FinBERT/GPT-4o sentiment analysis, financial NER extraction, OpenAI vector embedding generation, and anomaly detection.
    3. **Load**: Storage in relational tables and vector-indexed signals repository.
    4. **Serve & Observe**: REST API query validation (`/signals`, `/summaries`, `/alerts`), WebSocket live alert broadcast verification, and Prometheus `/metrics` scrape verification.
- [x] **Enforced Coverage Threshold**:
  - `pytest tests/ --cov=src --cov-fail-under=80` succeeds without failures.
- [x] **All Issue Markers Passing**:
  - Verification that test suites for all completed issues (`issue_1` through `issue_19`) continue to pass without regressions.

---

## Implementation Tasks

### 1. Preparation & Branching
```bash
make start-issue ID=19 NAME=full-test-suite
```

### 2. Unit Test Coverage Hardening (`tests/unit/`)
- **File**: `tests/unit/test_sec_edgar_extractor.py`
  - Add tests for filing parsing edge cases (XML/XBRL parsing, malformed HTML, empty response handling, rate limit backoff exhaustion).
  - Target: Elevate `src/market_intel/extractors/sec_edgar.py` coverage from 78% to $\ge 85\%$.
- **File**: `tests/unit/test_sentiment_pipeline.py`
  - Add tests for HuggingFace FinBERT tokenization corner cases, batch inference slicing, and fallback error branches.
  - Target: Elevate `src/market_intel/transformers/sentiment.py` coverage from 76% to $\ge 85\%$.
- **File**: `tests/unit/test_postgres_schema.py`
  - Add test coverage for `loaders/migrations/env.py` helper functions (offline mode, target metadata inspection).

### 3. Integration Tests Hardening (`tests/integration/`)
- **File**: `tests/integration/test_storage_cache_integration.py`
  - Validate async database transactions, rollback on error, and vector search similarity querying via `EmbeddingRepository`.
  - Validate `DeduplicationCache` with Redis backend (mocked/in-memory Redis client) testing TTL expiration, key hashing, and metrics counters (`cache_hits_total`, `cache_misses_total`).
- **File**: `tests/integration/test_celery_pipeline_integration.py`
  - Validate end-to-end Celery async execution chaining: article ingestion $\to$ `enrich_article_task` $\to$ `generate_embedding_task` $\to$ `send_alert_task`.
  - Validate Dead Letter Queue (DLQ) message retrieval and queue inspection.

### 4. Full Pipeline End-to-End Test (`tests/e2e/test_pipeline_e2e.py`)
- **File**: `tests/e2e/test_pipeline_e2e.py`
  - Create asynchronous E2E smoke test covering the entire system:
    - Step 1: Mock ingestion of raw financial data (Tech sector news + price volatility).
    - Step 2: Run enrichment pipeline (Sentiment scoring + Cashtag/Org NER + 1536-dim embedding generation + Anomaly volume spike detection).
    - Step 3: Persist enriched records to database session.
    - Step 4: Dispatch alert via WebSocket adapter and assert broadcast receipt.
    - Step 5: Query REST API (`GET /signals?symbol=NVDA`, `GET /summaries/NVDA`, `GET /alerts`) and verify responses.
    - Step 6: Query `GET /metrics` and verify Prometheus counters/histograms were incremented.

### 5. Verification & Coverage Report
```bash
make test-issue ID=19
.venv/bin/pytest tests/ --cov=src --cov-fail-under=80
make check
```

### 6. Git & Issue Finish
```bash
make finish-issue ID=19 MSG="test(core): implement full test suite across unit, integration, and e2e layers"
```
