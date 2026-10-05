# Issue 20: Docker containerization and multi-service orchestration

**Branch:** `feature/issue-20-docker-containerization`  
**Status:** Completed  
**PR:** TBD  
**Milestone:** M5 — Quality, Security & Release  

---

## Objective

Deliver a production-ready, security-hardened Docker containerization and multi-service orchestration stack for the AI-Powered Market Intelligence platform. Implement an optimized, multi-stage `Dockerfile` adhering to OCI and container security best practices (non-root unprivileged user, minimal attack surface via slim base image, layer caching, and healthcheck commands), an entrypoint lifecycle manager supporting automatic Alembic database schema migrations, a comprehensive `.dockerignore` file, an expanded `docker-compose.yml` integrating the full service topology (PostgreSQL with `pgvector`, Redis, FastAPI REST/WebSocket server, Celery worker, Prometheus, and Grafana), and a dedicated test suite under `@pytest.mark.issue_20` validating container specifications, Docker Compose service graph integrity, and networking configurations.

---

## Acceptance Criteria

- [x] **Optimized Multi-Stage `Dockerfile` (`Dockerfile` / `infra/docker/Dockerfile`)**:
  - Multi-stage build architecture separating compilation dependencies (wheels, build-essential, libpq) from the lean runtime image.
  - Hardened execution: Non-root application user (`marketintel` with explicit UID/GID `10001:10001`).
  - Standardized directory layout (`/app`, virtual environment at `/opt/venv`, `/app/data`).
  - Signal handling: Configured with `tini` or proper `exec` form entrypoint for deterministic `SIGTERM` / `SIGINT` propagation.
  - Native container healthcheck instructions and exposed service ports (`8000`).
- [x] **Container Entrypoint & Lifespan Script (`infra/docker/entrypoint.sh`)**:
  - Robust bash script supporting commands: `api`, `worker`, `beat`, `migrate`, and arbitrary bash commands.
  - Database connectivity wait-loop verifying PostgreSQL readiness before executing Alembic migrations (`alembic upgrade head`).
  - Clean privilege dropping and parameter forwarding via `exec "$@"`.
- [x] **Docker Ignore Rules (`.dockerignore`)**:
  - Comprehensive exclusion list preventing build context bloat and secret leaks (excluding `.git`, `.venv`, `__pycache__`, `.env`, `.pytest_cache`, `.ruff_cache`, `.mypy_cache`, test artifacts, and IDE configurations).
- [x] **Unified Multi-Service Orchestration (`docker-compose.yml`)**:
  - Full application topology orchestration:
    - `postgres`: Image `pgvector/pgvector:pg16` with persistent volume, healthcheck (`pg_isready`), and resource limits.
    - `redis`: Image `redis:7-alpine` with persistent volume, healthcheck (`redis-cli ping`), and custom memory policy.
    - `api`: FastAPI application service built from `Dockerfile`, healthcheck via `/health`, mapped port `8000:8000`, depends on `postgres` and `redis` with `condition: service_healthy`.
    - `celery_worker`: Background Celery async task processor built from `Dockerfile` with command `worker`, depends on `postgres` and `redis`.
    - `celery_beat`: Periodic task scheduler (optional profile/service).
    - `prometheus`: Scrapes metrics from `api:8000/metrics` and host containers.
    - `grafana`: Visualizes dashboards from provisioned sources and dashboards.
  - Defined bridge network `market_intel_net` and persistent named volumes (`postgres_data`, `redis_data`, `prometheus_data`, `grafana_data`).
- [x] **Prometheus Configuration Alignment (`infra/docker/prometheus/prometheus.yml`)**:
  - Updated scrape configs pointing directly to internal docker-compose service DNS `api:8000` alongside existing host gateway configurations.
- [x] **Developer Ergonomics & Makefile Automation (`Makefile`)**:
  - Makefile targets for container lifecycle: `docker-build`, `docker-up`, `docker-down`, and `docker-logs`.
- [x] **Automated Test Suite (`tests/unit/test_docker_config.py`)**:
  - Unit tests marked `@pytest.mark.unit` and `@pytest.mark.issue_20`:
    - Validates `Dockerfile` syntax, multi-stage structure, non-root user configuration, and security practices.
    - Validates `.dockerignore` patterns ensure secrets and cache folders are excluded.
    - Validates `docker-compose.yml` schema structure, service names, healthcheck commands, volume mounts, dependency conditions, and port bindings.
    - Validates `infra/docker/entrypoint.sh` syntax and executable permissions.

---

## Implementation Tasks

### 1. Preparation & Branching
```bash
make start-issue ID=20 NAME=docker-containerization
```

### 2. Multi-Stage Dockerfile & Container Scaffolding
- **File**: `Dockerfile`
  - Builder stage:
    - Base on `python:3.12-slim` (or `python:3.12-bookworm`).
    - Install system build prerequisites (`build-essential`, `libpq-dev`, `curl`).
    - Create virtualenv at `/opt/venv` and install package with wheels (`pip install --no-cache-dir .[all]`).
  - Runtime stage:
    - Base on clean `python:3.12-slim`.
    - Install minimal runtime libraries (`libpq5`, `curl`, `tini`).
    - Create non-root system group and user (`marketintel` UID `10001`).
    - Copy virtualenv from builder stage (`/opt/venv`).
    - Copy application source (`src/`, `alembic.ini`, `entrypoint.sh`).
    - Set environment variables (`PATH="/opt/venv/bin:$PATH"`, `PYTHONUNBUFFERED=1`, `PYTHONDONTWRITEBYTECODE=1`).
    - Configure `HEALTHCHECK` probing `http://localhost:8000/health`.
    - Set `ENTRYPOINT ["/entrypoint.sh"]` and default `CMD ["api"]`.
- **File**: `.dockerignore`
  - Exclude `.git`, `.venv`, `.mypy_cache`, `.pytest_cache`, `.ruff_cache`, `tests`, `docs`, `artifacts`, `*.log`, `.env`, and credentials.
- **File**: `infra/docker/entrypoint.sh`
  - Shell script with `set -euo pipefail`.
  - Database ping helper loop checking `$POSTGRES_HOST:$POSTGRES_PORT`.
  - Command routing:
    - `api`: Run migrations `alembic upgrade head` and launch `uvicorn market_intel.api.app:app --host 0.0.0.0 --port 8000`.
    - `worker`: Launch `celery -A market_intel.core.celery_app worker --loglevel=info -Q high_priority,default,dlq`.
    - `beat`: Launch `celery -A market_intel.core.celery_app beat --loglevel=info`.
    - `migrate`: Run `alembic upgrade head`.
    - Default: `exec "$@"`.

### 3. Orchestration Configuration (`docker-compose.yml`)
- **File**: `docker-compose.yml`
  - Expand existing file to declare complete topology:
    - `postgres`:
      - Image: `pgvector/pgvector:pg16`
      - Environment: matching `.env.example` defaults (`POSTGRES_DB=market_intel`, `POSTGRES_USER=market_intel_user`, `POSTGRES_PASSWORD=market_intel_password`)
      - Ports: `5432:5432`
      - Healthcheck: `pg_isready -U $$POSTGRES_USER -d $$POSTGRES_DB`
      - Volume: `postgres_data:/var/lib/postgresql/data`
    - `redis`:
      - Image: `redis:7-alpine`
      - Ports: `6379:6379`
      - Healthcheck: `redis-cli ping`
      - Volume: `redis_data:/data`
    - `api`:
      - Build: `.` with Dockerfile
      - Ports: `8000:8000`
      - Environment: pointing to `postgres` and `redis` services
      - Depends on: `postgres` (condition: service_healthy), `redis` (condition: service_healthy)
      - Healthcheck: `curl -f http://localhost:8000/health || exit 1`
    - `celery_worker`:
      - Build: `.` with Dockerfile
      - Command: `worker`
      - Depends on: `postgres` (condition: service_healthy), `redis` (condition: service_healthy)
    - `prometheus` & `grafana`:
      - Keep existing configuration from Issue 18, ensuring `prometheus.yml` scrapes both `api:8000` and host.
- **File**: `infra/docker/prometheus/prometheus.yml`
  - Update scrape target `api` to reference `api:8000` directly inside the Docker bridge network.

### 4. Makefile Integration
- **File**: `Makefile`
  - Add developer convenience targets:
    ```makefile
    .PHONY: docker-build
    docker-build: ## Build Docker images
    	docker compose build

    .PHONY: docker-up
    docker-up: ## Start all services in background
    	docker compose up -d

    .PHONY: docker-down
    docker-down: ## Stop all running containers
    	docker compose down

    .PHONY: docker-logs
    docker-logs: ## Follow container logs
    	docker compose logs -f
    ```

### 5. Automated Unit Tests (`tests/unit/test_docker_config.py`)
- **File**: `tests/unit/test_docker_config.py`
  - Mark tests `@pytest.mark.unit` and `@pytest.mark.issue_20`:
    - `test_dockerfile_structure_and_security`: Validates presence of multi-stage build (`AS builder`), non-root `USER`, exposed port 8000, and minimal base image.
    - `test_dockerignore_exclusions`: Asserts sensitive files (`.env`, `.git`, `.venv`, `.pytest_cache`, credentials) are ignored.
    - `test_docker_compose_services_specification`: Parses `docker-compose.yml` with PyYAML and asserts services (`postgres`, `redis`, `api`, `celery_worker`, `prometheus`, `grafana`), healthchecks, network bindings, and volume persistency.
    - `test_entrypoint_script_directives`: Validates syntax, execution modes (`api`, `worker`, `beat`, `migrate`), database connection probe loop, and `exec` dispatching.
    - `test_prometheus_scrape_config_includes_api`: Verifies Prometheus targets include `api:8000`.

### 6. Verification & Quality Gates
```bash
make test-issue ID=20
.venv/bin/pytest tests/ --cov=src --cov-fail-under=80
make check
```

### 7. Git & Issue Finish
```bash
make finish-issue ID=20 MSG="feat(infra): implement production Docker containerization and multi-service orchestration"
```
