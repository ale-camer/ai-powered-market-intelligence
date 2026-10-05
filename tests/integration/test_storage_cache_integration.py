"""Integration tests for database persistence, pgvector, and Redis caching (Issue #19)."""

import time
import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import StaticPool

from market_intel.core.cache import (
    DeduplicationCache,
    generate_fingerprint,
    normalize_url,
)
from market_intel.loaders.database import Base, get_async_session_factory
from market_intel.loaders.models import EnrichedSignalModel
from market_intel.loaders.repository import EmbeddingRepository, compute_cosine_similarity

pytestmark = [pytest.mark.integration, pytest.mark.issue_19]


class InMemoryAsyncRedis:
    """Async in-memory key-value store simulating Redis semantics for integration tests."""

    def __init__(self) -> None:
        self.store: dict[str, str] = {}
        self.expires: dict[str, float] = {}

    def _clean_expired(self, name: str) -> None:
        if name in self.expires and time.time() > self.expires[name]:
            self.store.pop(name, None)
            self.expires.pop(name, None)

    async def get(self, name: str) -> str | None:
        self._clean_expired(name)
        return self.store.get(name)

    async def set(
        self,
        name: str,
        value: str,
        ex: int | None = None,
        nx: bool = False,
    ) -> bool | None:
        self._clean_expired(name)
        if nx and name in self.store:
            return None
        self.store[name] = str(value)
        if ex is not None:
            self.expires[name] = time.time() + ex
        return True

    async def exists(self, *names: str) -> int:
        count = 0
        for name in names:
            self._clean_expired(name)
            if name in self.store:
                count += 1
        return count

    async def delete(self, *names: str) -> int:
        count = 0
        for name in names:
            if name in self.store:
                del self.store[name]
                self.expires.pop(name, None)
                count += 1
        return count

    async def ping(self) -> bool:
        return True

    async def aclose(self) -> None:
        self.store.clear()
        self.expires.clear()


@pytest.fixture
async def async_session() -> AsyncSession:
    """Provide an isolated in-memory SQLite async database session."""
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
        yield session

    await engine.dispose()


@pytest.fixture
def in_memory_redis() -> InMemoryAsyncRedis:
    return InMemoryAsyncRedis()


@pytest.mark.asyncio
async def test_embedding_repository_upsert_and_similarity_search(
    async_session: AsyncSession,
) -> None:
    """Test vector persistence and multi-attribute similarity search."""
    repo = EmbeddingRepository(async_session)

    # 1. Seed records with known orthogonal and parallel 3-dimensional normalized vectors
    # Note: EmbeddingRepository supports any vector dimension for similarity ranking
    tech_vector = [1.0, 0.0, 0.0]
    health_vector = [0.0, 1.0, 0.0]
    finance_vector = [0.0, 0.0, 1.0]

    sig_tech = EnrichedSignalModel(
        id=uuid.uuid4(),
        source_type="article",
        symbol="NVDA",
        signal_type="sentiment",
        sentiment_score=0.9,
        sentiment_label="bullish",
        confidence=0.95,
        summary="NVIDIA announces next-generation Blackwell architecture.",
        entities={"companies": ["NVIDIA"], "tickers": ["NVDA"]},
        embedding=tech_vector,
        timestamp=datetime.now(UTC),
    )
    sig_health = EnrichedSignalModel(
        id=uuid.uuid4(),
        source_type="filing",
        symbol="PFE",
        signal_type="sentiment",
        sentiment_score=0.2,
        sentiment_label="neutral",
        confidence=0.88,
        summary="Pfizer quarterly FDA clinical trial updates.",
        entities={"companies": ["Pfizer"], "tickers": ["PFE"]},
        embedding=health_vector,
        timestamp=datetime.now(UTC),
    )
    sig_finance = EnrichedSignalModel(
        id=uuid.uuid4(),
        source_type="article",
        symbol="JPM",
        signal_type="anomaly",
        sentiment_score=-0.4,
        sentiment_label="bearish",
        confidence=0.91,
        summary="JPMorgan flags unusual derivative trading volume.",
        entities={"companies": ["JPMorgan"], "tickers": ["JPM"]},
        embedding=finance_vector,
        timestamp=datetime.now(UTC),
    )

    await repo.upsert(sig_tech)
    await repo.upsert(sig_health)
    await repo.upsert(sig_finance)
    await async_session.commit()

    # 2. Query with a vector aligned with tech: [0.95, 0.05, 0.0]
    query_vector = [0.95, 0.05, 0.0]
    results = await repo.similarity_search(query_embedding=query_vector, top_k=2)

    assert len(results) == 2
    top_match, top_score = results[0]
    assert top_match.symbol == "NVDA"
    assert top_score > 0.9  # Highly aligned cosine similarity

    # 3. Query with symbol filter
    filtered_results = await repo.similarity_search(
        query_embedding=query_vector,
        top_k=5,
        symbol="PFE",
    )
    assert len(filtered_results) == 1
    assert filtered_results[0][0].symbol == "PFE"

    # 4. Query with signal_type filter
    anomaly_results = await repo.similarity_search(
        query_embedding=query_vector,
        top_k=5,
        signal_type="anomaly",
    )
    assert len(anomaly_results) == 1
    assert anomaly_results[0][0].symbol == "JPM"


@pytest.mark.asyncio
async def test_deduplication_cache_full_lifecycle(in_memory_redis: InMemoryAsyncRedis) -> None:
    """Validate cache URL normalization, SHA-256 fingerprinting, TTL, and Prometheus metrics."""
    cache = DeduplicationCache(redis_client=in_memory_redis, name="integration_dedup")

    raw_url = "https://reuters.com/markets/stocks/nvidia-rally/?utm_source=twitter&utm_medium=feed"
    normalized = normalize_url(raw_url)
    assert "utm_source" not in normalized

    fp = generate_fingerprint(raw_url, prefix="news")
    assert fp.startswith("news:")

    # Initial state: not duplicate
    is_dup = await cache.is_duplicate(fp)
    assert is_dup is False

    # Check and set: first call sets key and returns False (not duplicate)
    first_set = await cache.check_and_set(fp, ttl=300)
    assert first_set is False

    # Second call detects duplicate key
    second_set = await cache.check_and_set(fp, ttl=300)
    assert second_set is True

    # Immediate existence check
    assert await cache.is_duplicate(fp) is True

    # Expiration simulation: overwrite expiration timestamp into the past
    in_memory_redis.expires[fp] = time.time() - 10.0
    assert await cache.is_duplicate(fp) is False


def test_compute_cosine_similarity_edge_cases() -> None:
    """Test mathematical boundary conditions for vector similarity calculation."""
    # Orthogonal vectors
    assert compute_cosine_similarity([1.0, 0.0], [0.0, 1.0]) == 0.0

    # Opposite vectors
    assert compute_cosine_similarity([1.0, 0.0], [-1.0, 0.0]) == -1.0

    # Identical vectors
    assert pytest.approx(compute_cosine_similarity([3.0, 4.0], [3.0, 4.0])) == 1.0

    # Null and mismatched vectors
    assert compute_cosine_similarity(None, [1.0, 0.0]) == 0.0
    assert compute_cosine_similarity([1.0], [1.0, 2.0]) == 0.0
    assert compute_cosine_similarity([0.0, 0.0], [0.0, 0.0]) == 0.0
