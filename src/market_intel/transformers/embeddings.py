"""Document summarization and OpenAI vector embedding pipeline."""

import asyncio
import time
from collections import deque
from collections.abc import Callable, Coroutine, Sequence
from typing import Any, TypeVar, cast

from market_intel.core.config import get_settings
from market_intel.core.logger import get_logger
from market_intel.core.schemas import (
    DocumentEnrichmentResult,
    EmbeddingResult,
    SummaryResult,
)

logger = get_logger(__name__)

T = TypeVar("T")

DEFAULT_SUMMARY_MODEL = "gpt-4o-mini"
DEFAULT_EMBEDDING_MODEL = "text-embedding-3-small"
DEFAULT_EMBEDDING_DIMENSIONS = 1536
DEFAULT_MAX_RPM = 500
DEFAULT_MAX_TPM = 200000
DEFAULT_CONTEXT_WINDOW = 8000
DEFAULT_MAX_SUMMARY_TOKENS = 150

FINANCIAL_SUMMARY_SYSTEM_PROMPT = (
    "You are an expert financial market analyst. Provide a concise, high-impact "
    "executive summary of the following financial text. Focus on: key financial metrics, "
    "revenue/profit guidance, macroeconomic impact, and market catalysts. "
    "Keep the summary strictly under 150 words/tokens, professional, and factual."
)


def _get_encoding(model: str) -> object | None:
    """Safely obtain tiktoken encoding for model with fallback."""
    try:
        import tiktoken

        try:
            return cast(object, tiktoken.encoding_for_model(model))
        except KeyError:
            return cast(object, tiktoken.get_encoding("cl100k_base"))
    except (ImportError, Exception):
        return None


def count_tokens(text: str, model: str = DEFAULT_EMBEDDING_MODEL) -> int:
    """Count tokens in text using tiktoken or heuristic character fallback.

    Args:
        text: Input string to tokenize.
        model: OpenAI model name.

    Returns:
        Estimated or exact token count (>= 0).
    """
    if not text:
        return 0

    enc = _get_encoding(model)
    if enc is not None:
        try:
            return len(enc.encode(text))  # type: ignore[attr-defined]
        except Exception:
            pass

    # Heuristic fallback: ~4 characters per token
    return max(1, len(text) // 4)


def truncate_text_to_tokens(
    text: str,
    max_tokens: int,
    model: str = DEFAULT_EMBEDDING_MODEL,
) -> str:
    """Truncate text to at most max_tokens using tiktoken or heuristic fallback.

    Args:
        text: Input text to truncate.
        max_tokens: Maximum allowed tokens.
        model: OpenAI model name for encoding.

    Returns:
        Truncated text string.
    """
    if not text or max_tokens <= 0:
        return ""

    enc = _get_encoding(model)
    if enc is not None:
        try:
            tokens = enc.encode(text)  # type: ignore[attr-defined]
            if len(tokens) <= max_tokens:
                return text
            return enc.decode(tokens[:max_tokens])  # type: ignore[attr-defined,no-any-return]
        except Exception:
            pass

    # Heuristic fallback
    max_chars = max_tokens * 4
    return text[:max_chars]


class AsyncRateLimiter:
    """Asynchronous dual-constraint rate limiter tracking requests (RPM) and tokens (TPM).

    Uses a sliding-window token bucket with non-blocking delays via asyncio.sleep.
    """

    def __init__(
        self,
        max_rpm: int = DEFAULT_MAX_RPM,
        max_tpm: int = DEFAULT_MAX_TPM,
        window_seconds: float = 60.0,
    ) -> None:
        """Initialize the rate limiter.

        Args:
            max_rpm: Maximum requests allowed per window.
            max_tpm: Maximum tokens allowed per window.
            window_seconds: Window duration in seconds (default: 60.0).
        """
        self.max_rpm = max_rpm
        self.max_tpm = max_tpm
        self.window_seconds = window_seconds
        self._history: deque[tuple[float, int]] = deque()
        self._lock = asyncio.Lock()

    async def acquire(self, tokens: int = 0) -> None:
        """Acquire permission to execute a request consuming the given token count.

        Suspends execution non-blockingly if rate limits would be exceeded.

        Args:
            tokens: Number of tokens consumed by the upcoming request.
        """
        if self.max_rpm <= 0 and self.max_tpm <= 0:
            return

        async with self._lock:
            while True:
                now = time.monotonic()
                cutoff = now - self.window_seconds

                # Purge history outside current sliding window
                while self._history and self._history[0][0] <= cutoff:
                    self._history.popleft()

                current_rpm = len(self._history)
                current_tpm = sum(t for _, t in self._history)

                # Special case: single request exceeds max_tpm when history is empty
                if self.max_tpm > 0 and tokens > self.max_tpm and not self._history:
                    logger.warning(
                        "Request token count (%d) exceeds max_tpm (%d); proceeding anyway.",
                        tokens,
                        self.max_tpm,
                    )
                    self._history.append((now, tokens))
                    return

                rpm_exceeded = (self.max_rpm > 0) and (current_rpm + 1 > self.max_rpm)
                tpm_exceeded = (self.max_tpm > 0) and (current_tpm + tokens > self.max_tpm)

                if not rpm_exceeded and not tpm_exceeded:
                    self._history.append((now, tokens))
                    return

                # Calculate non-blocking wait time until the earliest item leaves window
                if self._history:
                    oldest_ts = self._history[0][0]
                    wait_seconds = max(0.001, (oldest_ts + self.window_seconds) - now + 0.005)
                else:
                    wait_seconds = 0.05

                await asyncio.sleep(wait_seconds)


class DocumentTransformer:
    """Asynchronous document summarization and vector embedding pipeline.

    Leverages OpenAI's gpt-4o-mini for financial summaries (<= 150 tokens) and
    text-embedding-3-small for 1536-dimensional vector representations.
    """

    def __init__(
        self,
        summary_model: str | None = None,
        embedding_model: str | None = None,
        embedding_dimensions: int | None = None,
        max_rpm: int | None = None,
        max_tpm: int | None = None,
        rate_limiter: AsyncRateLimiter | None = None,
        openai_client: object | None = None,
        max_retries: int = 3,
        retry_delay: float = 1.0,
    ) -> None:
        """Initialize the DocumentTransformer pipeline.

        Args:
            summary_model: Model used for text summarization.
            embedding_model: Model used for vector embeddings.
            embedding_dimensions: Expected embedding dimensions.
            max_rpm: Maximum requests per minute.
            max_tpm: Maximum tokens per minute.
            rate_limiter: Optional custom AsyncRateLimiter instance.
            openai_client: Optional pre-configured AsyncOpenAI client instance.
            max_retries: Maximum retries on API rate-limit/network failures.
            retry_delay: Initial backoff delay in seconds.
        """
        settings = get_settings()

        self.summary_model = summary_model or settings.openai_summary_model or DEFAULT_SUMMARY_MODEL
        self.embedding_model = (
            embedding_model or settings.openai_embedding_model or DEFAULT_EMBEDDING_MODEL
        )
        self.embedding_dimensions = (
            embedding_dimensions
            if embedding_dimensions is not None
            else settings.openai_embedding_dimensions or DEFAULT_EMBEDDING_DIMENSIONS
        )
        self.max_retries = max_retries
        self.retry_delay = retry_delay

        rpm = max_rpm if max_rpm is not None else settings.openai_max_rpm or DEFAULT_MAX_RPM
        tpm = max_tpm if max_tpm is not None else settings.openai_max_tpm or DEFAULT_MAX_TPM
        self.rate_limiter = rate_limiter or AsyncRateLimiter(max_rpm=rpm, max_tpm=tpm)

        self._client = openai_client

    def _get_client(self) -> object:
        """Lazy-initialize or return configured AsyncOpenAI client."""
        if self._client is None:
            try:
                from openai import AsyncOpenAI

                api_key = get_settings().openai_api_key
                self._client = AsyncOpenAI(api_key=api_key or "sk-dummy-key-for-local-testing")
            except Exception as exc:
                logger.error("Failed to initialize AsyncOpenAI client: %s", exc)
                raise RuntimeError(f"AsyncOpenAI client initialization failed: {exc}") from exc
        return self._client

    async def _call_with_retry(
        self,
        api_func: Callable[..., Coroutine[object, object, T]],
        *args: object,
        **kwargs: object,
    ) -> T:
        """Execute an asynchronous API call with exponential backoff on errors."""
        delay = self.retry_delay
        for attempt in range(1, self.max_retries + 1):
            try:
                return await api_func(*args, **kwargs)
            except Exception as exc:
                status_code = getattr(exc, "status_code", None)
                err_str = str(exc).lower()
                is_rate_limit = (
                    status_code == 429
                    or "rate_limit" in type(exc).__name__.lower()
                    or "429" in err_str
                )

                if attempt < self.max_retries:
                    logger.warning(
                        "OpenAI API call failed (attempt %d/%d): %s (rate_limit=%s). "
                        "Retrying in %.2fs...",
                        attempt,
                        self.max_retries,
                        exc,
                        is_rate_limit,
                        delay,
                    )
                    await asyncio.sleep(delay)
                    delay *= 2.0
                else:
                    logger.error(
                        "OpenAI API call permanently failed after %d attempts: %s", attempt, exc
                    )
                    raise

        raise RuntimeError("Unreachable retry loop termination.")

    async def _invoke_chat_summary(self, truncated_input: str) -> object:
        """Internal helper to call chat completions API."""
        client_any = cast(Any, self._get_client())
        return await client_any.chat.completions.create(
            model=self.summary_model,
            messages=[
                {"role": "system", "content": FINANCIAL_SUMMARY_SYSTEM_PROMPT},
                {"role": "user", "content": truncated_input},
            ],
            max_tokens=DEFAULT_MAX_SUMMARY_TOKENS,
            temperature=0.0,
        )

    async def _invoke_single_embedding(self, truncated_input: str) -> object:
        """Internal helper to call embedding API for a single text."""
        client_any = cast(Any, self._get_client())
        return await client_any.embeddings.create(
            model=self.embedding_model,
            input=truncated_input,
        )

    async def _invoke_batch_embeddings(self, inputs: list[str]) -> object:
        """Internal helper to call embedding API for a batch of texts."""
        client_any = cast(Any, self._get_client())
        return await client_any.embeddings.create(
            model=self.embedding_model,
            input=inputs,
        )

    async def summarize_text_async(self, text: str) -> SummaryResult:
        """Summarize financial document asynchronously using gpt-4o-mini (<= 150 tokens).

        Args:
            text: Document text to summarize.

        Returns:
            SummaryResult containing concise summary text and metadata.
        """
        cleaned = text.strip() if text else ""
        if not cleaned:
            return SummaryResult(
                summary="",
                model_used=self.summary_model,
                tokens_used=0,
            )

        truncated_input = truncate_text_to_tokens(
            cleaned,
            max_tokens=DEFAULT_CONTEXT_WINDOW,
            model=self.summary_model,
        )
        input_tokens = count_tokens(truncated_input, model=self.summary_model)
        await self.rate_limiter.acquire(tokens=input_tokens + DEFAULT_MAX_SUMMARY_TOKENS)

        response_raw = await self._call_with_retry(self._invoke_chat_summary, truncated_input)
        response = cast(Any, response_raw)

        summary_text = ""
        if response.choices and response.choices[0].message:
            summary_text = (response.choices[0].message.content or "").strip()

        tokens_used: int | None = None
        if hasattr(response, "usage") and response.usage:
            tokens_used = getattr(response.usage, "total_tokens", None)

        return SummaryResult(
            summary=summary_text,
            model_used=self.summary_model,
            tokens_used=tokens_used,
        )

    async def generate_embedding_async(self, text: str) -> EmbeddingResult:
        """Generate 1536-dimensional vector embedding asynchronously using text-embedding-3-small.

        Args:
            text: Document text to embed.

        Returns:
            EmbeddingResult containing vector float list and metadata.
        """
        cleaned = text.strip() if text else ""
        if not cleaned:
            return EmbeddingResult(
                embedding=[0.0] * self.embedding_dimensions,
                dimensions=self.embedding_dimensions,
                model_used=self.embedding_model,
                tokens_used=0,
            )

        truncated_input = truncate_text_to_tokens(
            cleaned,
            max_tokens=8191,
            model=self.embedding_model,
        )
        input_tokens = count_tokens(truncated_input, model=self.embedding_model)
        await self.rate_limiter.acquire(tokens=input_tokens)

        response_raw = await self._call_with_retry(self._invoke_single_embedding, truncated_input)
        response = cast(Any, response_raw)

        embedding_vector: list[float] = []
        if response.data:
            embedding_vector = [float(x) for x in response.data[0].embedding]

        tokens_used: int | None = None
        if hasattr(response, "usage") and response.usage:
            tokens_used = getattr(response.usage, "total_tokens", None)

        return EmbeddingResult(
            embedding=embedding_vector,
            dimensions=len(embedding_vector),
            model_used=self.embedding_model,
            tokens_used=tokens_used,
        )

    async def generate_embeddings_batch_async(
        self,
        texts: Sequence[str],
        batch_size: int = 32,
    ) -> list[EmbeddingResult]:
        """Generate vector embeddings for multiple documents in batches asynchronously.

        Args:
            texts: Sequence of texts to embed.
            batch_size: Batch size chunk limit.

        Returns:
            List of EmbeddingResult objects in original input order.
        """
        if not texts:
            return []

        effective_batch_size = max(1, batch_size)
        results: list[EmbeddingResult] = []

        for i in range(0, len(texts), effective_batch_size):
            chunk = list(texts[i : i + effective_batch_size])

            # Track empty texts vs non-empty texts to maintain ordering
            chunk_results: list[EmbeddingResult | None] = [None] * len(chunk)
            non_empty_indices: list[int] = []
            non_empty_inputs: list[str] = []

            for idx, text in enumerate(chunk):
                cleaned = text.strip() if text else ""
                if not cleaned:
                    chunk_results[idx] = EmbeddingResult(
                        embedding=[0.0] * self.embedding_dimensions,
                        dimensions=self.embedding_dimensions,
                        model_used=self.embedding_model,
                        tokens_used=0,
                    )
                else:
                    truncated = truncate_text_to_tokens(
                        cleaned,
                        max_tokens=8191,
                        model=self.embedding_model,
                    )
                    non_empty_indices.append(idx)
                    non_empty_inputs.append(truncated)

            if non_empty_inputs:
                total_tokens = sum(
                    count_tokens(inp, model=self.embedding_model) for inp in non_empty_inputs
                )
                await self.rate_limiter.acquire(tokens=total_tokens)

                response_raw = await self._call_with_retry(
                    self._invoke_batch_embeddings,
                    non_empty_inputs,
                )
                response = cast(Any, response_raw)

                avg_tokens = (
                    getattr(response.usage, "total_tokens", 0) // len(non_empty_inputs)
                    if hasattr(response, "usage") and response.usage
                    else None
                )

                # OpenAI returns embeddings sorted by input index
                for target_idx, item in zip(non_empty_indices, response.data, strict=True):
                    vector = [float(x) for x in item.embedding]
                    chunk_results[target_idx] = EmbeddingResult(
                        embedding=vector,
                        dimensions=len(vector),
                        model_used=self.embedding_model,
                        tokens_used=avg_tokens,
                    )

            for res in chunk_results:
                if res is not None:
                    results.append(res)

        return results

    async def enrich_document_async(self, text: str) -> DocumentEnrichmentResult:
        """Enrich a financial document by running summarization and embedding concurrently.

        Args:
            text: Document text to enrich.

        Returns:
            DocumentEnrichmentResult containing summary, embedding vector, and model names.
        """
        summary_res, embedding_res = await asyncio.gather(
            self.summarize_text_async(text),
            self.generate_embedding_async(text),
        )
        return DocumentEnrichmentResult(
            summary=summary_res.summary,
            embedding=embedding_res.embedding,
            model_summary=summary_res.model_used,
            model_embedding=embedding_res.model_used,
        )

    # ──────────────────────────────────────────────────────────────────────────
    # Synchronous Convenience Wrappers
    # ──────────────────────────────────────────────────────────────────────────

    def _run_coroutine_sync(self, coro: Coroutine[object, object, T]) -> T:
        """Execute a coroutine synchronously safely in both sync and async contexts."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop is not None and loop.is_running():
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(asyncio.run, coro)
                return future.result()
        return asyncio.run(coro)

    def summarize_text(self, text: str) -> SummaryResult:
        """Synchronously summarize a financial document."""
        return self._run_coroutine_sync(self.summarize_text_async(text))

    def generate_embedding(self, text: str) -> EmbeddingResult:
        """Synchronously generate an embedding vector for a financial document."""
        return self._run_coroutine_sync(self.generate_embedding_async(text))

    def generate_embeddings_batch(
        self,
        texts: Sequence[str],
        batch_size: int = 32,
    ) -> list[EmbeddingResult]:
        """Synchronously generate embeddings for a batch of documents."""
        return self._run_coroutine_sync(
            self.generate_embeddings_batch_async(texts, batch_size=batch_size)
        )

    def enrich_document(self, text: str) -> DocumentEnrichmentResult:
        """Synchronously enrich a document with summary and embedding."""
        return self._run_coroutine_sync(self.enrich_document_async(text))
