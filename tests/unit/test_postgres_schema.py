"""Unit tests for PostgreSQL schema, SQLAlchemy models, and Alembic migrations."""

import uuid
from datetime import UTC, datetime

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from market_intel.core.config import Settings
from market_intel.core.exceptions import DatabaseError
from market_intel.loaders.database import (
    Base,
    get_async_engine,
    get_async_session,
    get_async_session_factory,
)
from market_intel.loaders.models import (
    ArticleModel,
    EnrichedSignalModel,
    FilingModel,
    PriceDataModel,
    RedditPostModel,
)


@pytest.mark.unit
@pytest.mark.issue_6
def test_postgres_url_properties() -> None:
    """Validate computed async and sync PostgreSQL URLs."""
    settings = Settings(
        POSTGRES_HOST="db.internal",
        POSTGRES_PORT=5433,
        POSTGRES_DB="test_market_intel",
        POSTGRES_USER="test_user",
        POSTGRES_PASSWORD="secure_password",
    )
    assert settings.async_postgres_url == (
        "postgresql+asyncpg://test_user:secure_password@db.internal:5433/test_market_intel"
    )
    assert settings.sync_postgres_url == (
        "postgresql+psycopg2://test_user:secure_password@db.internal:5433/test_market_intel"
    )


@pytest.mark.unit
@pytest.mark.issue_6
def test_async_engine_pool_configuration() -> None:
    """Verify that get_async_engine configures connection pool parameters."""
    engine = get_async_engine(
        url="postgresql+asyncpg://user:pass@localhost:5432/db",
        pool_size=15,
        max_overflow=25,
        pool_pre_ping=True,
    )
    assert isinstance(engine, AsyncEngine)
    assert engine.pool.size() == 15
    assert engine.pool._max_overflow == 25


@pytest.mark.unit
@pytest.mark.issue_6
def test_metadata_tables_registration() -> None:
    """Verify all 5 required tables are registered in Base.metadata."""
    table_names = set(Base.metadata.tables.keys())
    expected_tables = {
        "articles",
        "filings",
        "reddit_posts",
        "price_data",
        "enriched_signals",
    }
    assert expected_tables.issubset(table_names)


@pytest.mark.unit
@pytest.mark.issue_6
def test_articles_model_structure() -> None:
    """Validate structure, columns, and indexes for ArticleModel."""
    table = Base.metadata.tables["articles"]
    col_names = {c.name for c in table.columns}
    expected_cols = {
        "id",
        "source_id",
        "source_name",
        "author",
        "title",
        "description",
        "url",
        "url_to_image",
        "published_at",
        "content",
        "created_at",
        "updated_at",
    }
    assert expected_cols == col_names
    assert table.columns["id"].primary_key is True
    assert table.columns["url"].unique is True

    index_names = {idx.name for idx in table.indexes}
    assert "ix_articles_published_at" in index_names
    assert "ix_articles_published_at_source" in index_names


@pytest.mark.unit
@pytest.mark.issue_6
def test_filings_model_structure() -> None:
    """Validate structure, columns, and indexes for FilingModel."""
    table = Base.metadata.tables["filings"]
    col_names = {c.name for c in table.columns}
    expected_cols = {
        "id",
        "cik",
        "company_name",
        "filing_type",
        "filing_date",
        "period_of_report",
        "revenue",
        "eps",
        "assets",
        "raw_metrics",
        "created_at",
        "updated_at",
    }
    assert expected_cols == col_names
    assert table.columns["id"].primary_key is True

    index_names = {idx.name for idx in table.indexes}
    assert "ix_filings_cik" in index_names
    assert "ix_filings_filing_type" in index_names
    assert "ix_filings_filing_date" in index_names
    assert "ix_filings_cik_filing_date" in index_names


@pytest.mark.unit
@pytest.mark.issue_6
def test_reddit_posts_model_structure() -> None:
    """Validate structure, columns, and indexes for RedditPostModel."""
    table = Base.metadata.tables["reddit_posts"]
    col_names = {c.name for c in table.columns}
    expected_cols = {
        "id",
        "post_id",
        "subreddit",
        "title",
        "body",
        "score",
        "num_comments",
        "created_utc",
        "flair",
        "created_at",
        "updated_at",
    }
    assert expected_cols == col_names
    assert table.columns["id"].primary_key is True
    assert table.columns["post_id"].unique is True

    index_names = {idx.name for idx in table.indexes}
    assert "ix_reddit_posts_subreddit" in index_names
    assert "ix_reddit_posts_created_utc" in index_names
    assert "ix_reddit_posts_subreddit_created" in index_names


@pytest.mark.unit
@pytest.mark.issue_6
def test_price_data_model_structure() -> None:
    """Validate structure, constraints, and indexes for PriceDataModel."""
    table = Base.metadata.tables["price_data"]
    col_names = {c.name for c in table.columns}
    expected_cols = {
        "id",
        "symbol",
        "date",
        "open",
        "high",
        "low",
        "close",
        "adjusted_close",
        "volume",
        "created_at",
        "updated_at",
    }
    assert expected_cols == col_names
    assert table.columns["id"].primary_key is True

    unique_constraint_names = {c.name for c in table.constraints if c.name}
    assert "uq_price_data_symbol_date" in unique_constraint_names

    index_names = {idx.name for idx in table.indexes}
    assert "ix_price_data_symbol" in index_names
    assert "ix_price_data_date" in index_names
    assert "ix_price_data_symbol_date" in index_names


@pytest.mark.unit
@pytest.mark.issue_6
def test_enriched_signals_model_structure() -> None:
    """Validate structure, columns, and indexes for EnrichedSignalModel."""
    table = Base.metadata.tables["enriched_signals"]
    col_names = {c.name for c in table.columns}
    expected_cols = {
        "id",
        "source_type",
        "source_id",
        "symbol",
        "signal_type",
        "sentiment_score",
        "sentiment_label",
        "confidence",
        "summary",
        "entities",
        "timestamp",
        "created_at",
        "updated_at",
    }
    assert expected_cols == col_names
    assert table.columns["id"].primary_key is True

    index_names = {idx.name for idx in table.indexes}
    assert "ix_enriched_signals_symbol" in index_names
    assert "ix_enriched_signals_signal_type" in index_names
    assert "ix_enriched_signals_timestamp" in index_names
    assert "ix_enriched_signals_symbol_type" in index_names


@pytest.mark.unit
@pytest.mark.issue_6
@pytest.mark.asyncio
async def test_in_memory_sqlite_ddl_and_crud() -> None:
    """Verify DDL execution and CRUD operations using an async in-memory SQLite engine."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = get_async_session_factory(engine)
    async with session_factory() as session:
        # 1. Insert Article
        article = ArticleModel(
            source_name="Financial Times",
            title="Markets Rally on Earnings",
            url="https://example.com/article-1",
            published_at=datetime.now(UTC),
            content="Full article content here.",
        )
        session.add(article)

        # 2. Insert Filing
        filing = FilingModel(
            cik="0000320193",
            company_name="Apple Inc.",
            filing_type="10-K",
            filing_date=datetime.now(UTC),
            revenue=383285000000.0,
            eps=6.13,
            raw_metrics={"fiscal_year": 2023},
        )
        session.add(filing)

        # 3. Insert Reddit Post
        post = RedditPostModel(
            post_id="post_xyz123",
            subreddit="wallstreetbets",
            title="DD on semiconductors",
            body="Deep analysis on market trends...",
            score=1420,
            num_comments=88,
            created_utc=datetime.now(UTC),
        )
        session.add(post)

        # 4. Insert Price Data
        price = PriceDataModel(
            symbol="AAPL",
            date=datetime(2026, 9, 24, 0, 0, 0, tzinfo=UTC),
            open=225.50,
            high=228.10,
            low=224.90,
            close=227.35,
            adjusted_close=227.35,
            volume=55000000,
        )
        session.add(price)

        # 5. Insert Enriched Signal
        signal = EnrichedSignalModel(
            source_type="article",
            source_id=article.id,
            symbol="AAPL",
            signal_type="sentiment",
            sentiment_score=0.85,
            sentiment_label="bullish",
            confidence=0.92,
            summary="Strong earnings outlook driving bullish sentiment.",
            entities={"companies": ["Apple Inc."], "tickers": ["AAPL"]},
            timestamp=datetime.now(UTC),
        )
        session.add(signal)

        await session.commit()

    # Query back using get_async_session context manager
    async with get_async_session(engine) as session:
        queried_article = await session.get(ArticleModel, article.id)
        assert queried_article is not None
        assert queried_article.title == "Markets Rally on Earnings"
        assert isinstance(queried_article.id, uuid.UUID)

        queried_filing = await session.get(FilingModel, filing.id)
        assert queried_filing is not None
        assert queried_filing.cik == "0000320193"

        queried_price = await session.get(PriceDataModel, price.id)
        assert queried_price is not None
        assert queried_price.symbol == "AAPL"
        assert float(queried_price.close) == 227.35

        queried_signal = await session.get(EnrichedSignalModel, signal.id)
        assert queried_signal is not None
        assert queried_signal.sentiment_label == "bullish"
        assert queried_signal.entities == {"companies": ["Apple Inc."], "tickers": ["AAPL"]}

    await engine.dispose()


@pytest.mark.unit
@pytest.mark.issue_6
def test_alembic_configuration_and_migration_discovery() -> None:
    """Verify that Alembic configuration finds the initial migration."""
    alembic_cfg = Config("alembic.ini")
    script = ScriptDirectory.from_config(alembic_cfg)
    revisions = list(script.walk_revisions())

    assert len(revisions) >= 1
    initial_rev = script.get_revision("0001_initial_schema")
    assert initial_rev is not None
    assert initial_rev.revision == "0001_initial_schema"
    assert initial_rev.down_revision is None


@pytest.mark.unit
@pytest.mark.issue_6
def test_alembic_offline_sql_generation(capsys: pytest.CaptureFixture[str]) -> None:
    """Verify Alembic can generate offline SQL migrations (upgrade and downgrade)."""
    from alembic import command

    alembic_cfg = Config("alembic.ini")
    command.upgrade(alembic_cfg, "0001_initial_schema", sql=True)
    captured_upgrade = capsys.readouterr()
    assert "CREATE TABLE articles" in captured_upgrade.out
    assert "CREATE TABLE filings" in captured_upgrade.out
    assert "CREATE TABLE reddit_posts" in captured_upgrade.out
    assert "CREATE TABLE price_data" in captured_upgrade.out
    assert "CREATE TABLE enriched_signals" in captured_upgrade.out

    command.downgrade(alembic_cfg, "0001_initial_schema:base", sql=True)
    captured_downgrade = capsys.readouterr()
    assert "DROP TABLE enriched_signals" in captured_downgrade.out
    assert "DROP TABLE price_data" in captured_downgrade.out
    assert "DROP TABLE reddit_posts" in captured_downgrade.out
    assert "DROP TABLE filings" in captured_downgrade.out
    assert "DROP TABLE articles" in captured_downgrade.out


@pytest.mark.unit
@pytest.mark.issue_6
@pytest.mark.asyncio
async def test_async_session_rollback_on_error() -> None:
    """Verify get_async_session context manager rolls back transaction on exception."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    with pytest.raises(RuntimeError, match="Simulated failure"):
        async with get_async_session(engine) as session:
            article = ArticleModel(
                source_name="Bloomberg",
                title="Temporary Test Title",
                url="https://example.com/rollback-test",
                published_at=datetime.now(UTC),
            )
            session.add(article)
            await session.flush()
            raise RuntimeError("Simulated failure")

    async with get_async_session(engine) as session:
        queried = await session.get(ArticleModel, article.id)
        assert queried is None

    await engine.dispose()


@pytest.mark.unit
@pytest.mark.issue_6
def test_database_error_exception() -> None:
    """Validate DatabaseError exception instantiation and message."""
    err = DatabaseError("Connection timeout")
    assert str(err) == "Connection timeout"
    assert err.message == "Connection timeout"
