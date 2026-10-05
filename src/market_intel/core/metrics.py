"""Centralized Prometheus metrics registry and telemetry instrumentation helpers."""

import time
from collections.abc import Sequence

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    REGISTRY,
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)

from market_intel.core.logger import get_logger

logger = get_logger("market_intel.core.metrics")


def _get_or_create_histogram(
    name: str,
    documentation: str,
    labelnames: Sequence[str] = (),
    buckets: Sequence[float] = Histogram.DEFAULT_BUCKETS,
    registry: CollectorRegistry = REGISTRY,
) -> Histogram:
    """Retrieve existing Histogram from registry or register a new one safely."""
    collector = registry._names_to_collectors.get(name)
    if isinstance(collector, Histogram):
        return collector
    return Histogram(
        name,
        documentation,
        labelnames=labelnames,
        buckets=buckets,
        registry=registry,
    )


def _get_or_create_counter(
    name: str,
    documentation: str,
    labelnames: Sequence[str] = (),
    registry: CollectorRegistry = REGISTRY,
) -> Counter:
    """Retrieve existing Counter from registry or register a new one safely."""
    collector = registry._names_to_collectors.get(name)
    if isinstance(collector, Counter):
        return collector
    return Counter(
        name,
        documentation,
        labelnames=labelnames,
        registry=registry,
    )


def _get_or_create_gauge(
    name: str,
    documentation: str,
    labelnames: Sequence[str] = (),
    registry: CollectorRegistry = REGISTRY,
) -> Gauge:
    """Retrieve existing Gauge from registry or register a new one safely."""
    collector = registry._names_to_collectors.get(name)
    if isinstance(collector, Gauge):
        return collector
    return Gauge(
        name,
        documentation,
        labelnames=labelnames,
        registry=registry,
    )


# ──────────────────────────────────────────────────────────────────────────────
# Core Metrics Registry
# ──────────────────────────────────────────────────────────────────────────────

HTTP_REQUEST_DURATION_SECONDS = _get_or_create_histogram(
    name="http_request_duration_seconds",
    documentation="HTTP request latency in seconds",
    labelnames=["method", "endpoint", "status_code"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)

HTTP_REQUESTS_TOTAL = _get_or_create_counter(
    name="http_requests_total",
    documentation="Total HTTP requests received",
    labelnames=["method", "endpoint", "status_code"],
)

DB_QUERY_DURATION_SECONDS = _get_or_create_histogram(
    name="db_query_duration_seconds",
    documentation="Database query execution duration in seconds",
    labelnames=["operation", "table"],
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.0),
)

ENRICHMENT_QUEUE_DEPTH = _get_or_create_gauge(
    name="enrichment_queue_depth",
    documentation="Current depth of enrichment tasks in queue",
    labelnames=["queue_name"],
)

WEBSOCKET_ACTIVE_CONNECTIONS = _get_or_create_gauge(
    name="websocket_active_connections",
    documentation="Number of currently active WebSocket streaming clients",
)

CACHE_HITS_TOTAL = _get_or_create_counter(
    name="cache_hits_total",
    documentation="Total number of cache hits in deduplication layer",
    labelnames=["cache_name"],
)

CACHE_MISSES_TOTAL = _get_or_create_counter(
    name="cache_misses_total",
    documentation="Total number of cache misses in deduplication layer",
    labelnames=["cache_name"],
)


# ──────────────────────────────────────────────────────────────────────────────
# Telemetry Helper Functions & Context Managers
# ──────────────────────────────────────────────────────────────────────────────


def record_request_metric(
    method: str,
    endpoint: str,
    status_code: int,
    duration_seconds: float,
) -> None:
    """Record HTTP request duration and count metrics.

    Args:
        method: HTTP method (e.g. GET, POST).
        endpoint: Request path or route pattern (e.g. /signals).
        status_code: HTTP response status code (e.g. 200).
        duration_seconds: Elapsed request time in seconds.
    """
    clean_method = method.upper()
    clean_code = str(status_code)
    HTTP_REQUEST_DURATION_SECONDS.labels(
        method=clean_method,
        endpoint=endpoint,
        status_code=clean_code,
    ).observe(max(0.0, duration_seconds))

    HTTP_REQUESTS_TOTAL.labels(
        method=clean_method,
        endpoint=endpoint,
        status_code=clean_code,
    ).inc()


PROMETHEUS_REGISTRY = REGISTRY


class DBQueryTracker:
    """Synchronous and asynchronous context manager tracking database query execution time."""

    def __init__(
        self,
        operation: str = "SELECT",
        table: str = "",
        table_name: str | None = None,
    ) -> None:
        self.operation = (operation or "SELECT").upper()
        self.table = (table_name or table or "unknown").lower()
        self.start_time: float = 0.0

    def __enter__(self) -> "DBQueryTracker":
        self.start_time = time.perf_counter()
        return self

    def __exit__(
        self,
        exc_type: object,
        exc_val: object,
        exc_tb: object,
    ) -> None:
        elapsed = time.perf_counter() - self.start_time
        DB_QUERY_DURATION_SECONDS.labels(
            operation=self.operation,
            table=self.table,
        ).observe(max(0.0, elapsed))

    async def __aenter__(self) -> "DBQueryTracker":
        return self.__enter__()

    async def __aexit__(
        self,
        exc_type: object,
        exc_val: object,
        exc_tb: object,
    ) -> None:
        self.__exit__(exc_type, exc_val, exc_tb)


def track_db_query(
    operation: str = "SELECT",
    table: str = "",
    table_name: str | None = None,
) -> DBQueryTracker:
    """Measure execution duration of database queries via sync/async context manager.

    Args:
        operation: SQL operation type (e.g. SELECT, INSERT, UPDATE).
        table: Name of database table being queried.
        table_name: Optional alias for table parameter.

    Returns:
        DBQueryTracker context manager instance.
    """
    return DBQueryTracker(operation=operation, table=table, table_name=table_name)


def set_queue_depth(
    depth_or_queue: int | float | str,
    depth: int | float | None = None,
    queue_name: str = "celery",
) -> None:
    """Set the gauge value for enrichment queue depth.

    Supports either:
        set_queue_depth(42)  # depth=42, default queue='celery'
        set_queue_depth("my_queue", 42)
        set_queue_depth(42, queue_name="my_queue")

    Args:
        depth_or_queue: Either numeric depth count or string queue name.
        depth: Numeric depth count if first argument was string queue name.
        queue_name: Target queue name if first argument was numeric.
    """
    if isinstance(depth_or_queue, (int, float)):
        val = float(depth_or_queue)
        q = queue_name
    else:
        q = str(depth_or_queue)
        val = float(depth if depth is not None else 0.0)
    ENRICHMENT_QUEUE_DEPTH.labels(queue_name=q).set(max(0.0, val))


def set_websocket_connections(count: int) -> None:
    """Set the current count of active WebSocket streaming connections.

    Args:
        count: Number of active client connections.
    """
    WEBSOCKET_ACTIVE_CONNECTIONS.set(max(0.0, float(count)))


def increment_websocket_connections(delta: int = 1) -> None:
    """Increment the active WebSocket connections gauge.

    Args:
        delta: Amount to increment (default: 1).
    """
    WEBSOCKET_ACTIVE_CONNECTIONS.inc(delta)


def decrement_websocket_connections(delta: int = 1) -> None:
    """Decrement the active WebSocket connections gauge.

    Args:
        delta: Amount to decrement (default: 1).
    """
    WEBSOCKET_ACTIVE_CONNECTIONS.dec(delta)


def generate_metrics_payload(
    registry: CollectorRegistry = REGISTRY,
) -> tuple[bytes, str]:
    """Generate latest Prometheus formatted metrics payload.

    Args:
        registry: Target CollectorRegistry to export (default: global REGISTRY).

    Returns:
        Tuple containing binary payload and content-type header string.
    """
    payload = generate_latest(registry)
    return payload, CONTENT_TYPE_LATEST
