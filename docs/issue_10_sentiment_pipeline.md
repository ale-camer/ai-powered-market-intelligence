# Issue 10: Sentiment analysis pipeline using FinBERT and GPT-4o

**Branch:** `feature/issue-10-sentiment-pipeline`  
**Status:** In Progress  
**PR:** TBD  
**Milestone:** M3 — NLP & AI Enrichment Layer  

---

## Objective

Implement `src/market_intel/transformers/sentiment.py` for financial sentiment scoring. The pipeline uses HuggingFace FinBERT (`ProsusAI/finbert`) for batch inference and incorporates a GPT-4o fallback via OpenAI API for ambiguous or short texts, returning standardized `SentimentResult` models per document.

---

## Acceptance Criteria

- [x] **FinBERT Model**: HuggingFace `ProsusAI/finbert` integration for batch inference with continuous score `[-1.0, 1.0]` and categorical labels (`positive`, `negative`, `neutral`).
- [x] **GPT-4o Fallback**: Automatic fallback to GPT-4o via OpenAI API when input text is too short or FinBERT confidence is below threshold.
- [x] **Typed Schema**: Return `SentimentResult(label, score, model_used, confidence, explanation)` per analyzed document.
- [x] **Configurable Batch Processing**: High-throughput batch inference supporting customizable `batch_size`.
- [x] **Unit Tests**: Full unit test coverage with mocked fixtures (`pytest -m issue_10`) verifying positive/negative/neutral scoring, short-text fallback, low-confidence fallback, and batch processing.

---

## Implementation Tasks

### 1. Preparation & Branching
```bash
make start-issue ID=10 NAME=sentiment-pipeline
```

### 2. Configuration & Schema
- **File**: `pyproject.toml`
  - Add NLP optional dependencies: `transformers`, `torch`, `openai`.
- **File**: `src/market_intel/core/config.py`
  - Add `finbert_model_name`, `sentiment_confidence_threshold`, `sentiment_min_text_length`, `sentiment_batch_size`.
- **File**: `src/market_intel/core/schemas.py`
  - Add `SentimentResult` Pydantic model with strict validation.

### 3. Sentiment Analysis Pipeline
- **File**: `src/market_intel/transformers/sentiment.py`
  - Implement `SentimentAnalyzer` class:
    - Lazy model & tokenizer loading.
    - Batch tokenization and forward pass.
    - Softmax label probability & compound score calculation.
    - Ambiguity and short-text detection heuristic.
    - OpenAI GPT-4o structured fallback integration with error handling.
    - `analyze_batch(texts, batch_size)` and `analyze_text(text)`.
- **File**: `src/market_intel/transformers/__init__.py`
  - Re-export `SentimentAnalyzer` and `SentimentResult`.

### 4. Test Suite
- **File**: `tests/unit/test_sentiment_pipeline.py`
  - Fast, isolated unit tests using mocks for FinBERT and OpenAI.
  - Test positive, negative, neutral classification.
  - Test short-text and ambiguous-text fallback trigger.
  - Test batch chunking and ordering.
  - Test empty/whitespace input handling.
  - Test OpenAI failure resilience.

### 5. Verification
```bash
make test-issue ID=10
make check
```

### 6. Git & Finish
```bash
make finish-issue ID=10 MSG="feat(nlp): implement sentiment analysis pipeline using FinBERT and GPT-4o"
```
