# Issue 11: Named entity recognition and financial sector tagging

**Branch:** `feature/issue-11-ner-sector-tagging`  
**Status:** In Progress  
**PR:** TBD  
**Milestone:** M3 — NLP & AI Enrichment Layer  

---

## Objective

Build `src/market_intel/transformers/ner.py` to extract financial named entities (companies, monetary amounts, percentages, and dates) using SpaCy (`en_core_web_trf`), normalize company names to ticker symbols via an alias-aware lookup table, and tag documents with standard GICS industry sectors.

---

## Acceptance Criteria

- [x] **SpaCy Integration**: Extraction of financial entities (`ORG`, `MONEY`, `PERCENT`, `DATE`) using SpaCy `en_core_web_trf` (with lazy loading and test injection support).
- [x] **Ticker Normalization**: Map identified company names and aliases (e.g., "Apple Inc.", "Microsoft Corp.") to standard ticker symbols (`AAPL`, `MSFT`) via a normalized lookup table.
- [x] **GICS Sector Tagging**: Assign Global Industry Classification Standard (GICS) sector tags based on recognized ticker symbols.
- [x] **Typed Schema**: Return `NERResult(entities, tickers, sectors, detailed_entities)` per analyzed document.
- [x] **Batch Processing**: Support high-throughput batch extraction (`extract_batch`) using SpaCy's `nlp.pipe`.
- [x] **Unit Tests**: Full unit test coverage (`pytest -m issue_11`) validating entity extraction, ticker normalization, GICS tagging, batch processing, and edge cases.

---

## Implementation Tasks

### 1. Preparation & Branching
```bash
make start-issue ID=11 NAME=ner-sector-tagging
```

### 2. Configuration & Schema
- **File**: `pyproject.toml`
  - Add `spacy>=3.7.0` to `[project.optional-dependencies] nlp`.
- **File**: `src/market_intel/core/config.py`
  - Add `spacy_ner_model` setting (default `"en_core_web_trf"`).
- **File**: `src/market_intel/core/schemas.py`
  - Define `EntityItem` and `NERResult` models.
- **File**: `src/market_intel/core/__init__.py`
  - Re-export `NERResult` and `EntityItem`.

### 3. NER and Sector Tagging Pipeline
- **File**: `src/market_intel/transformers/ner.py`
  - Implement `FinancialNERExtractor`:
    - Lookup dictionaries: `DEFAULT_COMPANY_TO_TICKER` (with alias normalization) and `TICKER_TO_GICS_SECTOR`.
    - Lazy loading of SpaCy transformer model.
    - Filtering of entity types: `ORG`, `MONEY`, `PERCENT`, `DATE`.
    - `extract_text(text: str) -> NERResult`.
    - `extract_batch(texts: Sequence[str], batch_size: int = 32) -> list[NERResult]`.
- **File**: `src/market_intel/transformers/__init__.py`
  - Re-export `FinancialNERExtractor`, `NERResult`, and `EntityItem`.

### 4. Test Suite
- **File**: `tests/unit/test_ner_pipeline.py`
  - Fast, isolated unit tests using mock SpaCy doc/spans.
  - Verify entity extraction (`ORG`, `MONEY`, `PERCENT`, `DATE`).
  - Verify company name normalization and corporate suffix cleaning.
  - Verify GICS sector tagging.
  - Verify batch extraction and ordering.
  - Verify empty/whitespace text handling.
  - Verify custom lookup table injection.

### 5. Verification
```bash
make test-issue ID=11
make check
```

### 6. Git & Finish
```bash
make finish-issue ID=11 MSG="feat(nlp): implement named entity recognition and financial sector tagging"
```
