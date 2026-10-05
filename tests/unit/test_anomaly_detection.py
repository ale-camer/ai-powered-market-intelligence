"""Unit tests for statistical and machine-learning anomaly detection on time-series data."""

from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest

from market_intel.core.schemas import AnomalyResult, PriceSchema
from market_intel.transformers.anomaly import (
    DEFAULT_IFOREST_CONTAMINATION,
    DEFAULT_IQR_MULTIPLIER,
    DEFAULT_ZSCORE_THRESHOLD,
    TimeSeriesAnomalyDetector,
    compute_mean,
    compute_percentile,
    compute_stdev,
)

pytestmark = [pytest.mark.unit, pytest.mark.issue_13]


def generate_synthetic_series(n: int = 50, base: float = 100.0, spread: float = 2.0) -> list[float]:
    """Generate deterministic synthetic time series around a base value."""
    # Deterministic pseudo-random variation
    return [base + spread * math_sin_wave(i) for i in range(n)]


def math_sin_wave(idx: int) -> float:
    """Deterministic periodic variation."""
    import math

    return math.sin(idx * 0.4)


# ──────────────────────────────────────────────────────────────────────────────
# Statistical Utilities Unit Tests
# ──────────────────────────────────────────────────────────────────────────────


def test_statistical_helpers() -> None:
    """Verify statistical helper functions with standard values and edge cases."""
    assert compute_mean([]) == 0.0
    assert compute_mean([10.0, 20.0, 30.0]) == 20.0

    assert compute_stdev([]) == 0.0
    assert compute_stdev([42.0]) == 0.0
    assert abs(compute_stdev([10.0, 20.0]) - 7.071) < 0.01

    assert compute_percentile([], 0.5) == 0.0
    assert compute_percentile([42.0], 0.5) == 42.0
    assert compute_percentile([0.0, 100.0], 0.25) == 25.0
    assert compute_percentile([0.0, 100.0], 0.75) == 75.0
    assert compute_percentile([10.0, 20.0, 30.0, 40.0], 0.5) == 25.0


# ──────────────────────────────────────────────────────────────────────────────
# Z-Score Spike Detection Tests
# ──────────────────────────────────────────────────────────────────────────────


def test_zscore_spike_detection() -> None:
    """Verify Z-score accurately identifies injected price and volume spikes."""
    detector = TimeSeriesAnomalyDetector(zscore_threshold=3.0)
    data = generate_synthetic_series(n=60, base=100.0, spread=2.0)

    # Inject extreme positive and negative spikes
    spike_idx_high = 20
    spike_idx_low = 45
    data[spike_idx_high] = 135.0  # ~12+ stdevs above mean
    data[spike_idx_low] = 65.0  # ~12+ stdevs below mean

    results = detector.detect_zscore(data)

    assert len(results) == 60
    assert all(isinstance(r, AnomalyResult) for r in results)

    # Injected spikes must be flagged as anomalies
    assert results[spike_idx_high].is_anomaly is True
    assert results[spike_idx_high].score > 3.0
    assert results[spike_idx_high].method == "zscore"
    assert results[spike_idx_high].details is not None
    assert results[spike_idx_high].details["value"] == 135.0

    assert results[spike_idx_low].is_anomaly is True
    assert results[spike_idx_low].score > 3.0
    assert results[spike_idx_low].details is not None
    assert results[spike_idx_low].details["value"] == 65.0

    # Normal points should not be flagged
    assert results[0].is_anomaly is False
    assert results[10].is_anomaly is False
    assert results[30].is_anomaly is False


# ──────────────────────────────────────────────────────────────────────────────
# IQR Outlier Detection Tests
# ──────────────────────────────────────────────────────────────────────────────


def test_iqr_outlier_detection() -> None:
    """Verify IQR outlier detection detects data outside interquartile fences."""
    detector = TimeSeriesAnomalyDetector(iqr_multiplier=1.5)
    data = generate_synthetic_series(n=50, base=50.0, spread=1.5)

    # Inject extreme outlier
    outlier_idx = 15
    data[outlier_idx] = 95.0

    results = detector.detect_iqr(data)

    assert len(results) == 50
    assert results[outlier_idx].is_anomaly is True
    assert results[outlier_idx].method == "iqr"
    assert results[outlier_idx].score > 1.5
    assert results[outlier_idx].details is not None
    assert "q1" in results[outlier_idx].details
    assert "q3" in results[outlier_idx].details
    assert "iqr" in results[outlier_idx].details

    # Normal baseline items
    assert results[0].is_anomaly is False
    assert results[5].is_anomaly is False


# ──────────────────────────────────────────────────────────────────────────────
# Isolation Forest Multivariate Detection Tests
# ──────────────────────────────────────────────────────────────────────────────


def test_multivariate_isolation_forest() -> None:
    """Verify Isolation Forest detects joint multidimensional price/volume anomalies."""
    detector = TimeSeriesAnomalyDetector(iforest_contamination=0.05)

    # 50 normal observations (price ~100, volume ~1,000,000)
    features: list[list[float]] = [
        [100.0 + math_sin_wave(i) * 2.0, 1_000_000.0 + math_sin_wave(i + 5) * 50_000.0]
        for i in range(50)
    ]

    # Inject extreme volume anomaly (normal price, massive 15x volume spike)
    vol_spike_idx = 12
    features[vol_spike_idx] = [100.5, 15_000_000.0]

    # Inject extreme price crash (normal volume, price collapse)
    price_crash_idx = 38
    features[price_crash_idx] = [20.0, 1_020_000.0]

    results = detector.detect_isolation_forest(features)

    assert len(results) == 50
    assert all(r.method == "isolation_forest" for r in results)

    # The two joint outliers should be detected
    assert results[vol_spike_idx].is_anomaly is True
    assert results[price_crash_idx].is_anomaly is True


def test_custom_isolation_forest_injection() -> None:
    """Verify custom or mocked Isolation Forest model injection."""
    mock_model = MagicMock()
    mock_model.predict.return_value = [-1, 1, 1]
    mock_model.score_samples.return_value = [0.85, 0.20, 0.15]

    detector = TimeSeriesAnomalyDetector(isolation_forest_model=mock_model)
    dummy_features = [[100.0, 5000.0], [101.0, 5100.0], [102.0, 5200.0]]

    results = detector.detect_isolation_forest(dummy_features)

    assert len(results) == 3
    assert results[0].is_anomaly is True
    assert results[0].score == 0.85
    assert results[1].is_anomaly is False
    assert results[2].is_anomaly is False


# ──────────────────────────────────────────────────────────────────────────────
# PriceSchema Integration Tests
# ──────────────────────────────────────────────────────────────────────────────


def test_detect_price_volume_anomalies_with_price_schema() -> None:
    """Verify detector processes collections of PriceSchema domain objects."""
    detector = TimeSeriesAnomalyDetector()

    base_date = datetime(2026, 9, 1, 0, 0, tzinfo=UTC)
    records: list[PriceSchema] = []

    for i in range(40):
        records.append(
            PriceSchema(
                symbol="AAPL",
                date=base_date,
                open=150.0 + math_sin_wave(i),
                high=152.0 + math_sin_wave(i),
                low=149.0 + math_sin_wave(i),
                close=150.5 + math_sin_wave(i),
                volume=10_000_000 + int(math_sin_wave(i) * 100_000),
            )
        )

    # Inject price spike on record 10
    records[10] = PriceSchema(
        symbol="AAPL",
        date=base_date,
        open=150.0,
        high=250.0,
        low=150.0,
        close=245.0,  # +63% price spike
        volume=10_000_000,
    )

    # Inject volume spike on record 25
    records[25] = PriceSchema(
        symbol="AAPL",
        date=base_date,
        open=150.0,
        high=151.0,
        low=149.0,
        close=150.0,
        volume=120_000_000,  # 12x volume spike
    )

    # Test with Z-score
    zscore_results = detector.detect_price_volume_anomalies(records, method="zscore")
    assert len(zscore_results) == 40
    assert zscore_results[10].is_anomaly is True
    assert zscore_results[25].is_anomaly is True
    assert zscore_results[10].details is not None
    assert zscore_results[10].details["price_anomaly"] is True
    assert zscore_results[25].details is not None
    assert zscore_results[25].details["volume_anomaly"] is True

    # Test with IQR
    iqr_results = detector.detect_price_volume_anomalies(records, method="iqr")
    assert len(iqr_results) == 40
    assert iqr_results[10].is_anomaly is True
    assert iqr_results[25].is_anomaly is True

    # Test with Isolation Forest
    iforest_results = detector.detect_price_volume_anomalies(records, method="isolation_forest")
    assert len(iforest_results) == 40
    assert iforest_results[10].is_anomaly is True or iforest_results[25].is_anomaly is True


def test_detect_price_volume_anomalies_with_dict_records() -> None:
    """Verify detector processes dictionary representations."""
    detector = TimeSeriesAnomalyDetector()
    records = [{"close": 100.0 + math_sin_wave(i), "volume": 50000 + i} for i in range(30)]
    records[5] = {"close": 200.0, "volume": 50000}

    results = detector.detect_price_volume_anomalies(records, method="zscore")
    assert len(results) == 30
    assert results[5].is_anomaly is True


# ──────────────────────────────────────────────────────────────────────────────
# Edge Cases & Configuration Tests
# ──────────────────────────────────────────────────────────────────────────────


def test_edge_case_zero_variance() -> None:
    """Verify constant flat series handles zero standard deviation gracefully."""
    detector = TimeSeriesAnomalyDetector()
    flat_series = [150.0] * 30

    z_results = detector.detect_zscore(flat_series)
    assert len(z_results) == 30
    assert all(r.is_anomaly is False for r in z_results)
    assert all(r.score == 0.0 for r in z_results)

    iqr_results = detector.detect_iqr(flat_series)
    assert len(iqr_results) == 30
    assert all(r.is_anomaly is False for r in iqr_results)


def test_edge_case_insufficient_data() -> None:
    """Verify empty or small datasets return non-anomalies with diagnostic details."""
    detector = TimeSeriesAnomalyDetector()

    assert detector.detect_zscore([]) == []
    assert detector.detect_iqr([]) == []
    assert detector.detect_isolation_forest([]) == []
    assert detector.detect_price_volume_anomalies([]) == []

    # Single-element series
    single_z = detector.detect_zscore([100.0])
    assert len(single_z) == 1
    assert single_z[0].is_anomaly is False
    assert single_z[0].details is not None
    assert single_z[0].details.get("reason") == "insufficient_data"

    # Small series (< 4 items for IQR / Isolation Forest)
    small_iqr = detector.detect_iqr([10.0, 20.0, 30.0])
    assert len(small_iqr) == 3
    assert all(r.is_anomaly is False for r in small_iqr)

    small_iforest = detector.detect_isolation_forest([[10.0, 20.0], [30.0, 40.0]])
    assert len(small_iforest) == 2
    assert all(r.is_anomaly is False for r in small_iforest)


def test_configurable_thresholds_override() -> None:
    """Verify defaults and runtime parameter overrides."""
    detector = TimeSeriesAnomalyDetector(
        zscore_threshold=DEFAULT_ZSCORE_THRESHOLD,
        iqr_multiplier=DEFAULT_IQR_MULTIPLIER,
        iforest_contamination=DEFAULT_IFOREST_CONTAMINATION,
    )
    assert detector.zscore_threshold == 3.0
    assert detector.iqr_multiplier == 1.5
    assert detector.iforest_contamination == 0.05

    # Test runtime threshold override in method call
    data = generate_synthetic_series(n=30, base=100.0, spread=2.0)
    data[10] = 106.0  # moderate spike (~2.5 stdevs)

    strict_results = detector.detect_zscore(data, threshold=2.0)
    lenient_results = detector.detect_zscore(data, threshold=4.0)

    assert strict_results[10].is_anomaly is True
    assert lenient_results[10].is_anomaly is False


def test_schema_serialization() -> None:
    """Verify AnomalyResult schema validation and serialization."""
    res = AnomalyResult(
        is_anomaly=True,
        score=4.25,
        method="zscore",
        details={"symbol": "MSFT", "metric": "volume"},
    )
    data = res.model_dump()
    assert data["is_anomaly"] is True
    assert data["score"] == 4.25
    assert data["method"] == "zscore"
    assert data["details"]["symbol"] == "MSFT"  # type: ignore[index]
