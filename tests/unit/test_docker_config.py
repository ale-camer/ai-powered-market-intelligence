"""Unit tests for Docker containerization and orchestration configuration.

Validates multi-stage Dockerfile, .dockerignore security, docker-compose.yml
service definitions, container entrypoint lifecycle script, and Prometheus targets.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest
import yaml

pytestmark = [pytest.mark.unit, pytest.mark.issue_20]


def test_dockerfile_structure_and_security() -> None:
    """Validate Dockerfile follows multi-stage, non-root, and healthcheck best practices."""
    dockerfile_path = Path("Dockerfile")
    assert dockerfile_path.exists(), "Dockerfile must exist at repository root"

    content = dockerfile_path.read_text(encoding="utf-8")

    # Multi-stage validation
    assert "AS builder" in content, "Dockerfile must define a builder stage"
    assert "AS runtime" in content, "Dockerfile must define a runtime stage"

    # Base image validation
    assert "python:3.12-slim" in content, "Must use python:3.12-slim base image"

    # Non-root security validation
    assert "marketintel" in content, "Must create dedicated marketintel system user"
    assert "10001" in content, "Must use explicit UID/GID 10001 for non-root user"
    assert "USER marketintel:marketintel" in content, (
        "Must switch to unprivileged user in runtime stage"
    )

    # Signal handling & entrypoint
    assert "tini" in content, "Must install and use tini for proper signal forwarding"
    assert 'ENTRYPOINT ["/usr/bin/tini", "--", "/entrypoint.sh"]' in content
    assert 'CMD ["api"]' in content

    # Networking & healthcheck
    assert "EXPOSE 8000" in content, "Must expose port 8000"
    assert "HEALTHCHECK" in content, "Must define native container healthcheck"
    assert "/health" in content, "Healthcheck must probe /health endpoint"


def test_dockerignore_rules() -> None:
    """Validate .dockerignore prevents sensitive credentials and cache bloat."""
    dockerignore_path = Path(".dockerignore")
    assert dockerignore_path.exists(), ".dockerignore must exist at repository root"

    rules = [
        line.strip()
        for line in dockerignore_path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]

    # Required exclusions
    critical_exclusions = [
        ".git",
        ".venv",
        "__pycache__/",
        ".pytest_cache/",
        ".ruff_cache/",
        ".mypy_cache/",
        ".coverage",
        ".env",
        "tests/",
        "docs/",
        "artifacts/",
    ]

    for exclusion in critical_exclusions:
        assert exclusion in rules, f"Expected '{exclusion}' in .dockerignore"


def test_docker_compose_services_specification() -> None:
    """Validate full multi-service topology in docker-compose.yml."""
    compose_path = Path("docker-compose.yml")
    assert compose_path.exists(), "docker-compose.yml must exist at repository root"

    with open(compose_path, encoding="utf-8") as f:
        config: dict[str, Any] = yaml.safe_load(f)

    assert "services" in config, "Compose file must define 'services'"
    services = config["services"]

    # 1. PostgreSQL with pgvector
    assert "postgres" in services
    pg = services["postgres"]
    assert "pgvector" in pg["image"]
    assert "healthcheck" in pg
    assert "pg_isready" in str(pg["healthcheck"].get("test", []))
    assert "5432:5432" in pg.get("ports", [])
    assert any("postgres_data" in v for v in pg.get("volumes", []))

    # 2. Redis Cache
    assert "redis" in services
    redis_svc = services["redis"]
    assert "redis:7" in redis_svc["image"]
    assert "healthcheck" in redis_svc
    assert "redis-cli" in str(redis_svc["healthcheck"].get("test", []))
    assert "6379:6379" in redis_svc.get("ports", [])
    assert any("redis_data" in v for v in redis_svc.get("volumes", []))

    # 3. FastAPI REST / WebSocket API
    assert "api" in services
    api = services["api"]
    assert api.get("build", {}).get("dockerfile") == "Dockerfile"
    assert "8000:8000" in api.get("ports", [])
    assert "healthcheck" in api
    assert "/health" in str(api["healthcheck"].get("test", []))

    # Dependency conditions
    api_depends = api.get("depends_on", {})
    assert "postgres" in api_depends
    assert api_depends["postgres"].get("condition") == "service_healthy"
    assert "redis" in api_depends
    assert api_depends["redis"].get("condition") == "service_healthy"

    # 4. Celery Worker
    assert "celery_worker" in services
    worker = services["celery_worker"]
    assert worker.get("command") == ["worker"]
    worker_depends = worker.get("depends_on", {})
    assert "postgres" in worker_depends
    assert "redis" in worker_depends

    # 5. Celery Beat
    assert "celery_beat" in services
    beat = services["celery_beat"]
    assert beat.get("command") == ["beat"]

    # 6. Observability (Prometheus & Grafana)
    assert "prometheus" in services
    assert "grafana" in services
    assert "9090:9090" in services["prometheus"].get("ports", [])
    assert "3000:3000" in services["grafana"].get("ports", [])

    # Named volumes and networks
    assert "volumes" in config
    volumes = config["volumes"]
    for expected_vol in ["postgres_data", "redis_data", "prometheus_data", "grafana_data"]:
        assert expected_vol in volumes, f"Missing volume '{expected_vol}' in docker-compose.yml"

    assert "networks" in config
    assert "market_intel_net" in config["networks"]


def test_entrypoint_script_directives() -> None:
    """Validate entrypoint lifecycle script syntax, permissions, and command dispatch."""
    entrypoint_path = Path("infra/docker/entrypoint.sh")
    assert entrypoint_path.exists(), "infra/docker/entrypoint.sh must exist"
    assert os.access(entrypoint_path, os.X_OK), "entrypoint.sh must be executable"

    script = entrypoint_path.read_text(encoding="utf-8")

    # Strict error handling
    assert "set -euo pipefail" in script

    # Network socket wait loops
    assert "wait_for_service" in script
    assert "socket.create_connection" in script

    # Command dispatch roles
    assert "api)" in script
    assert "worker)" in script
    assert "beat)" in script
    assert "migrate)" in script

    # Migration enforcement
    assert "alembic upgrade head" in script

    # Service executions
    assert "uvicorn market_intel.api.app:app" in script
    assert "celery -A market_intel.core.celery_app worker" in script
    assert "celery -A market_intel.core.celery_app beat" in script
    assert 'exec "$@"' in script


def test_prometheus_scrape_configuration() -> None:
    """Validate Prometheus config targets the containerized API service."""
    prom_path = Path("infra/docker/prometheus/prometheus.yml")
    assert prom_path.exists()

    with open(prom_path, encoding="utf-8") as f:
        prom_cfg: dict[str, Any] = yaml.safe_load(f)

    scrape_configs = prom_cfg.get("scrape_configs", [])
    api_job = next((j for j in scrape_configs if j.get("job_name") == "market-intel-api"), None)
    assert api_job is not None, "Missing market-intel-api scrape job"

    static_configs = api_job.get("static_configs", [])
    assert len(static_configs) > 0
    targets = static_configs[0].get("targets", [])
    assert "api:8000" in targets, "Prometheus must target api:8000 inside Docker network"


def test_makefile_docker_targets() -> None:
    """Validate Makefile provides convenient Docker orchestration targets."""
    makefile_path = Path("Makefile")
    assert makefile_path.exists()

    content = makefile_path.read_text(encoding="utf-8")

    assert "docker-build:" in content
    assert "docker-up:" in content
    assert "docker-down:" in content
    assert "docker-logs:" in content
    assert "docker compose build" in content
    assert "docker compose up -d" in content
    assert "docker compose down" in content
    assert "docker compose logs -f" in content
