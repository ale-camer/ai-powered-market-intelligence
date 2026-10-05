# Issue 13: Anomaly detection on financial time-series data

**Branch:** `feature/issue-13-anomaly-detection`  
**Status:** In Progress  
**PR:** TBD  
**Milestone:** M3 — NLP & AI Enrichment Layer  

---

## Objective

Build `src/market_intel/transformers/anomaly.py` for statistical and machine-learning-based anomaly detection on financial price and volume time-series data. Implement univariate spike detection (Z-score and IQR) and multivariate outlier detection (Isolation Forest), returning typed `AnomalyResult` schemas per data point with environment-variable configurable thresholds.

---

## Acceptance Criteria

- [x] **Z-score Spike Detection**: Detect price and volume spikes based on standardized deviation from rolling/batch mean with configurable threshold (`ANOMALY_ZSCORE_THRESHOLD`, default `3.0`).
- [x] **IQR Outlier Detection**: Interquartile range ($Q_1, Q_3, IQR$) outlier filter with configurable multiplier (`ANOMALY_IQR_MULTIPLIER`, default `1.5`).
- [x] **Isolation Forest Model**: Multivariate anomaly detection combining multiple financial features (e.g., price and volume changes) with configurable contamination rate (`ANOMALY_IFOREST_CONTAMINATION`, default `0.05`).
- [x] **Typed Schema**: Return standardized `AnomalyResult(is_anomaly, score, method, details)` per analyzed data point.
- [x] **Configurable Thresholds**: Support global configuration via environment variables in `Settings` and per-call parameter overrides.
- [x] **Unit Tests with Synthetic Data**: Fast unit test suite (`pytest -m issue_13`) validating Z-score, IQR, Isolation Forest, edge cases (zero variance, small sample sizes, empty lists), and `PriceSchema` ingestion.

---

## Implementation Tasks

### 1. Preparation & Branching
```bash
make start-issue ID=13 NAME=anomaly-detection
```

### 2. Configuration & Schema
- **File**: `pyproject.toml`
  - Add `scikit-learn>=1.4.0` and `numpy>=1.26.0` to `[project.optional-dependencies] nlp`.
  - Register `issue_13: tests for Issue #13` marker (already present).
- **File**: `src/market_intel/core/config.py`
  - Add `anomaly_zscore_threshold` (default `3.0`).
  - Add `anomaly_iqr_multiplier` (default `1.5`).
  - Add `anomaly_iforest_contamination` (default `0.05`).
- **File**: `src/market_intel/core/schemas.py`
  - Define `AnomalyResult` Pydantic model with strict validation.
- **File**: `src/market_intel/core/__init__.py`
  - Re-export `AnomalyResult`.

### 3. Anomaly Detection Pipeline
- **File**: `src/market_intel/transformers/anomaly.py`
  - Statistical calculation utilities:
    - Pure-Python mean, standard deviation, percentiles ($Q_1, Q_3$).
  - `TimeSeriesAnomalyDetector`:
    - `detect_zscore(values: Sequence[float], threshold: float | None = None) -> list[AnomalyResult]`.
    - `detect_iqr(values: Sequence[float], multiplier: float | None = None) -> list[AnomalyResult]`.
    - `detect_isolation_forest(features: Sequence[Sequence[float]], contamination: float | None = None) -> list[AnomalyResult]`.
    - `detect_price_volume_anomalies(records: Sequence[PriceSchema | dict[str, object]], method: str = "zscore") -> list[AnomalyResult]`.
    - Graceful handling of constant series (zero standard deviation), small sample sizes ($N < 4$), and missing values.
    - Test injection / fallback support for Isolation Forest estimator.
- **File**: `src/market_intel/transformers/__init__.py`
  - Re-export `TimeSeriesAnomalyDetector` and `AnomalyResult`.

### 4. Test Suite
- **File**: `tests/unit/test_anomaly_detection.py`
  - Tests marked with `@pytest.mark.unit` and `@pytest.mark.issue_13`.
  - Synthetic price and volume series generation (sine waves, trend + injected spikes).
  - Verify Z-score spike detection on known outliers.
  - Verify IQR fence calculation and outlier classification.
  - Verify Isolation Forest multivariate detection identifying joint price/volume dislocations.
  - Verify `PriceSchema` batch processing.
  - Verify threshold configurability via environment variables.
  - Verify edge cases: flat prices (zero variance), single-element inputs, empty lists.

### 5. Verification
```bash
make test-issue ID=13
make check
```

### 6. Git & Finish (Cierre de Issue y Milestone M3)
```bash
make finish-issue ID=13 MSG="feat(nlp): implement statistical and isolation forest anomaly detection on time-series"
make finish-milestone MILESTONE=M3
```
