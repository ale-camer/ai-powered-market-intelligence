"""SQLAlchemy 2.0 asynchronous engine and session management."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import datetime

from sqlalchemy import DateTime, func
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from market_intel.core.config import get_settings


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy declarative models."""

    pass


class TimestampMixin:
    """Mixin adding created_at and updated_at timestamps to models."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


def get_async_engine(
    url: str | None = None,
    echo: bool = False,
    pool_size: int = 10,
    max_overflow: int = 20,
    pool_pre_ping: bool = True,
    **engine_kwargs: object,
) -> AsyncEngine:
    """Create and return an asynchronous SQLAlchemy engine.

    Args:
        url: Database URL (defaults to Settings.async_postgres_url).
        echo: If True, log SQL statements.
        pool_size: Connection pool size (for pool-supporting drivers).
        max_overflow: Maximum pool overflow.
        pool_pre_ping: Check connection liveness before checkout.
        **engine_kwargs: Additional arguments for create_async_engine.

    Returns:
        Configured AsyncEngine instance.
    """
    db_url = url or get_settings().async_postgres_url

    kwargs: dict[str, object] = {
        "echo": echo,
        "pool_pre_ping": pool_pre_ping,
        **engine_kwargs,
    }

    # SQLite (e.g. for testing) does not accept pool_size/max_overflow with default pool
    if not db_url.startswith("sqlite"):
        kwargs["pool_size"] = pool_size
        kwargs["max_overflow"] = max_overflow

    return create_async_engine(db_url, **kwargs)


def get_async_session_factory(
    engine: AsyncEngine | None = None,
) -> async_sessionmaker[AsyncSession]:
    """Create and return an async sessionmaker bound to an engine."""
    target_engine = engine or get_async_engine()
    return async_sessionmaker(
        bind=target_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )


@asynccontextmanager
async def get_async_session(
    engine: AsyncEngine | None = None,
) -> AsyncGenerator[AsyncSession, None]:
    """Async context manager yielding an AsyncSession."""
    factory = get_async_session_factory(engine)
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
