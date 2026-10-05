# Issue 18: Prometheus metrics and Grafana observability dashboard

**Branch:** `feature/issue-18-observability`  
**Status:** Completed  
**PR:** TBD  
**Milestone:** M4 — Orchestration & Delivery Layer (FINAL ISSUE OF M4)  

---

## Objective

Instrument the application with `prometheus-client` to capture essential service and system telemetry (HTTP request latency histograms, database query execution times, cache hit/miss ratios, enrichment queue depth, and WebSocket active connections), expose an authenticated/standard `/metrics` endpoint in FastAPI and ASGI via middleware, define an enterprise Grafana dashboard definition in `infra/docker/grafana/dashboards/market_intel.json`, provide a production-ready `docker-compose.yml` running Prometheus and Grafana, and write unit tests under `@pytest.mark.issue_18`.

> **⭐ Milestone Notice**: Issue #18 is the **final issue of Milestone 4 (Orchestration & Delivery Layer)**. Upon finishing and merging this issue into `develop`, Milestone 4 will be ready to be closed to `main` via `make finish-milestone MILESTONE=M4`.

---

## Acceptance Criteria

- [x] **FastAPI Middleware & `/metrics` Endpoint**: Custom ASGI/FastAPI middleware tracking all incoming HTTP requests and exposing a standard Prometheus `/metrics` scrape endpoint returning formatted Prometheus text metrics.
- [x] **Core Observability Metrics**:
  - `http_request_duration_seconds`: Histogram measuring HTTP request latency bucketed across status codes, methods, and endpoints.
  - `http_requests_total`: Counter tracking total processed HTTP requests.
  - `db_query_duration_seconds`: Histogram measuring database query execution duration by operation and table.
  - `cache_hits_total` & `cache_misses_total`: Counters tracking Redis deduplication and hot-path cache performance.
  - `enrichment_queue_depth`: Gauge tracking the depth of queued items awaiting async enrichment in Celery / background queues.
  - `websocket_active_connections`: Gauge tracking currently connected WebSocket alert streaming clients.
- [x] **Grafana Dashboard Definition**: Complete, validated Grafana dashboard JSON in `infra/docker/grafana/dashboards/market_intel.json` with panels for request throughput, latency quantiles (P50, P95, P99), error rates, DB latency, cache hit ratio, queue depth, and WebSocket clients.
- [x] **Docker Compose Observability Stack**: Production-ready `docker-compose.yml` defining interconnected Prometheus and Grafana services with automated datasource and dashboard provisioning.
- [x] **Unit Tests**: Test suite under `@pytest.mark.unit` and `@pytest.mark.issue_18` in `tests/unit/test_metrics.py` validating metric registration, middleware request timing, `/metrics` endpoint scrape output, and dashboard JSON schema integrity.

---

## Implementation Tasks

### 1. Preparation & Branching
```bash
make start-issue ID=18 NAME=observability
```

### 2. Core Metrics Registry & Instrumentation
- **File**: `src/market_intel/core/metrics.py`
  - Centralize Prometheus metrics using `prometheus_client`:
    - `HTTP_REQUEST_DURATION_SECONDS = Histogram("http_request_duration_seconds", "HTTP request latency in seconds", ["method", "endpoint", "status_code"], buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0))`
    - `HTTP_REQUESTS_TOTAL = Counter("http_requests_total", "Total HTTP requests received", ["method", "endpoint", "status_code"])`
    - `DB_QUERY_DURATION_SECONDS = Histogram("db_query_duration_seconds", "Database query execution duration in seconds", ["operation", "table"], buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.0))`
    - `ENRICHMENT_QUEUE_DEPTH = Gauge("enrichment_queue_depth", "Current depth of enrichment tasks in queue", ["queue_name"])`
    - `WEBSOCKET_ACTIVE_CONNECTIONS = Gauge("websocket_active_connections", "Number of currently active WebSocket streaming clients")`
    - Context managers and utility helpers:
      - `track_db_query(operation: str, table: str)`: Context manager timing DB operations.
      - `record_request_metric(method: str, endpoint: str, status_code: int, duration_seconds: float)`: Records request duration and increments counter.
      - `set_queue_depth(queue_name: str, depth: int | float)`: Sets queue gauge value.
      - `generate_metrics_payload() -> tuple[bytes, str]`: Generates latest Prometheus exposition payload and content type.
- **File**: `src/market_intel/core/__init__.py`
  - Re-export metrics and instrumentation utilities.

### 3. Middleware & Delivery Layer Integration
- **File**: `src/market_intel/api/app.py`
  - Implement Prometheus HTTP request timing middleware:
    - Records start time, awaits response, extracts path/endpoint, method, status code, and records to `HTTP_REQUEST_DURATION_SECONDS` and `HTTP_REQUESTS_TOTAL`.
  - Expose `/metrics` route on FastAPI and ASGI app:
    - Returns Prometheus text payload with `CONTENT_TYPE_LATEST`.
  - Update `ConnectionManager` in `src/market_intel/api/websocket.py` to update `WEBSOCKET_ACTIVE_CONNECTIONS` gauge on connect and disconnect.

### 4. Grafana Dashboard & Prometheus Docker Stack
- **File**: `infra/docker/grafana/dashboards/market_intel.json`
  - Production-ready Grafana dashboard containing:
    - Overview KPI stats: Total Requests, Avg Latency, Cache Hit Rate %, Queue Depth, Active WebSockets.
    - Time-series panels: Request Rate by Status Code, Request Latency Quantiles (P50, P95, P99), DB Query Duration by Table, Cache Hits vs Misses, Celery Queue Depth.
- **File**: `infra/docker/prometheus/prometheus.yml`
  - Prometheus scrape config targeting `market-intel-api:8000` with scrape interval 5s.
- **File**: `infra/docker/grafana/provisioning/datasources/datasources.yml`
  - Automated provisioning connecting Grafana to Prometheus datasource.
- **File**: `infra/docker/grafana/provisioning/dashboards/dashboards.yml`
  - Automated dashboard provider loading `market_intel.json`.
- **File**: `docker-compose.yml`
  - Root docker-compose configuration defining `prometheus` and `grafana` services with healthchecks, persistent volumes, and port mappings (`9090:9090` and `3000:3000`).

### 5. Test Suite
- **File**: `tests/unit/test_metrics.py`
  - Marked with `@pytest.mark.unit` and `@pytest.mark.issue_18`.
  - Tests validating:
    - Metrics registration in Prometheus registry.
    - `track_db_query` timing and sample observation.
    - `record_request_metric` recording histograms and counters.
    - `ENRICHMENT_QUEUE_DEPTH` and `WEBSOCKET_ACTIVE_CONNECTIONS` gauge updates.
    - `GET /metrics` HTTP endpoint returning status 200 with standard Prometheus text exposition format.
    - ASGI `/metrics` scope integration.
    - Grafana dashboard JSON schema validity (valid JSON, contains required panels and metrics targets).

### 6. Verification
```bash
make test-issue ID=18
make check
```

### 7. Git & Issue Finish
```bash
make finish-issue ID=18 MSG="feat(observability): implement Prometheus metrics and Grafana dashboard"
```

---

## Final Milestone M4 Closure (End of Milestone 4)

Once Issue #18 is finished and merged to `develop`, **Milestone M4 is 100% complete**.

### M4 Review Checklist:
- [x] Issue #14: Apache Airflow DAG for pipeline orchestration (`feature/issue-14-airflow-dag`)
- [x] Issue #15: FastAPI REST endpoints for signals, summaries, and alerts (`feature/issue-15-fastapi-endpoints`)
- [x] Issue #16: WebSocket streaming for real-time market alerts (`feature/issue-16-websocket-streaming`)
- [x] Issue #17: Celery async task workers and retry logic (`feature/issue-17-celery-workers`)
- [x] Issue #18: Prometheus metrics and Grafana observability dashboard (`feature/issue-18-observability`)

### Command to Close Milestone M4:
```bash
make finish-milestone MILESTONE=M4
```
This command checks out `main`, merges `develop` into `main`, pushes to remote, and tags the milestone release.
