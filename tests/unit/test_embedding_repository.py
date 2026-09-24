"""Unit tests for pgvector integration, cosine similarity, and EmbeddingRepository."""

import math
import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy.ext.asyncio import create_async_engine

from market_intel.loaders.database import Base, get_async_session_factory
from market_intel.loaders.models import EnrichedSignalModel
from market_intel.loaders.repository import (
    EmbeddingRepository,
    compute_cosine_similarity,
)


@pytest.mark.unit
@pytest.mark.issue_7
def test_cosine_similarity_mathematics() -> None:
    """Validate mathematical correctness of compute_cosine_similarity."""
    # Identical vectors
    v1 = [1.0, 2.0, 3.0]
    assert math.isclose(compute_cosine_similarity(v1, v1), 1.0)

    # Orthogonal vectors
    v_x = [1.0, 0.0, 0.0]
    v_y = [0.0, 1.0, 0.0]
    assert math.isclose(compute_cosine_similarity(v_x, v_y), 0.0)

    # Opposite vectors
    v_pos = [2.0, 4.0]
    v_neg = [-2.0, -4.0]
    assert math.isclose(compute_cosine_similarity(v_pos, v_neg), -1.0)

    # 45 degree angle
    v_a = [1.0, 0.0]
    v_b = [1.0, 1.0]
    expected = 1.0 / math.sqrt(2.0)
    assert math.isclose(compute_cosine_similarity(v_a, v_b), expected, rel_tol=1e-5)


@pytest.mark.unit
@pytest.mark.issue_7
def test_cosine_similarity_edge_cases() -> None:
    """Validate edge cases in compute_cosine_similarity."""
    assert compute_cosine_similarity(None, [1.0, 2.0]) == 0.0
    assert compute_cosine_similarity([1.0, 2.0], None) == 0.0
    assert compute_cosine_similarity([], []) == 0.0
    assert compute_cosine_similarity([1.0], [1.0, 2.0]) == 0.0  # length mismatch
    assert compute_cosine_similarity([0.0, 0.0], [1.0, 2.0]) == 0.0  # zero vector


@pytest.mark.unit
@pytest.mark.issue_7
@pytest.mark.asyncio
async def test_embedding_repository_upsert_and_similarity_search() -> None:
    """Test upsert and top-K similarity search with filters using in-memory engine."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = get_async_session_factory(engine)
    async with session_factory() as session:
        repo = EmbeddingRepository(session)

        # 1. Create signals with different embeddings
        sig_aapl_1 = EnrichedSignalModel(
            id=uuid.uuid4(),
            source_type="article",
            symbol="AAPL",
            signal_type="sentiment",
            sentiment_score=0.9,
            embedding=[1.0, 0.0, 0.0],
            timestamp=datetime.now(UTC),
        )
        sig_aapl_2 = EnrichedSignalModel(
            id=uuid.uuid4(),
            source_type="article",
            symbol="AAPL",
            signal_type="sentiment",
            sentiment_score=0.7,
            embedding=[0.8, 0.6, 0.0],  # norm = 1.0, dot with [1,0,0] = 0.8
            timestamp=datetime.now(UTC),
        )
        sig_msft = EnrichedSignalModel(
            id=uuid.uuid4(),
            source_type="filing",
            symbol="MSFT",
            signal_type="sentiment",
            sentiment_score=0.5,
            embedding=[0.0, 1.0, 0.0],  # orthogonal, dot with [1,0,0] = 0.0
            timestamp=datetime.now(UTC),
        )
        sig_aapl_anomaly = EnrichedSignalModel(
            id=uuid.uuid4(),
            source_type="article",
            symbol="AAPL",
            signal_type="anomaly",
            sentiment_score=-0.5,
            embedding=[0.6, 0.0, 0.8],  # norm = 1.0, dot with [1,0,0] = 0.6
            timestamp=datetime.now(UTC),
        )
        sig_no_emb = EnrichedSignalModel(
            id=uuid.uuid4(),
            source_type="reddit_post",
            symbol="AAPL",
            signal_type="sentiment",
            embedding=None,
            timestamp=datetime.now(UTC),
        )

        for sig in [sig_aapl_1, sig_aapl_2, sig_msft, sig_aapl_anomaly, sig_no_emb]:
            await repo.upsert(sig)
        await session.commit()

        # 2. Search top-2 closest to [1.0, 0.0, 0.0]
        query = [1.0, 0.0, 0.0]
        results = await repo.similarity_search(query, top_k=2)

        assert len(results) == 2
        top1_sig, top1_score = results[0]
        top2_sig, top2_score = results[1]

        assert top1_sig.id == sig_aapl_1.id
        assert math.isclose(top1_score, 1.0, rel_tol=1e-4)

        assert top2_sig.id == sig_aapl_2.id
        assert math.isclose(top2_score, 0.8, rel_tol=1e-4)

        # 3. Search with symbol filter
        msft_results = await repo.similarity_search(query, symbol="MSFT")
        assert len(msft_results) == 1
        assert msft_results[0][0].symbol == "MSFT"

        # 4. Search with signal_type filter
        anomaly_results = await repo.similarity_search(query, signal_type="anomaly")
        assert len(anomaly_results) == 1
        assert anomaly_results[0][0].signal_type == "anomaly"
        assert math.isclose(anomaly_results[0][1], 0.6, rel_tol=1e-4)

        # 5. Test update via upsert
        sig_aapl_1.sentiment_score = 0.99
        sig_aapl_1.embedding = [0.0, 0.0, 1.0]
        updated = await repo.upsert(sig_aapl_1)
        assert updated.sentiment_score == 0.99
        await session.commit()

        new_results = await repo.similarity_search([0.0, 0.0, 1.0], top_k=1)
        assert len(new_results) == 1
        assert new_results[0][0].id == sig_aapl_1.id
        assert math.isclose(new_results[0][1], 1.0, rel_tol=1e-4)

    await engine.dispose()


@pytest.mark.unit
@pytest.mark.issue_7
@pytest.mark.asyncio
async def test_embedding_repository_postgres_branch() -> None:
    """Verify similarity_search constructs native pgvector query on Postgres."""
    mock_session = AsyncMock()
    mock_bind = MagicMock()
    mock_bind.dialect.name = "postgresql"
    mock_session.bind = mock_bind
    mock_session.get_bind = MagicMock(return_value=mock_bind)

    # Mock execute result
    mock_result = MagicMock()
    fake_signal = EnrichedSignalModel(
        id=uuid.uuid4(),
        source_type="article",
        symbol="NVDA",
        signal_type="sentiment",
        embedding=[0.1] * 1536,
        timestamp=datetime.now(UTC),
    )
    # Cosine distance = 0.05 -> similarity = 0.95
    mock_result.all.return_value = [(fake_signal, 0.05)]
    mock_session.execute.return_value = mock_result

    repo = EmbeddingRepository(mock_session)
    results = await repo.similarity_search(
        query_embedding=[0.1] * 1536,
        top_k=3,
        symbol="NVDA",
        signal_type="sentiment",
    )

    assert len(results) == 1
    sig, score = results[0]
    assert sig.symbol == "NVDA"
    assert math.isclose(score, 0.95, rel_tol=1e-4)
    assert mock_session.execute.called


@pytest.mark.unit
@pytest.mark.issue_7
def test_alembic_migration_0002_discovery() -> None:
    """Verify Alembic discovers migration 0002_add_vector_embeddings chained to 0001."""
    alembic_cfg = Config("alembic.ini")
    script = ScriptDirectory.from_config(alembic_cfg)

    rev_0002 = script.get_revision("0002_add_vector_embeddings")
    assert rev_0002 is not None
    assert rev_0002.revision == "0002_add_vector_embeddings"
    assert rev_0002.down_revision == "0001_initial_schema"


@pytest.mark.unit
@pytest.mark.issue_7
def test_alembic_migration_0002_offline_sql(capsys: pytest.CaptureFixture[str]) -> None:
    """Verify offline SQL generation for migration 0002 (upgrade and downgrade)."""
    from alembic import command

    alembic_cfg = Config("alembic.ini")

    # Upgrade 0001 -> 0002
    command.upgrade(alembic_cfg, "0001_initial_schema:0002_add_vector_embeddings", sql=True)
    captured_upgrade = capsys.readouterr()
    assert "CREATE EXTENSION IF NOT EXISTS vector" in captured_upgrade.out
    assert "ALTER TABLE enriched_signals ADD COLUMN embedding VECTOR(1536)" in captured_upgrade.out
    assert "CREATE INDEX ix_enriched_signals_embedding_ivfflat" in captured_upgrade.out
    assert "USING ivfflat (embedding vector_cosine_ops)" in captured_upgrade.out

    # Downgrade 0002 -> 0001
    command.downgrade(alembic_cfg, "0002_add_vector_embeddings:0001_initial_schema", sql=True)
    captured_downgrade = capsys.readouterr()
    assert "DROP INDEX ix_enriched_signals_embedding_ivfflat" in captured_downgrade.out
    assert "ALTER TABLE enriched_signals DROP COLUMN embedding" in captured_downgrade.out
