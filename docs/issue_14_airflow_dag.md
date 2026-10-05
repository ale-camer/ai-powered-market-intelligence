# Issue 14: Airflow DAG wiring: ingest → transform → load pipeline

**Branch:** `feature/issue-14-airflow-dag`  
**Status:** In Progress  
**PR:** TBD  
**Milestone:** M4 — Orchestration & Delivery Layer  

---

## Objective

Define the main Apache Airflow DAG in `src/market_intel/pipelines/market_intel_dag.py` (and exposed via `dags/market_intel_daily.py`) to orchestrate the end-to-end market intelligence pipeline: multi-source ingestion (`news`, `filings`, `reddit`, `prices`), NLP/AI enrichment (`transform_enrich`), and storage persistence (`load_to_db`), wired with `@daily` scheduling, SLA miss notifications, and retry policies.

---

## Acceptance Criteria

- [x] **DAG Definition**: Define DAG `market_intel_daily` with schedule `@daily`, default args (retries, retry delays, email alerts), and tag `market-intel`.
- [x] **Task Topology**: Implement 6 distinct tasks:
  - `ingest_news`: Ingest financial articles from NewsAPI.
  - `ingest_filings`: Ingest quarterly/annual filings from SEC EDGAR.
  - `ingest_reddit`: Ingest financial submissions from Reddit.
  - `ingest_prices`: Ingest daily OHLCV prices from Alpha Vantage.
  - `transform_enrich`: Process signals with sentiment, NER, embeddings, and anomaly detection.
  - `load_to_db`: Persist raw models and enriched signals into PostgreSQL/pgvector and update Redis cache.
- [x] **Dependency Wiring**: Upstream ingestion tasks fan-in to transformation, which flows to loader:
  ```python
  [ingest_news, ingest_filings, ingest_reddit, ingest_prices] >> transform_enrich >> load_to_db
  ```
- [x] **SLA Miss Callback**: Custom callback (`sla_miss_alert`) triggered on SLA breaches sending email and logging warnings.
- [x] **DAG Import Tests**: Full test suite (`pytest -m issue_14`) validating DAG structure, schedule, task IDs, upstream/downstream dependencies, SLA callbacks, and task execution callables.

---

## Implementation Tasks

### 1. Preparation & Branching
```bash
make start-issue ID=14 NAME=airflow-dag
```

### 2. Configuration & Dependencies
- **File**: `pyproject.toml`
  - Add `apache-airflow>=2.9.0` to `[project.optional-dependencies] orchestration`.
  - Verify marker `issue_14: tests for Issue #14` is registered.
- **File**: `src/market_intel/core/config.py`
  - Add `airflow_alert_email: str` (default `"alerts@market-intel.local"`).
  - Add `airflow_dag_sla_hours: float` (default `2.0`).

### 3. Pipeline DAG Implementation
- **File**: `src/market_intel/pipelines/market_intel_dag.py`
  - Lightweight shim / Airflow compatibility layer to support environments both with and without Airflow installed.
  - Implement task callables:
    - `run_ingest_news(context)`
    - `run_ingest_filings(context)`
    - `run_ingest_reddit(context)`
    - `run_ingest_prices(context)`
    - `run_transform_enrich(context)`
    - `run_load_to_db(context)`
  - Implement `sla_miss_alert(dag, task_list, blocking_task_list, slas, blocking_tis)`.
  - Construct `market_intel_daily` DAG with dependencies:
    `[ingest_news, ingest_filings, ingest_reddit, ingest_prices] >> transform_enrich >> load_to_db`.
- **File**: `src/market_intel/pipelines/__init__.py`
  - Re-export `market_intel_daily`, task callables, and SLA callback.
- **File**: `dags/market_intel_daily.py`
  - Expose `dag = market_intel_daily` for Airflow scheduler DAG discovery.

### 4. Test Suite
- **File**: `tests/unit/test_market_intel_dag.py`
  - Tests marked with `@pytest.mark.unit` and `@pytest.mark.issue_14`.
  - Verify DAG imports without errors.
  - Verify DAG ID `market_intel_daily` and `@daily` schedule.
  - Verify all 6 task IDs exist in DAG.
  - Verify correct dependency graph (fan-in from 4 ingestion tasks to `transform_enrich`, then `load_to_db`).
  - Verify SLA configuration and callback execution.
  - Verify task callables execute properly.

### 5. Verification
```bash
make test-issue ID=14
make check
```

### 6. Git & Finish
```bash
make finish-issue ID=14 MSG="feat(orchestration): implement Airflow DAG wiring for ingest, transform, and load pipeline"
```
