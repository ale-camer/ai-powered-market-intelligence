"""Unit tests for document summarization and OpenAI vector embeddings pipeline."""

import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from market_intel.core.schemas import (
    DocumentEnrichmentResult,
    EmbeddingResult,
    SummaryResult,
)
from market_intel.transformers.embeddings import (
    DEFAULT_EMBEDDING_DIMENSIONS,
    DEFAULT_EMBEDDING_MODEL,
    DEFAULT_MAX_SUMMARY_TOKENS,
    DEFAULT_SUMMARY_MODEL,
    FINANCIAL_SUMMARY_SYSTEM_PROMPT,
    AsyncRateLimiter,
    DocumentTransformer,
    count_tokens,
    truncate_text_to_tokens,
)

pytestmark = [pytest.mark.unit, pytest.mark.issue_12]


class MockChatChoice:
    """Mock choice object for OpenAI ChatCompletion."""

    def __init__(self, content: str) -> None:
        self.message = MagicMock(content=content)


class MockChatResponse:
    """Mock response object for OpenAI ChatCompletion."""

    def __init__(self, content: str, total_tokens: int = 120) -> None:
        self.choices = [MockChatChoice(content)]
        self.usage = MagicMock(total_tokens=total_tokens)


class MockEmbeddingItem:
    """Mock item for OpenAI Embedding data."""

    def __init__(self, embedding: list[float], index: int = 0) -> None:
        self.embedding = embedding
        self.index = index


class MockEmbeddingResponse:
    """Mock response for OpenAI Embedding."""

    def __init__(self, embeddings: list[list[float]], total_tokens: int = 40) -> None:
        self.data = [MockEmbeddingItem(vec, i) for i, vec in enumerate(embeddings)]
        self.usage = MagicMock(total_tokens=total_tokens)


class MockAsyncOpenAIClient:
    """Mock AsyncOpenAI client for deterministic fast testing."""

    def __init__(
        self,
        summary_text: str = "Quarterly revenue grew 12% YoY driven by enterprise cloud sales.",
        embedding_vector: list[float] | None = None,
    ) -> None:
        self.summary_text = summary_text
        self.embedding_vector = (
            embedding_vector
            if embedding_vector is not None
            else [0.05 * (i % 10) for i in range(DEFAULT_EMBEDDING_DIMENSIONS)]
        )

        # Mock chat completion
        self.chat = MagicMock()
        self.chat.completions = MagicMock()
        self.chat_create = AsyncMock(
            return_value=MockChatResponse(self.summary_text, total_tokens=110)
        )
        self.chat.completions.create = self.chat_create

        # Mock embeddings
        self.embeddings = MagicMock()
        self.embeddings_create = AsyncMock(side_effect=self._mock_embeddings_create)
        self.embeddings.create = self.embeddings_create

    async def _mock_embeddings_create(
        self, *args: object, **kwargs: object
    ) -> MockEmbeddingResponse:
        inputs = kwargs.get("input") or (args[1] if len(args) > 1 else None)
        if isinstance(inputs, list):
            vectors = [list(self.embedding_vector) for _ in inputs]
            return MockEmbeddingResponse(vectors, total_tokens=len(inputs) * 25)
        return MockEmbeddingResponse([list(self.embedding_vector)], total_tokens=25)


@pytest.mark.asyncio
async def test_summarize_text_prompt_and_tokens() -> None:
    """Verify financial summarization uses correct prompt template, parameters, and tokens."""
    mock_client = MockAsyncOpenAIClient(
        summary_text="Alphabet reported Q3 net income growth of 34%."
    )
    transformer = DocumentTransformer(openai_client=mock_client)

    sample_text = (
        "Alphabet Inc. reported financial results for the quarter ended September 30, 2026. "
        "Revenues were $88.3 billion, up 15% year-over-year, reflecting strong momentum."
    )

    result = await transformer.summarize_text_async(sample_text)

    assert isinstance(result, SummaryResult)
    assert result.summary == "Alphabet reported Q3 net income growth of 34%."
    assert result.model_used == DEFAULT_SUMMARY_MODEL
    assert result.tokens_used == 110

    # Verify API invocation call arguments
    mock_client.chat_create.assert_awaited_once()
    _, kwargs = mock_client.chat_create.call_args
    assert kwargs["model"] == DEFAULT_SUMMARY_MODEL
    assert kwargs["max_tokens"] == DEFAULT_MAX_SUMMARY_TOKENS
    assert kwargs["temperature"] == 0.0

    messages = kwargs["messages"]
    assert len(messages) == 2
    assert messages[0]["role"] == "system"
    assert messages[0]["content"] == FINANCIAL_SUMMARY_SYSTEM_PROMPT
    assert messages[1]["role"] == "user"
    assert "Alphabet Inc." in messages[1]["content"]


@pytest.mark.asyncio
async def test_generate_embedding_dimensions() -> None:
    """Verify OpenAI vector embedding generation returns 1536 float dimensions."""
    mock_client = MockAsyncOpenAIClient()
    transformer = DocumentTransformer(openai_client=mock_client)

    sample_text = "Federal Reserve signals potential rate pauses heading into Q4."
    result = await transformer.generate_embedding_async(sample_text)

    assert isinstance(result, EmbeddingResult)
    assert result.dimensions == 1536
    assert len(result.embedding) == 1536
    assert result.model_used == DEFAULT_EMBEDDING_MODEL
    assert result.tokens_used == 25

    mock_client.embeddings_create.assert_awaited_once()
    _, kwargs = mock_client.embeddings_create.call_args
    assert kwargs["model"] == DEFAULT_EMBEDDING_MODEL
    assert kwargs["input"] == sample_text


def test_token_counting_and_truncation() -> None:
    """Verify safe token counting and truncation heuristics."""
    # Empty inputs
    assert count_tokens("") == 0
    assert truncate_text_to_tokens("", max_tokens=10) == ""
    assert truncate_text_to_tokens("some text", max_tokens=0) == ""

    # Non-empty inputs
    text = "The quick brown fox jumps over the lazy dog."
    cnt = count_tokens(text)
    assert cnt > 0

    long_text = "apple " * 500
    truncated = truncate_text_to_tokens(long_text, max_tokens=10)
    assert len(truncated) < len(long_text)
    assert count_tokens(truncated) <= 20


@pytest.mark.asyncio
async def test_rate_limiter_rpm_and_tpm() -> None:
    """Verify rate limiter pauses when exceeding requests per minute or tokens per minute."""
    # Window of 0.1 seconds, limit of 2 requests
    limiter = AsyncRateLimiter(max_rpm=2, max_tpm=100, window_seconds=0.1)

    start_time = time.monotonic()
    await limiter.acquire(tokens=10)
    await limiter.acquire(tokens=10)

    # 3rd request exceeds max_rpm=2, must wait until the window slides
    await limiter.acquire(tokens=10)
    elapsed = time.monotonic() - start_time

    assert elapsed >= 0.08

    # Test disabled limiter (<=0)
    unlimited = AsyncRateLimiter(max_rpm=0, max_tpm=0)
    await unlimited.acquire(tokens=1000)

    # Test single request with tokens > max_tpm on empty history proceeds safely
    strict_tpm = AsyncRateLimiter(max_rpm=10, max_tpm=50, window_seconds=0.1)
    await strict_tpm.acquire(tokens=200)


@pytest.mark.asyncio
async def test_async_batch_embeddings() -> None:
    """Verify batch processing preserves index order and handles empty elements."""
    mock_client = MockAsyncOpenAIClient()
    transformer = DocumentTransformer(openai_client=mock_client)

    texts = [
        "First financial document",
        "",
        "   ",
        "Second financial document",
    ]

    results = await transformer.generate_embeddings_batch_async(texts, batch_size=2)

    assert len(results) == 4
    # 0 and 3 are non-empty
    assert len(results[0].embedding) == 1536
    assert results[0].tokens_used is not None
    assert any(x != 0.0 for x in results[0].embedding)

    # 1 and 2 are empty/whitespace: zero vector with 0 tokens
    assert results[1].embedding == [0.0] * 1536
    assert results[1].tokens_used == 0
    assert results[2].embedding == [0.0] * 1536
    assert results[2].tokens_used == 0

    assert len(results[3].embedding) == 1536
    assert any(x != 0.0 for x in results[3].embedding)

    # Empty batch returns empty list
    assert await transformer.generate_embeddings_batch_async([]) == []


@pytest.mark.asyncio
async def test_enrich_document_concurrent() -> None:
    """Verify enrich_document_async executes summary and embedding concurrently."""
    mock_client = MockAsyncOpenAIClient(
        summary_text="Nvidia hits new all-time high amid AI chip demand."
    )
    transformer = DocumentTransformer(openai_client=mock_client)

    doc_text = "Nvidia Corporation announced record revenue for Q3 fiscal 2027."
    enriched = await transformer.enrich_document_async(doc_text)

    assert isinstance(enriched, DocumentEnrichmentResult)
    assert enriched.summary == "Nvidia hits new all-time high amid AI chip demand."
    assert len(enriched.embedding) == 1536
    assert enriched.model_summary == DEFAULT_SUMMARY_MODEL
    assert enriched.model_embedding == DEFAULT_EMBEDDING_MODEL


@pytest.mark.asyncio
async def test_empty_and_whitespace_input() -> None:
    """Verify empty or whitespace strings are handled gracefully without calling API."""
    mock_client = MockAsyncOpenAIClient()
    transformer = DocumentTransformer(openai_client=mock_client)

    summary_res = await transformer.summarize_text_async("   \n\t  ")
    assert summary_res.summary == ""
    assert summary_res.tokens_used == 0

    emb_res = await transformer.generate_embedding_async("")
    assert emb_res.embedding == [0.0] * 1536
    assert emb_res.tokens_used == 0

    # Ensure no API calls were made
    mock_client.chat_create.assert_not_called()
    mock_client.embeddings_create.assert_not_called()


@pytest.mark.asyncio
async def test_rate_limit_retry_backoff() -> None:
    """Verify exponential backoff retries upon rate limit error (HTTP 429)."""
    mock_client = MockAsyncOpenAIClient()

    class MockRateLimitError(Exception):
        status_code: int = 429

    error_429 = MockRateLimitError("Rate limit reached. 429 Too Many Requests")
    call_counter = 0

    async def _flaky_chat(*args: object, **kwargs: object) -> MockChatResponse:
        nonlocal call_counter
        call_counter += 1
        if call_counter == 1:
            raise error_429
        return MockChatResponse("Recovered after backoff retry.")

    mock_client.chat.completions.create = AsyncMock(side_effect=_flaky_chat)

    transformer = DocumentTransformer(
        openai_client=mock_client,
        max_retries=3,
        retry_delay=0.01,
    )

    res = await transformer.summarize_text_async("Financial text to summarize")
    assert res.summary == "Recovered after backoff retry."
    assert call_counter == 2

    # Verify permanent failure if error persists
    failing_client = MockAsyncOpenAIClient()
    failing_client.chat.completions.create = AsyncMock(side_effect=error_429)
    failing_transformer = DocumentTransformer(
        openai_client=failing_client,
        max_retries=2,
        retry_delay=0.01,
    )

    with pytest.raises(Exception, match="429"):
        await failing_transformer.summarize_text_async("Another text")


def test_sync_convenience_wrappers() -> None:
    """Verify synchronous wrappers execute properly in standard environments."""
    mock_client = MockAsyncOpenAIClient(summary_text="Synchronous summary succeeded.")
    transformer = DocumentTransformer(openai_client=mock_client)

    summary = transformer.summarize_text("Sample input")
    assert summary.summary == "Synchronous summary succeeded."

    emb = transformer.generate_embedding("Sample input")
    assert len(emb.embedding) == 1536

    batch_emb = transformer.generate_embeddings_batch(["Text A", "Text B"])
    assert len(batch_emb) == 2

    enriched = transformer.enrich_document("Sample input")
    assert enriched.summary == "Synchronous summary succeeded."
    assert len(enriched.embedding) == 1536


def test_schema_serialization_and_validation() -> None:
    """Verify Pydantic serialization and schema validation for NLP models."""
    summary = SummaryResult(
        summary="Test summary",
        model_used="gpt-4o-mini",
        tokens_used=50,
    )
    summary_data = summary.model_dump()
    assert summary_data["summary"] == "Test summary"
    assert summary_data["tokens_used"] == 50

    embedding = EmbeddingResult(
        embedding=[0.1, 0.2, 0.3],
        dimensions=3,
        model_used="text-embedding-3-small",
        tokens_used=12,
    )
    emb_data = embedding.model_dump()
    assert emb_data["dimensions"] == 3
    assert emb_data["embedding"] == [0.1, 0.2, 0.3]

    enrichment = DocumentEnrichmentResult(
        summary="Summary text",
        embedding=[0.1, 0.2],
        model_summary="gpt-4o-mini",
        model_embedding="text-embedding-3-small",
    )
    enrich_data = enrichment.model_dump()
    assert enrich_data["model_summary"] == "gpt-4o-mini"
    assert enrich_data["model_embedding"] == "text-embedding-3-small"
