"""Unit tests for Redis deduplication caching layer and Prometheus metrics."""

from unittest.mock import AsyncMock, patch

import pytest
from redis.exceptions import ConnectionError as RedisConnectionError

from market_intel.core.cache import (
    CACHE_HITS_TOTAL,
    CACHE_MISSES_TOTAL,
    DeduplicationCache,
    generate_fingerprint,
    normalize_url,
)
from market_intel.core.exceptions import CacheError, MarketIntelError


@pytest.mark.unit
@pytest.mark.issue_8
def test_url_normalization() -> None:
    """Verify URL normalization removes tracking parameters and normalizes format."""
    url1 = "https://Example.COM:443/markets/news/?utm_source=twitter&utm_medium=social&ticker=AAPL"
    url2 = "https://example.com/markets/news?ticker=AAPL&utm_campaign=summer"

    assert normalize_url(url1) == "https://example.com/markets/news?ticker=AAPL"
    assert normalize_url(url2) == "https://example.com/markets/news?ticker=AAPL"
    assert normalize_url(url1) == normalize_url(url2)

    # Non-URL string remains trimmed
    assert normalize_url("   raw string text   ") == "raw string text"


@pytest.mark.unit
@pytest.mark.issue_8
def test_fingerprint_generation_determinism() -> None:
    """Verify generate_fingerprint produces deterministic SHA-256 digests."""
    url_a = "https://bloomberg.com/news/articles/2026-09-24/earnings?utm_source=feed"
    url_b = "https://bloomberg.com/news/articles/2026-09-24/earnings/"

    fp_a = generate_fingerprint(url_a, prefix="article")
    fp_b = generate_fingerprint(url_b, prefix="article")

    assert fp_a == fp_b
    assert fp_a.startswith("article:")
    assert len(fp_a.split(":")[1]) == 64  # SHA-256 hex digest length

    # Different content produces different fingerprint
    fp_c = generate_fingerprint("https://reuters.com/markets", prefix="article")
    assert fp_a != fp_c


@pytest.mark.unit
@pytest.mark.issue_8
@pytest.mark.asyncio
async def test_cache_check_and_set_miss_and_hit() -> None:
    """Verify atomic check_and_set distinguishes between fresh keys (miss) and duplicates (hit)."""
    mock_redis = AsyncMock()
    cache_name = "test_dedup_check"
    cache = DeduplicationCache(redis_client=mock_redis, name=cache_name)

    # Initial metric values
    init_misses = CACHE_MISSES_TOTAL.labels(cache_name=cache_name)._value.get()
    init_hits = CACHE_HITS_TOTAL.labels(cache_name=cache_name)._value.get()

    # 1. Fresh key (Cache Miss): redis.set returns True
    mock_redis.set.return_value = True
    is_dup = await cache.check_and_set("doc:key1", ttl=3600)
    assert is_dup is False
    mock_redis.set.assert_called_with(name="doc:key1", value="1", ex=3600, nx=True)
    assert CACHE_MISSES_TOTAL.labels(cache_name=cache_name)._value.get() == init_misses + 1

    # 2. Existing key (Cache Hit): redis.set returns None
    mock_redis.set.return_value = None
    is_dup_second = await cache.check_and_set("doc:key1", ttl=3600)
    assert is_dup_second is True
    assert CACHE_HITS_TOTAL.labels(cache_name=cache_name)._value.get() == init_hits + 1


@pytest.mark.unit
@pytest.mark.issue_8
@pytest.mark.asyncio
async def test_cache_is_duplicate() -> None:
    """Verify is_duplicate reads key existence and updates Prometheus counters."""
    mock_redis = AsyncMock()
    cache_name = "test_is_duplicate"
    cache = DeduplicationCache(redis_client=mock_redis, name=cache_name)

    init_hits = CACHE_HITS_TOTAL.labels(cache_name=cache_name)._value.get()
    init_misses = CACHE_MISSES_TOTAL.labels(cache_name=cache_name)._value.get()

    # Key exists -> duplicate
    mock_redis.exists.return_value = 1
    assert await cache.is_duplicate("doc:exists") is True
    assert CACHE_HITS_TOTAL.labels(cache_name=cache_name)._value.get() == init_hits + 1

    # Key does not exist -> not duplicate
    mock_redis.exists.return_value = 0
    assert await cache.is_duplicate("doc:missing") is False
    assert CACHE_MISSES_TOTAL.labels(cache_name=cache_name)._value.get() == init_misses + 1


@pytest.mark.unit
@pytest.mark.issue_8
@pytest.mark.asyncio
async def test_cache_set_fingerprint_and_delete() -> None:
    """Verify set_fingerprint and delete operations."""
    mock_redis = AsyncMock()
    cache = DeduplicationCache(redis_client=mock_redis)

    # set_fingerprint
    result = await cache.set_fingerprint("doc:explicit", ttl=7200)
    assert result is True
    mock_redis.set.assert_called_with(name="doc:explicit", value="1", ex=7200)

    # delete existing
    mock_redis.delete.return_value = 1
    assert await cache.delete("doc:explicit") is True
    mock_redis.delete.assert_called_with("doc:explicit")

    # delete non-existent
    mock_redis.delete.return_value = 0
    assert await cache.delete("doc:nonexistent") is False


@pytest.mark.unit
@pytest.mark.issue_8
@pytest.mark.asyncio
async def test_cache_redis_error_raises_cache_error() -> None:
    """Verify Redis exceptions are wrapped in CacheError."""
    mock_redis = AsyncMock()
    mock_redis.set.side_effect = RedisConnectionError("Redis connection refused")
    mock_redis.exists.side_effect = RedisConnectionError("Redis connection refused")
    mock_redis.delete.side_effect = RedisConnectionError("Redis connection refused")

    cache = DeduplicationCache(redis_client=mock_redis)

    with pytest.raises(CacheError, match="Redis check_and_set failed"):
        await cache.check_and_set("key:fail")

    with pytest.raises(CacheError, match="Redis is_duplicate check failed"):
        await cache.is_duplicate("key:fail")

    with pytest.raises(CacheError, match="Redis set_fingerprint failed"):
        await cache.set_fingerprint("key:fail")

    with pytest.raises(CacheError, match="Redis delete failed"):
        await cache.delete("key:fail")


@pytest.mark.unit
@pytest.mark.issue_8
@pytest.mark.asyncio
async def test_cache_context_manager() -> None:
    """Verify async context manager protocol closes client on exit."""
    mock_client = AsyncMock()
    with patch("redis.asyncio.from_url", return_value=mock_client):
        async with DeduplicationCache(redis_url="redis://localhost:6379/1") as cache:
            assert cache.client == mock_client

        mock_client.aclose.assert_called_once()


@pytest.mark.unit
@pytest.mark.issue_8
def test_cache_error_hierarchy() -> None:
    """Verify CacheError inherits from MarketIntelError."""
    err = CacheError("Deduplication failed")
    assert isinstance(err, MarketIntelError)
    assert isinstance(err, Exception)
    assert str(err) == "Deduplication failed"
