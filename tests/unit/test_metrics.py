"""Unit tests for Prometheus metrics registry and observability (Issue #18)."""

import json
from pathlib import Path

import httpx
import pytest
import yaml

from market_intel.api.app import create_app
from market_intel.core.metrics import (
    CACHE_HITS_TOTAL,
    CACHE_MISSES_TOTAL,
    DB_QUERY_DURATION_SECONDS,
    ENRICHMENT_QUEUE_DEPTH,
    HTTP_REQUEST_DURATION_SECONDS,
    HTTP_REQUESTS_TOTAL,
    PROMETHEUS_REGISTRY,
    WEBSOCKET_ACTIVE_CONNECTIONS,
    generate_metrics_payload,
    record_request_metric,
    set_queue_depth,
    set_websocket_connections,
    track_db_query,
)


@pytest.mark.unit
@pytest.mark.issue_18
def test_metrics_registration() -> None:
    """Ensure all core Prometheus collectors are properly registered."""
    registered_names = set(PROMETHEUS_REGISTRY._names_to_collectors.keys())

    expected_metrics = {
        "http_request_duration_seconds",
        "http_requests_total",
        "db_query_duration_seconds",
        "cache_hits_total",
        "cache_misses_total",
        "enrichment_queue_depth",
        "websocket_active_connections",
    }
    for metric_name in expected_metrics:
        assert metric_name in registered_names, f"Missing metric collector: {metric_name}"

    assert HTTP_REQUEST_DURATION_SECONDS is not None
    assert HTTP_REQUESTS_TOTAL is not None
    assert DB_QUERY_DURATION_SECONDS is not None
    assert CACHE_HITS_TOTAL is not None
    assert CACHE_MISSES_TOTAL is not None
    assert ENRICHMENT_QUEUE_DEPTH is not None
    assert WEBSOCKET_ACTIVE_CONNECTIONS is not None


@pytest.mark.unit
@pytest.mark.issue_18
def test_record_request_metric() -> None:
    """Validate request metric recording updates histogram and counter."""
    record_request_metric(
        method="GET",
        endpoint="/api/v1/test",
        status_code=200,
        duration_seconds=0.042,
    )
    record_request_metric(
        method="POST",
        endpoint="/api/v1/test",
        status_code=500,
        duration_seconds=0.150,
    )

    payload, content_type = generate_metrics_payload()
    payload_text = payload.decode("utf-8")

    assert "text/plain" in content_type
    assert 'http_requests_total{endpoint="/api/v1/test",method="GET",status_code="200"}' in (
        payload_text
    )
    assert 'http_requests_total{endpoint="/api/v1/test",method="POST",status_code="500"}' in (
        payload_text
    )
    assert (
        'http_request_duration_seconds_count{endpoint="/api/v1/test",method="GET",status_code="200"}'
        in payload_text
    )


@pytest.mark.unit
@pytest.mark.issue_18
def test_track_db_query_sync_context_manager() -> None:
    """Verify synchronous track_db_query records latency to histogram."""
    with track_db_query(table="articles", operation="select"):
        # Simulated database work
        _ = sum(range(100))

    payload, _ = generate_metrics_payload()
    payload_text = payload.decode("utf-8")
    assert 'db_query_duration_seconds_count{operation="SELECT",table="articles"}' in payload_text


@pytest.mark.unit
@pytest.mark.issue_18
async def test_track_db_query_async_context_manager() -> None:
    """Verify asynchronous track_db_query records latency to histogram."""
    async with track_db_query(table="enriched_signals", operation="insert"):
        # Simulated async query work
        _ = [i * 2 for i in range(50)]

    payload, _ = generate_metrics_payload()
    payload_text = payload.decode("utf-8")
    expected_metric = 'db_query_duration_seconds_count{operation="INSERT",table="enriched_signals"}'
    assert expected_metric in payload_text


@pytest.mark.unit
@pytest.mark.issue_18
def test_queue_depth_and_websocket_connections_gauges() -> None:
    """Verify queue depth and websocket connection gauges are updated."""
    set_queue_depth(42)
    set_websocket_connections(7)

    payload, _ = generate_metrics_payload()
    payload_text = payload.decode("utf-8")

    assert 'enrichment_queue_depth{queue_name="celery"} 42.0' in payload_text
    assert "websocket_active_connections 7.0" in payload_text

    # Update gauge values
    set_queue_depth(0)
    set_websocket_connections(3)

    payload_updated, _ = generate_metrics_payload()
    payload_updated_text = payload_updated.decode("utf-8")

    assert 'enrichment_queue_depth{queue_name="celery"} 0.0' in payload_updated_text
    assert "websocket_active_connections 3.0" in payload_updated_text


@pytest.mark.unit
@pytest.mark.issue_18
async def test_metrics_endpoint_http_get() -> None:
    """Verify GET /metrics on the application returns Prometheus formatted metrics."""
    app = create_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        # First trigger health endpoint to ensure middleware fires
        health_resp = await client.get("/health")
        assert health_resp.status_code == 200

        # Then query /metrics endpoint
        metrics_resp = await client.get("/metrics")
        assert metrics_resp.status_code == 200
        assert "text/plain" in metrics_resp.headers.get("content-type", "")

        metrics_text = metrics_resp.text
        assert "# HELP http_requests_total" in metrics_text
        assert "# TYPE http_requests_total counter"
        assert "# HELP http_request_duration_seconds" in metrics_text
        assert "# TYPE http_request_duration_seconds histogram"
        assert "# HELP db_query_duration_seconds" in metrics_text
        assert "# HELP cache_hits_total" in metrics_text
        assert "# HELP cache_misses_total" in metrics_text
        assert "# HELP enrichment_queue_depth" in metrics_text
        assert "# HELP websocket_active_connections" in metrics_text
        assert 'endpoint="/health"' in metrics_text


@pytest.mark.unit
@pytest.mark.issue_18
def test_grafana_dashboard_json_spec() -> None:
    """Validate Grafana dashboard JSON schema, structure, panels, and queries."""
    dashboard_path = Path("infra/docker/grafana/dashboards/market_intel.json")
    assert dashboard_path.exists(), f"Dashboard not found at {dashboard_path}"

    with open(dashboard_path, encoding="utf-8") as f:
        data = json.load(f)

    assert data["uid"] == "market-intel-overview"
    assert "Market Intelligence" in data["title"]
    assert "panels" in data
    assert len(data["panels"]) >= 6

    # Collect expressions and panel titles
    titles = [p.get("title") for p in data["panels"] if "title" in p]
    assert any("HTTP Request Throughput" in t for t in titles)
    assert any("HTTP Request Latency" in t for t in titles)
    assert any("Database Query Duration" in t for t in titles)
    assert any("Cache Performance" in t for t in titles)
    assert any("Queue Depth" in t for t in titles)
    assert any("Active WebSocket Connections" in t for t in titles)

    serialized = json.dumps(data)
    assert "http_requests_total" in serialized
    assert "http_request_duration_seconds" in serialized
    assert "db_query_duration_seconds" in serialized
    assert "cache_hits_total" in serialized
    assert "cache_misses_total" in serialized
    assert "enrichment_queue_depth" in serialized
    assert "websocket_active_connections" in serialized


@pytest.mark.unit
@pytest.mark.issue_18
def test_observability_docker_configurations() -> None:
    """Validate Prometheus, Grafana provisioning, and Docker Compose configurations."""
    # Prometheus config
    prom_path = Path("infra/docker/prometheus/prometheus.yml")
    assert prom_path.exists()
    with open(prom_path, encoding="utf-8") as f:
        prom_cfg = yaml.safe_load(f)
    assert "scrape_configs" in prom_cfg
    job_names = [j.get("job_name") for j in prom_cfg["scrape_configs"]]
    assert "market-intel-api" in job_names

    # Grafana datasources
    ds_path = Path("infra/docker/grafana/provisioning/datasources/datasources.yml")
    assert ds_path.exists()
    with open(ds_path, encoding="utf-8") as f:
        ds_cfg = yaml.safe_load(f)
    assert "datasources" in ds_cfg
    assert ds_cfg["datasources"][0]["type"] == "prometheus"

    # Grafana dashboards
    dash_path = Path("infra/docker/grafana/provisioning/dashboards/dashboards.yml")
    assert dash_path.exists()
    with open(dash_path, encoding="utf-8") as f:
        dash_cfg = yaml.safe_load(f)
    assert "providers" in dash_cfg
    assert dash_cfg["providers"][0]["options"]["path"] == "/var/lib/grafana/dashboards"

    # Docker Compose
    compose_path = Path("docker-compose.yml")
    assert compose_path.exists()
    with open(compose_path, encoding="utf-8") as f:
        compose_cfg = yaml.safe_load(f)
    assert "services" in compose_cfg
    assert "prometheus" in compose_cfg["services"]
    assert "grafana" in compose_cfg["services"]
