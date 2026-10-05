# Issue 12: Document summarization and OpenAI embedding generation

**Branch:** `feature/issue-12-embeddings-module`  
**Status:** In Progress  
**PR:** TBD  
**Milestone:** M3 — NLP & AI Enrichment Layer  

---

## Objective

Build `src/market_intel/transformers/embeddings.py` to provide asynchronous document summarization and vector embedding generation using OpenAI API models (`gpt-4o-mini` and `text-embedding-3-small`), protected by a dual-constraint token-bucket rate limiter (RPM and TPM) and safe token counting/truncation.

---

## Acceptance Criteria

- [x] **Financial Summarization**: Summarize documents using `gpt-4o-mini` with a specialized financial prompt template (key performance metrics, revenue/profit guidance, catalysts) and strict length limit ($\le 150$ completion tokens).
- [x] **Vector Embeddings**: Generate 1536-dimensional embeddings using OpenAI `text-embedding-3-small` model.
- [x] **Dual Rate Limiter**: Asynchronous token-bucket rate limiter enforcing both Requests Per Minute (RPM) and Tokens Per Minute (TPM) limits with non-blocking delays (`asyncio.sleep`).
- [x] **Token Counting & Safe Truncation**: Exact BPE token counting with `tiktoken` (plus fallback heuristic) and pre-request text truncation to prevent context window overflow.
- [x] **Concurrent Document Enrichment**: Async workflow (`enrich_document_async`) executing summary and embedding generation concurrently via `asyncio.gather`.
- [x] **Batch Processing**: High-throughput batch embedding generation (`generate_embeddings_batch_async`) with configurable batch sizes.
- [x] **Unit Tests**: Full unit test coverage (`pytest -m issue_12`) with mocked `AsyncOpenAI` client verifying summarization, 1536-dim embeddings, rate-limiting delays, token counting/truncation, retry backoff on 429 errors, and concurrency.

---

## Implementation Tasks

### 1. Preparation & Branching
```bash
make start-issue ID=12 NAME=embeddings-module
```

### 2. Configuration & Schema
- **File**: `pyproject.toml`
  - Add `tiktoken>=0.7.0` to `[project.optional-dependencies] nlp`.
- **File**: `src/market_intel/core/config.py`
  - Add `openai_summary_model` (`gpt-4o-mini`).
  - Add `openai_embedding_model` (`text-embedding-3-small`).
  - Add `openai_embedding_dimensions` (`1536`).
  - Add `openai_max_rpm` (`500`).
  - Add `openai_max_tpm` (`200000`).
- **File**: `src/market_intel/core/schemas.py`
  - Define `SummaryResult`, `EmbeddingResult`, and `DocumentEnrichmentResult` Pydantic models with strict validation.
- **File**: `src/market_intel/core/__init__.py`
  - Re-export `SummaryResult`, `EmbeddingResult`, and `DocumentEnrichmentResult`.

### 3. Embeddings & Summarization Pipeline
- **File**: `src/market_intel/transformers/embeddings.py`
  - Implement token utilities:
    - `count_tokens(text: str, model: str) -> int` (with `tiktoken` and fallback).
    - `truncate_text_to_tokens(text: str, max_tokens: int, model: str) -> str`.
  - Implement `AsyncRateLimiter`:
    - Tracks RPM and TPM using a sliding window / token bucket.
    - `acquire(tokens: int) -> None` async non-blocking wait.
  - Implement `DocumentTransformer`:
    - Async client initialization with fallback/mock support.
    - `summarize_text_async(text: str) -> SummaryResult`.
    - `generate_embedding_async(text: str) -> EmbeddingResult`.
    - `generate_embeddings_batch_async(texts: Sequence[str], batch_size: int) -> list[EmbeddingResult]`.
    - `enrich_document_async(text: str) -> DocumentEnrichmentResult`.
    - Synchronous wrapper methods (`summarize_text`, `generate_embedding`, `generate_embeddings_batch`, `enrich_document`).
    - Exponential backoff retry on HTTP 429 rate limits or network issues.
- **File**: `src/market_intel/transformers/__init__.py`
  - Re-export `DocumentTransformer`, `SummaryResult`, `EmbeddingResult`, `DocumentEnrichmentResult`.

### 4. Test Suite
- **File**: `tests/unit/test_embeddings_pipeline.py`
  - Fast, isolated unit tests using mocked `AsyncOpenAI` responses.
  - Verify financial summary generation with prompt template and $\le 150$ tokens.
  - Verify 1536-dimensional vector embedding generation.
  - Verify token counting and safe truncation.
  - Verify rate limiter throttling when exceeding simulated limits.
  - Verify batch embedding ordering and chunking.
  - Verify concurrent document enrichment.
  - Verify empty/whitespace input handling.
  - Verify retry backoff on 429 rate limit errors.

### 5. Verification
```bash
make test-issue ID=12
make check
```

### 6. Git & Finish
```bash
make finish-issue ID=12 MSG="feat(nlp): implement document summarization and OpenAI embedding generation"
```
