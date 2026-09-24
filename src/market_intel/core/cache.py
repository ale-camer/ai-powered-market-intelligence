"""Redis-backed asynchronous caching and deduplication layer."""

import hashlib
from types import TracebackType
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import redis.asyncio as redis
from prometheus_client import Counter
from redis.exceptions import RedisError

from market_intel.core.config import get_settings
from market_intel.core.exceptions import CacheError

CACHE_HITS_TOTAL = Counter(
    "cache_hits_total",
    "Total number of cache hits in deduplication layer",
    ["cache_name"],
)

CACHE_MISSES_TOTAL = Counter(
    "cache_misses_total",
    "Total number of cache misses in deduplication layer",
    ["cache_name"],
)

# Common tracking parameters to strip during URL normalization
TRACKING_PARAMS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "ref",
    "fbclid",
    "gclid",
    "_ga",
}


def normalize_url(url: str) -> str:
    """Normalize a URL by sorting query params and removing tracking parameters."""
    parsed = urlparse(url.strip())
    if not parsed.scheme or not parsed.netloc:
        return url.strip()

    scheme = parsed.scheme.lower()
    netloc = parsed.netloc.lower()

    # Strip port if default
    if scheme == "http" and netloc.endswith(":80"):
        netloc = netloc[:-3]
    elif scheme == "https" and netloc.endswith(":443"):
        netloc = netloc[:-4]

    # Clean path: normalize slashes
    path = parsed.path or "/"
    if len(path) > 1 and path.endswith("/"):
        path = path.rstrip("/")

    # Filter and sort query params
    filtered_params = [
        (k, v)
        for k, v in parse_qsl(parsed.query, keep_blank_values=True)
        if k.lower() not in TRACKING_PARAMS
    ]
    filtered_params.sort(key=lambda x: (x[0], x[1]))
    query = urlencode(filtered_params)

    return urlunparse((scheme, netloc, path, parsed.params, query, ""))


def generate_fingerprint(text: str, prefix: str = "doc") -> str:
    """Generate a deterministic SHA-256 fingerprint for a given URL or text payload.

    Args:
        text: Input string, URL, or payload text.
        prefix: Namespace prefix (e.g. 'article', 'reddit', 'doc').

    Returns:
        Formatted fingerprint string: '{prefix}:{sha256_hash}'.
    """
    cleaned = text.strip()
    if cleaned.startswith(("http://", "https://")):
        cleaned = normalize_url(cleaned)

    digest = hashlib.sha256(cleaned.encode("utf-8")).hexdigest()
    return f"{prefix}:{digest}"


class DeduplicationCache:
    """Asynchronous deduplication cache backed by Redis with Prometheus metrics."""

    def __init__(
        self,
        redis_client: redis.Redis | None = None,
        redis_url: str | None = None,
        name: str = "dedup",
    ) -> None:
        """Initialize the deduplication cache.

        Args:
            redis_client: Optional existing redis.asyncio.Redis instance.
            redis_url: Optional Redis connection URL (defaults to Settings.redis_url).
            name: Identifier for Prometheus metric labeling.
        """
        self.name = name
        self._owns_client = redis_client is None
        if redis_client is not None:
            self._client = redis_client
        else:
            url = redis_url or get_settings().redis_url
            self._client = redis.from_url(url, decode_responses=True)

    @property
    def client(self) -> redis.Redis:
        """Return the underlying Redis client."""
        return self._client

    async def __aenter__(self) -> "DeduplicationCache":
        """Async context manager entry."""
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Async context manager exit closing owned client."""
        await self.close()

    async def check_and_set(self, key: str, ttl: int = 86400) -> bool:
        """Atomically check if key exists, setting it with TTL if absent.

        Uses Redis SET with NX (Not eXists) and EX (EXpire seconds).

        Args:
            key: Fingerprint or cache key.
            ttl: Time-to-live in seconds (default: 86400 = 24h).

        Returns:
            True if the item is a DUPLICATE (hit: already existed).
            False if the item is NEW (miss: was set successfully).

        Raises:
            CacheError: If the Redis operation fails.
        """
        try:
            was_set = await self._client.set(name=key, value="1", ex=ttl, nx=True)
            if was_set:
                # Key was newly set: not a duplicate -> Cache Miss
                CACHE_MISSES_TOTAL.labels(cache_name=self.name).inc()
                return False

            # Key already existed: duplicate -> Cache Hit
            CACHE_HITS_TOTAL.labels(cache_name=self.name).inc()
            return True
        except RedisError as e:
            raise CacheError(f"Redis check_and_set failed for key '{key}': {e}") from e

    async def is_duplicate(self, key: str) -> bool:
        """Check whether a key exists in the cache without setting it.

        Args:
            key: Fingerprint or cache key.

        Returns:
            True if key exists (hit), False otherwise (miss).

        Raises:
            CacheError: If the Redis operation fails.
        """
        try:
            count = await self._client.exists(key)
            if count > 0:
                CACHE_HITS_TOTAL.labels(cache_name=self.name).inc()
                return True

            CACHE_MISSES_TOTAL.labels(cache_name=self.name).inc()
            return False
        except RedisError as e:
            raise CacheError(f"Redis is_duplicate check failed for key '{key}': {e}") from e

    async def set_fingerprint(self, key: str, ttl: int = 86400) -> bool:
        """Explicitly set a fingerprint key with TTL.

        Args:
            key: Fingerprint or cache key.
            ttl: Time-to-live in seconds.

        Returns:
            True if key was set successfully.

        Raises:
            CacheError: If the Redis operation fails.
        """
        try:
            await self._client.set(name=key, value="1", ex=ttl)
            return True
        except RedisError as e:
            raise CacheError(f"Redis set_fingerprint failed for key '{key}': {e}") from e

    async def delete(self, key: str) -> bool:
        """Remove a fingerprint key from cache.

        Args:
            key: Fingerprint or cache key.

        Returns:
            True if deleted, False if key did not exist.
        """
        try:
            deleted = await self._client.delete(key)
            return bool(deleted > 0)
        except RedisError as e:
            raise CacheError(f"Redis delete failed for key '{key}': {e}") from e

    async def close(self) -> None:
        """Close the Redis client connection if owned."""
        if self._owns_client and self._client is not None:
            await self._client.aclose()
