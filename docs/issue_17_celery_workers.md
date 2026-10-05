# Issue 17: Celery async task workers and retry logic

**Branch:** `feature/issue-17-celery-workers`  
**Status:** In Progress (Ready for Verification)  
**PR:** TBD  
**Milestone:** M4 — Orchestration & Delivery Layer  

---

## Objective

Configure Celery in `src/market_intel/core/celery_app.py` for asynchronous background task execution, integrating Redis as message broker and PostgreSQL as result backend, defining core asynchronous background tasks (`enrich_article_task`, `generate_embedding_task`, `send_alert_task`), configuring exponential backoff retry policies (max 3 retries, base delay 60s), implementing Dead Letter Queue (DLQ) routing for permanently failed tasks, and providing a comprehensive unit test suite marked `@pytest.mark.issue_17`.

---

## Acceptance Criteria

- [x] **Celery App Configuration**: Celery application instance configured with Redis broker (`settings.redis_url`) and PostgreSQL result backend (`settings.sync_postgres_url` / SQLAlchemy result backend), with dual-engine fallback ensuring offline execution and testing.
- [x] **Background Tasks**:
  - `enrich_article_task`: Asynchronously enriches financial articles with sentiment analysis and financial entity recognition (NER).
  - `generate_embedding_task`: Asynchronously computes 1536-dimensional vector embeddings for financial texts.
  - `send_alert_task`: Asynchronously delivers market anomaly alerts to WebSocket clients or notification channels.
- [x] **Exponential Backoff Retry**: Automatic retry on transient exceptions with max 3 retries, base delay of 60 seconds, and exponential backoff progression (60s, 120s, 240s).
- [x] **Dead Letter Queue (DLQ)**: Tasks failing permanently after exhausting retries are routed to a dedicated DLQ queue (`market_intel.dlq`) with structured failure metadata (task ID, arguments, exception details, timestamp).
- [x] **Unit Tests**: Comprehensive unit tests under `@pytest.mark.unit` and `@pytest.mark.issue_17` testing task execution, mock Celery worker interactions, retry backoff logic, and DLQ routing.

---

## Implementation Tasks

### 1. Preparation & Branching
```bash
make start-issue ID=17 NAME=celery-workers
```

### 2. Dependencies & Configuration
- **File**: `pyproject.toml`
  - Add `celery>=5.3.0` to `[project.optional-dependencies] orchestration`.
  - Verify test marker `issue_17` is registered under `markers`.
- **File**: `src/market_intel/core/config.py`
  - Add Celery settings to `Settings`:
    - `celery_broker_url: str = Field(default="redis://localhost:6379/0", alias="CELERY_BROKER_URL")`
    - `celery_result_backend: str | None = Field(default=None, alias="CELERY_RESULT_BACKEND")`
    - `celery_default_queue: str = Field(default="celery", alias="CELERY_DEFAULT_QUEUE")`
    - `celery_dlq_name: str = Field(default="market_intel.dlq", alias="CELERY_DLQ_NAME")`
    - `celery_max_retries: int = Field(default=3, alias="CELERY_MAX_RETRIES")`
    - `celery_retry_base_delay: int = Field(default=60, alias="CELERY_RETRY_BASE_DELAY")`
- **File**: `src/market_intel/core/__init__.py`
  - Re-export Celery tasks and app instance.

### 3. Celery App, Tasks & DLQ Architecture
- **File**: `src/market_intel/core/celery_app.py`
  - Create and configure Celery app:
    - Broker: Redis URL (`settings.redis_url`).
    - Result Backend: PostgreSQL database connection string (`db+postgresql://...`).
    - Task serializer, result serializer, and accept_content configured for JSON.
    - UTC timezone enabled.
    - Queue configuration for default queue and DLQ queue (`market_intel.dlq`).
  - Implement Dead Letter Queue routing:
    - Custom task failure callback / `on_failure` handler routing failed tasks after max retries to `market_intel.dlq`.
    - DLQ payload inspection helper `route_to_dlq(task_id, task_name, args, kwargs, exc_info)`.
  - Define Tasks with Exponential Backoff:
    - `enrich_article_task(article_data: Mapping[str, object] | str)`: Enriches article using `SentimentAnalyzer` and `FinancialNERExtractor`.
    - `generate_embedding_task(text_or_article: Mapping[str, object] | str, model: str | None = None)`: Computes vector embeddings using `DocumentTransformer`.
    - `send_alert_task(alert_data: Mapping[str, object] | str)`: Dispatches market anomaly alert via `ConnectionManager` or notification channel.
  - Dual-engine fallback:
    - Provide a robust shim `CeleryFallback` that mimics `celery.Celery` and `@task` semantics when `celery` is not installed or when running in lightweight unit test environments.

### 4. Test Suite
- **File**: `tests/unit/test_celery_tasks.py`
  - Marked with `@pytest.mark.unit` and `@pytest.mark.issue_17`.
  - Tests for:
    - Celery configuration parameters (broker, result backend, serialization, queues).
    - `enrich_article_task` execution with valid and invalid article payloads.
    - `generate_embedding_task` execution returning vector dimensions and token counts.
    - `send_alert_task` execution delivering alert payloads.
    - Retry policy with exponential backoff on transient errors (1st, 2nd, 3rd retry).
    - Routing to Dead Letter Queue (DLQ) when `MaxRetriesExceededError` or failure limit is reached.
    - Custom failure handler and DLQ message structure validation.

### 5. Verification
```bash
make test-issue ID=17
make check
```

### 6. Git & Finish
```bash
make finish-issue ID=17 MSG="feat(orchestration): implement Celery async task workers and retry logic"
```
