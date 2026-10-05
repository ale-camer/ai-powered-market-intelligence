"""End-to-End (E2E) integration test for full market intelligence data pipeline (Issue #19).

Covers the complete lifecycle:
  Ingest -> Deduplicate -> NLP Enrich -> Store -> Serve -> Telemetry
"""

import json
import uuid
from collections.abc import AsyncGenerator, Sequence
from datetime import UTC, datetime
from typing import Any
from unittest.mock import MagicMock

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from market_intel.api.app import create_app
from market_intel.api.websocket import connection_manager
from market_intel.core.cache import (
    DeduplicationCache,
    generate_fingerprint,
    normalize_url,
)
from market_intel.loaders.database import Base, get_async_session_factory
from market_intel.loaders.models import ArticleModel, EnrichedSignalModel
from market_intel.loaders.repository import EmbeddingRepository
from market_intel.transformers.anomaly import TimeSeriesAnomalyDetector
from market_intel.transformers.ner import FinancialNERExtractor
from market_intel.transformers.sentiment import SentimentAnalyzer

pytestmark = [pytest.mark.e2e, pytest.mark.issue_19]


class MockFinBERTModel:
    """Deterministic fast mock for FinBERT sequence classification in E2E tests."""

    def predict_batch(self, texts: Sequence[str]) -> list[dict[str, Any]]:
        return [
            {
                "label": "bullish",
                "score": 0.92,
                "confidence": 0.96,
                "probs": {"positive": 0.96, "negative": 0.03, "neutral": 0.01},
            }
            for _ in texts
        ]


class MockSpan:
    def __init__(self, text: str, label: str) -> None:
        self.text = text
        self.label_ = label
        self.start_char = 0
        self.end_char = len(text)


class MockDoc:
    def __init__(self, text: str, ents: list[MockSpan]) -> None:
        self.text = text
        self.ents = ents


class MockSpaCyNLP:
    def __call__(self, text: str) -> MockDoc:
        return MockDoc(text, [MockSpan("NVIDIA Corporation", "ORG")])


class InMemoryAsyncRedis:
    """Lightweight in-memory Redis client for E2E deduplication cache verification."""

    def __init__(self) -> None:
        self._data: dict[str, str] = {}

    async def get(self, name: str) -> str | None:
        return self._data.get(name)

    async def set(
        self,
        name: str,
        value: str,
        ex: int | None = None,
        nx: bool = False,
    ) -> bool | None:
        if nx and name in self._data:
            return None
        self._data[name] = str(value)
        return True

    async def exists(self, *names: str) -> int:
        return sum(1 for n in names if n in self._data)

    async def aclose(self) -> None:
        self._data.clear()


class MockWebSocketReceiver:
    """Mock WebSocket receiver simulating a connected frontend dashboard client."""

    def __init__(self) -> None:
        self.received_messages: list[str] = []

    async def send_text(self, text: str) -> None:
        self.received_messages.append(text)


@pytest.fixture
async def session_factory() -> AsyncGenerator[async_sessionmaker[AsyncSession], None]:
    """Provide isolated in-memory SQLite database session factory for E2E tests."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
        echo=False,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = get_async_session_factory(engine)
    yield factory
    await engine.dispose()


@pytest.fixture
async def api_client(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncGenerator[httpx.AsyncClient, None]:
    """Provide HTTP test client bound to ASGI application with SQLite database."""
    app = create_app(session_factory=session_factory)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client


@pytest.mark.asyncio
async def test_market_intelligence_full_pipeline_e2e(
    session_factory: async_sessionmaker[AsyncSession],
    api_client: httpx.AsyncClient,
) -> None:
    """Verify complete end-to-end data lifecycle across all architectural layers."""
    # ── 1. INGESTION & DEDUPLICATION ──────────────────────────────────────────
    raw_article = {
        "title": "NVIDIA NVDA reports record data center revenue surge beating analyst forecasts",
        "description": "NVIDIA Corporation $NVDA announced unprecedented AI GPU demand.",
        "content": "NVIDIA Corporation (NVDA) delivered record quarterly revenue of $30 billion.",
        "url": "https://reuters.com/technology/nvidia-earnings-record-2026?utm_source=twitter",
        "source": {"name": "Reuters"},
        "published_at": datetime.now(UTC),
    }

    normalized_url = normalize_url(raw_article["url"])
    assert "utm_source" not in normalized_url

    redis_mock = InMemoryAsyncRedis()
    cache = DeduplicationCache(redis_client=redis_mock, name="e2e_dedup")
    fingerprint = generate_fingerprint(normalized_url, prefix="article")

    # Verify first ingestion is not duplicate
    is_dup_first = await cache.check_and_set(fingerprint, ttl=3600)
    assert is_dup_first is False

    # Verify duplicate ingestion is prevented
    is_dup_second = await cache.check_and_set(fingerprint, ttl=3600)
    assert is_dup_second is True

    # ── 2. TRANSFORMATION & ENRICHMENT ────────────────────────────────────────
    # A. Sentiment Analysis
    sentiment_analyzer = SentimentAnalyzer(
        model=MockFinBERTModel(),
        tokenizer=MagicMock(),
    )
    sentiment_res = sentiment_analyzer.analyze_text(raw_article["title"])
    assert sentiment_res.label == "bullish"
    assert sentiment_res.score > 0.8
    assert sentiment_res.confidence > 0.9

    # B. Named Entity Recognition
    ner_extractor = FinancialNERExtractor(nlp=MockSpaCyNLP())
    ner_res = ner_extractor.extract_text(f"{raw_article['title']} {raw_article['content']}")
    assert "NVDA" in ner_res.tickers

    # C. Anomaly Detection on Price/Volume time-series
    anomaly_detector = TimeSeriesAnomalyDetector()
    volume_series = [1000.0 + float(i % 5) for i in range(30)] + [10000.0]
    anomalies = anomaly_detector.detect_zscore(volume_series)
    assert anomalies[-1].is_anomaly is True
    assert anomalies[-1].score is not None and anomalies[-1].score > 3.0

    # D. 1536-Dimensional Vector Embedding
    embedding_vector = [0.025] * 1536

    # ── 3. STORAGE & INDEXING ─────────────────────────────────────────────────
    signal_id = uuid.uuid4()
    anomaly_signal_id = uuid.uuid4()
    now = datetime.now(UTC)

    async with session_factory() as session:
        # Save raw article
        article_record = ArticleModel(
            source_name="Reuters",
            title=raw_article["title"],
            url=normalized_url,
            published_at=raw_article["published_at"],
        )
        session.add(article_record)

        # Save primary sentiment enriched signal
        sentiment_signal = EnrichedSignalModel(
            id=signal_id,
            source_type="article",
            symbol="NVDA",
            signal_type="sentiment",
            sentiment_score=sentiment_res.score,
            sentiment_label=sentiment_res.label,
            confidence=sentiment_res.confidence,
            summary=raw_article["title"],
            entities={"companies": ner_res.entities.get("ORG", []), "tickers": ner_res.tickers},
            embedding=embedding_vector,
            timestamp=now,
        )
        # Save volume anomaly signal
        anomaly_signal = EnrichedSignalModel(
            id=anomaly_signal_id,
            source_type="pipeline",
            symbol="NVDA",
            signal_type="anomaly",
            sentiment_score=None,
            sentiment_label="high",
            confidence=0.99,
            summary="Exceptional 5-sigma trading volume spike detected for NVDA",
            entities={"companies": ["NVIDIA Corporation"], "tickers": ["NVDA"]},
            embedding=embedding_vector,
            timestamp=now,
        )

        repo = EmbeddingRepository(session)
        await repo.upsert(sentiment_signal)
        await repo.upsert(anomaly_signal)
        await session.commit()

    # ── 4. REAL-TIME DELIVERY (WEBSOCKET ALERT STREAMING) ─────────────────────
    receiver = MockWebSocketReceiver()
    await connection_manager.connect(receiver)  # type: ignore[arg-type]

    alert_broadcast_data = {
        "id": str(anomaly_signal_id),
        "symbol": "NVDA",
        "anomaly_type": "volume_spike",
        "score": 0.99,
        "message": "Exceptional 5-sigma volume spike detected for NVDA",
        "timestamp": now.isoformat(),
    }
    await connection_manager.broadcast_alert(alert_broadcast_data)
    assert len(receiver.received_messages) == 1

    received_json = json.loads(receiver.received_messages[0])
    assert received_json["event"] == "alert"
    assert received_json["data"]["symbol"] == "NVDA"

    connection_manager.disconnect(receiver)

    # ── 5. DELIVERY LAYER (REST API ENDPOINTS) ────────────────────────────────
    # A. GET /health
    health_resp = await api_client.get("/health")
    assert health_resp.status_code == 200
    assert health_resp.json()["status"] == "healthy"

    # B. GET /signals?ticker=NVDA
    signals_resp = await api_client.get("/signals?ticker=NVDA")
    assert signals_resp.status_code == 200
    signals_data = signals_resp.json()
    assert signals_data["total"] >= 1
    assert any(s["symbol"] == "NVDA" for s in signals_data["items"])

    # C. GET /summary/NVDA
    summary_resp = await api_client.get("/summary/NVDA")
    assert summary_resp.status_code == 200
    summary_data = summary_resp.json()
    assert summary_data["ticker"] == "NVDA"
    assert summary_data["summary"]

    # D. GET /alerts
    alerts_resp = await api_client.get("/alerts")
    assert alerts_resp.status_code == 200
    alerts_data = alerts_resp.json()
    assert alerts_data["total"] >= 1
    assert any(a["symbol"] == "NVDA" for a in alerts_data["items"])

    # ── 6. OBSERVABILITY & TELEMETRY (/metrics) ───────────────────────────────
    metrics_resp = await api_client.get("/metrics")
    assert metrics_resp.status_code == 200
    assert "text/plain" in metrics_resp.headers.get("content-type", "")

    metrics_text = metrics_resp.text
    assert "# HELP http_requests_total" in metrics_text
    assert "# HELP http_request_duration_seconds" in metrics_text
    assert "# HELP db_query_duration_seconds" in metrics_text
    assert "# HELP cache_hits_total" in metrics_text
    assert "# HELP cache_misses_total" in metrics_text
    assert "# HELP websocket_active_connections" in metrics_text
    assert 'endpoint="/signals"' in metrics_text
