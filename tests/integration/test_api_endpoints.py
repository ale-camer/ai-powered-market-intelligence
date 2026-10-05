"""Integration tests for FastAPI REST endpoints (Issue #15)."""

import uuid
from datetime import UTC, datetime

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from market_intel.api.app import MarketIntelASGIApp, create_app
from market_intel.core.schemas import (
    AlertsResponse,
    CompanySummaryResponse,
    HealthResponse,
    SignalsQueryResponse,
)
from market_intel.loaders.database import Base, get_async_session_factory
from market_intel.loaders.models import EnrichedSignalModel


@pytest.fixture
async def session_factory() -> async_sessionmaker[AsyncSession]:
    """Create in-memory SQLite database and seed initial test records."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
        echo=False,
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = get_async_session_factory(engine)

    async with factory() as session:
        # Seed 1: AAPL sentiment signal (latest summary for AAPL)
        sig_aapl_sentiment = EnrichedSignalModel(
            id=uuid.uuid4(),
            source_type="article",
            symbol="AAPL",
            signal_type="sentiment",
            sentiment_score=0.88,
            sentiment_label="bullish",
            confidence=0.94,
            summary="Apple posted record quarterly revenue beating analyst expectations.",
            entities={"companies": ["Apple Inc."], "tickers": ["AAPL"]},
            timestamp=datetime(2026, 9, 24, 12, 0, tzinfo=UTC),
        )
        # Seed 2: AAPL anomaly signal
        sig_aapl_anomaly = EnrichedSignalModel(
            id=uuid.uuid4(),
            source_type="pipeline",
            symbol="AAPL",
            signal_type="anomaly",
            sentiment_score=None,
            sentiment_label="high",
            confidence=0.98,
            summary="Unusual volume spike observed during pre-market trading.",
            entities={
                "metric": "volume",
                "method": "zscore",
                "score": 3.65,
                "threshold": 3.0,
            },
            timestamp=datetime(2026, 9, 24, 10, 0, tzinfo=UTC),
        )
        # Seed 3: MSFT sentiment signal (latest summary for MSFT)
        sig_msft_sentiment = EnrichedSignalModel(
            id=uuid.uuid4(),
            source_type="filing",
            symbol="MSFT",
            signal_type="sentiment",
            sentiment_score=0.55,
            sentiment_label="neutral",
            confidence=0.82,
            summary="Microsoft expanded Azure cloud partnership with enterprise customers.",
            entities={"companies": ["Microsoft"], "tickers": ["MSFT"]},
            timestamp=datetime(2026, 9, 24, 12, 0, tzinfo=UTC),
        )
        # Seed 4: MSFT anomaly signal
        sig_msft_anomaly = EnrichedSignalModel(
            id=uuid.uuid4(),
            source_type="pipeline",
            symbol="MSFT",
            signal_type="anomaly",
            sentiment_score=None,
            sentiment_label="medium",
            confidence=0.85,
            summary="Cloud division margin variance detected.",
            entities={"metric": "margin", "method": "iqr", "score": 2.20},
            timestamp=datetime(2026, 9, 24, 11, 0, tzinfo=UTC),
        )
        # Seed 5 to 29: GOOGL signals for pagination testing (25 signals)
        googl_signals = [
            EnrichedSignalModel(
                id=uuid.uuid4(),
                source_type="article",
                symbol="GOOGL",
                signal_type="sentiment",
                sentiment_score=0.70,
                sentiment_label="bullish",
                confidence=0.85,
                summary=f"Google releases next-gen AI model benchmark {i}.",
                entities={"companies": ["Alphabet"], "tickers": ["GOOGL"]},
                timestamp=datetime(2026, 9, 24, 12, i, tzinfo=UTC),
            )
            for i in range(25)
        ]

        session.add_all(
            [
                sig_aapl_sentiment,
                sig_aapl_anomaly,
                sig_msft_sentiment,
                sig_msft_anomaly,
                *googl_signals,
            ]
        )
        await session.commit()

    try:
        yield factory
    finally:
        await engine.dispose()


@pytest.fixture
def app_instance(session_factory: async_sessionmaker[AsyncSession]) -> MarketIntelASGIApp:
    """Create MarketIntelASGIApp instance bound to test database."""
    return create_app(session_factory=session_factory)


@pytest.fixture
async def client(app_instance: MarketIntelASGIApp) -> httpx.AsyncClient:
    """Provide httpx.AsyncClient configured with ASGITransport."""
    transport = httpx.ASGITransport(app=app_instance)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as test_client:
        yield test_client


@pytest.mark.integration
@pytest.mark.issue_15
async def test_health_endpoint(client: httpx.AsyncClient) -> None:
    """Validate GET /health returns 200 with system health metadata."""
    response = await client.get("/health")
    assert response.status_code == 200

    data = response.json()
    validated = HealthResponse.model_validate(data)
    assert validated.status == "healthy"
    assert validated.version
    assert validated.environment
    assert validated.details is not None
    assert validated.details.get("database") == "connected"
    assert validated.details.get("cache") == "connected"


@pytest.mark.integration
@pytest.mark.issue_15
async def test_signals_filtering_by_ticker(client: httpx.AsyncClient) -> None:
    """Validate GET /signals?ticker=AAPL filters results properly."""
    response = await client.get("/signals?ticker=AAPL")
    assert response.status_code == 200

    data = response.json()
    validated = SignalsQueryResponse.model_validate(data)
    assert validated.total == 2
    assert len(validated.items) == 2
    for item in validated.items:
        assert item.symbol == "AAPL"


@pytest.mark.integration
@pytest.mark.issue_15
async def test_signals_filtering_by_type(client: httpx.AsyncClient) -> None:
    """Validate GET /signals?signal_type=anomaly filters by signal type."""
    response = await client.get("/signals?signal_type=anomaly")
    assert response.status_code == 200

    data = response.json()
    validated = SignalsQueryResponse.model_validate(data)
    assert validated.total == 2
    for item in validated.items:
        assert item.signal_type == "anomaly"


@pytest.mark.integration
@pytest.mark.issue_15
async def test_signals_pagination(client: httpx.AsyncClient) -> None:
    """Validate pagination with limit and offset query parameters."""
    # First page: limit 10, offset 0
    resp_page_1 = await client.get("/signals?ticker=GOOGL&limit=10&offset=0")
    assert resp_page_1.status_code == 200
    page_1 = SignalsQueryResponse.model_validate(resp_page_1.json())
    assert page_1.total == 25
    assert len(page_1.items) == 10
    assert page_1.limit == 10
    assert page_1.offset == 0

    # Second page: limit 10, offset 10
    resp_page_2 = await client.get("/signals?ticker=GOOGL&limit=10&offset=10")
    assert resp_page_2.status_code == 200
    page_2 = SignalsQueryResponse.model_validate(resp_page_2.json())
    assert page_2.total == 25
    assert len(page_2.items) == 10
    assert page_2.offset == 10

    # Verify no overlap between page 1 and page 2 items
    page_1_ids = {item.id for item in page_1.items}
    page_2_ids = {item.id for item in page_2.items}
    assert page_1_ids.isdisjoint(page_2_ids)

    # Third page: limit 10, offset 20 -> remaining 5 items
    resp_page_3 = await client.get("/signals?ticker=GOOGL&limit=10&offset=20")
    assert resp_page_3.status_code == 200
    page_3 = SignalsQueryResponse.model_validate(resp_page_3.json())
    assert len(page_3.items) == 5


@pytest.mark.integration
@pytest.mark.issue_15
async def test_signals_validation_errors(client: httpx.AsyncClient) -> None:
    """Validate limit and offset bounds return 422 Unprocessable Entity."""
    # limit = 0 (violates ge=1)
    res_zero = await client.get("/signals?limit=0")
    assert res_zero.status_code == 422

    # limit = 101 (violates le=100)
    res_large = await client.get("/signals?limit=101")
    assert res_large.status_code == 422

    # offset = -1 (violates ge=0)
    res_neg_offset = await client.get("/signals?offset=-1")
    assert res_neg_offset.status_code == 422

    # non-integer limit
    res_str = await client.get("/signals?limit=not-a-number")
    assert res_str.status_code == 422


@pytest.mark.integration
@pytest.mark.issue_15
async def test_company_summary_success(client: httpx.AsyncClient) -> None:
    """Validate GET /summary/{ticker} returns 200 with summary and metrics."""
    response = await client.get("/summary/AAPL")
    assert response.status_code == 200

    data = response.json()
    validated = CompanySummaryResponse.model_validate(data)
    assert validated.ticker == "AAPL"
    assert "Apple posted record quarterly revenue" in validated.summary
    assert validated.model_used is not None
    assert validated.metrics is not None
    assert validated.metrics.get("sentiment_score") == 0.88
    assert validated.metrics.get("sentiment_label") == "bullish"


@pytest.mark.integration
@pytest.mark.issue_15
async def test_company_summary_case_insensitive(client: httpx.AsyncClient) -> None:
    """Validate GET /summary/{ticker} handles lowercase ticker correctly."""
    response = await client.get("/summary/msft")
    assert response.status_code == 200

    data = response.json()
    validated = CompanySummaryResponse.model_validate(data)
    assert validated.ticker == "MSFT"
    assert "Azure" in validated.summary


@pytest.mark.integration
@pytest.mark.issue_15
async def test_company_summary_not_found(client: httpx.AsyncClient) -> None:
    """Validate GET /summary/{ticker} returns 404 for unknown ticker."""
    response = await client.get("/summary/UNKNOWN")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


@pytest.mark.integration
@pytest.mark.issue_15
async def test_anomaly_alerts_endpoint(client: httpx.AsyncClient) -> None:
    """Validate GET /alerts returns active anomaly alerts."""
    response = await client.get("/alerts")
    assert response.status_code == 200

    data = response.json()
    validated = AlertsResponse.model_validate(data)
    assert validated.total == 2
    assert len(validated.items) == 2

    # Ticker filter
    resp_aapl = await client.get("/alerts?ticker=AAPL")
    assert resp_aapl.status_code == 200
    alerts_aapl = AlertsResponse.model_validate(resp_aapl.json())
    assert alerts_aapl.total == 1
    assert alerts_aapl.items[0].symbol == "AAPL"
    assert alerts_aapl.items[0].method == "zscore"
    assert alerts_aapl.items[0].severity == "high"

    # Severity filter
    resp_med = await client.get("/alerts?severity=medium")
    assert resp_med.status_code == 200
    alerts_med = AlertsResponse.model_validate(resp_med.json())
    assert alerts_med.total == 1
    assert alerts_med.items[0].symbol == "MSFT"
    assert alerts_med.items[0].severity == "medium"


@pytest.mark.integration
@pytest.mark.issue_15
async def test_alerts_validation_errors(client: httpx.AsyncClient) -> None:
    """Validate GET /alerts returns 422 on invalid limit parameter."""
    res_zero = await client.get("/alerts?limit=0")
    assert res_zero.status_code == 422

    res_large = await client.get("/alerts?limit=150")
    assert res_large.status_code == 422


@pytest.mark.integration
@pytest.mark.issue_15
async def test_openapi_schema_generation(client: httpx.AsyncClient) -> None:
    """Validate GET /openapi.json returns valid OpenAPI 3.1.0 schema with required routes."""
    response = await client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()

    assert schema["openapi"] == "3.1.0"
    assert "info" in schema
    assert "paths" in schema

    paths = schema["paths"]
    assert "/health" in paths
    assert "/signals" in paths
    assert "/summary/{ticker}" in paths
    assert "/alerts" in paths

    components = schema["components"]["schemas"]
    assert "HealthResponse" in components
    assert "SignalsQueryResponse" in components
    assert "CompanySummaryResponse" in components
    assert "AlertItem" in components
    assert "AlertsResponse" in components


@pytest.mark.integration
@pytest.mark.issue_15
async def test_swagger_ui_docs(client: httpx.AsyncClient) -> None:
    """Validate GET /docs returns interactive Swagger UI HTML page."""
    response = await client.get("/docs")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "swagger-ui" in response.text.lower()


@pytest.mark.integration
@pytest.mark.issue_15
async def test_unsupported_methods_and_paths(client: httpx.AsyncClient) -> None:
    """Validate 405 Method Not Allowed and 404 Not Found handling."""
    # POST to GET endpoint
    post_res = await client.post("/health")
    assert post_res.status_code == 405

    # Non-existent endpoint
    unknown_res = await client.get("/non_existent_route")
    assert unknown_res.status_code == 404


@pytest.mark.integration
@pytest.mark.issue_15
async def test_graceful_handling_without_database() -> None:
    """Validate endpoints handle absent database connection gracefully."""
    app_no_db = create_app(session_factory=None)
    transport = httpx.ASGITransport(app=app_no_db)

    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as no_db_client:
        # Health check should return 200 with idle db status
        resp_health = await no_db_client.get("/health")
        assert resp_health.status_code == 200
        health_data = resp_health.json()
        assert health_data["status"] == "healthy"
        assert health_data["details"]["database"] == "idle"

        # Signals query returns empty list
        resp_signals = await no_db_client.get("/signals")
        assert resp_signals.status_code == 200
        signals_data = resp_signals.json()
        assert signals_data["items"] == []
        assert signals_data["total"] == 0

        # Summary returns 404
        resp_summary = await no_db_client.get("/summary/AAPL")
        assert resp_summary.status_code == 404

        # Alerts returns empty list
        resp_alerts = await no_db_client.get("/alerts")
        assert resp_alerts.status_code == 200
        alerts_data = resp_alerts.json()
        assert alerts_data["items"] == []


@pytest.mark.integration
@pytest.mark.issue_15
async def test_asgi_lifespan_and_non_http(app_instance: MarketIntelASGIApp) -> None:
    """Validate ASGI lifespan events and non-HTTP scope handling."""
    # Non-http scope should return immediately without error
    await app_instance({"type": "websocket"}, lambda: None, lambda _: None)

    # Lifespan startup and shutdown events
    events_sent: list[dict[str, object]] = []
    messages: list[dict[str, object]] = [
        {"type": "lifespan.startup"},
        {"type": "lifespan.shutdown"},
    ]

    async def mock_receive() -> dict[str, object]:
        if messages:
            return messages.pop(0)
        return {"type": "lifespan.unknown"}

    async def mock_send(event: dict[str, object]) -> None:
        events_sent.append(event)

    await app_instance({"type": "lifespan"}, mock_receive, mock_send)
    assert any(e.get("type") == "lifespan.startup.complete" for e in events_sent)
    assert any(e.get("type") == "lifespan.shutdown.complete" for e in events_sent)


@pytest.mark.integration
@pytest.mark.issue_15
async def test_database_error_resilience() -> None:
    """Validate that API routes degrade gracefully on database exceptions."""

    class FailingSessionContext:
        async def __aenter__(self) -> None:
            raise RuntimeError("Simulated DB connection failure")

        async def __aexit__(
            self,
            exc_type: object,
            exc_val: object,
            exc_tb: object,
        ) -> None:
            pass

    class FailingSessionFactory:
        def __call__(self) -> FailingSessionContext:
            return FailingSessionContext()

    failing_app = create_app(session_factory=FailingSessionFactory())  # type: ignore[arg-type]
    transport = httpx.ASGITransport(app=failing_app)

    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        # Health check marks db unreachable but returns 200
        resp_health = await client.get("/health")
        assert resp_health.status_code == 200
        assert resp_health.json()["details"]["database"] == "unreachable"

        # Signals handles exception and returns 0 items
        resp_signals = await client.get("/signals")
        assert resp_signals.status_code == 200
        assert resp_signals.json()["total"] == 0

        # Summary returns 404
        resp_summary = await client.get("/summary/AAPL")
        assert resp_summary.status_code == 404

        # Alerts returns 0 items
        resp_alerts = await client.get("/alerts")
        assert resp_alerts.status_code == 200
        assert resp_alerts.json()["total"] == 0


@pytest.mark.integration
@pytest.mark.issue_15
async def test_empty_summary_ticker(client: httpx.AsyncClient) -> None:
    """Validate GET /summary/ with whitespace ticker returns 404."""
    resp = await client.get("/summary/ ")
    assert resp.status_code == 404


@pytest.mark.integration
@pytest.mark.issue_15
def test_create_app_custom_settings() -> None:
    """Validate create_app initializes with custom settings."""
    from market_intel.core.config import Settings

    custom_settings = Settings(api_title="Custom Market Intel API", api_version="2.0.0")
    custom_app = create_app(settings=custom_settings)
    assert custom_app.title == "Custom Market Intel API"
    assert custom_app.version == "2.0.0"
    spec = custom_app.openapi()
    assert spec["info"]["title"] == "Custom Market Intel API"
    assert spec["info"]["version"] == "2.0.0"
