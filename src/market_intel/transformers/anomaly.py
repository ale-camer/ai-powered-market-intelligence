"""Statistical and machine learning anomaly detection on financial time-series data."""

import math
import random
from collections.abc import Sequence
from typing import Any, cast

from market_intel.core.config import get_settings
from market_intel.core.logger import get_logger
from market_intel.core.schemas import AnomalyResult, PriceSchema

logger = get_logger(__name__)

DEFAULT_ZSCORE_THRESHOLD = 3.0
DEFAULT_IQR_MULTIPLIER = 1.5
DEFAULT_IFOREST_CONTAMINATION = 0.05
EULER_MASCHERONI = 0.5772156649


# ──────────────────────────────────────────────────────────────────────────────
# Statistical Utilities (Pure Python)
# ──────────────────────────────────────────────────────────────────────────────


def compute_mean(values: Sequence[float]) -> float:
    """Calculate arithmetic mean of a numeric sequence."""
    if not values:
        return 0.0
    return float(sum(values) / len(values))


def compute_stdev(values: Sequence[float], mean_val: float | None = None) -> float:
    """Calculate sample standard deviation of a numeric sequence."""
    n = len(values)
    if n < 2:
        return 0.0
    m = mean_val if mean_val is not None else compute_mean(values)
    variance = sum((x - m) ** 2 for x in values) / (n - 1)
    return float(math.sqrt(max(0.0, variance)))


def compute_percentile(sorted_values: Sequence[float], p: float) -> float:
    """Calculate percentile p in [0.0, 1.0] using linear interpolation."""
    if not sorted_values:
        return 0.0
    n = len(sorted_values)
    if n == 1:
        return float(sorted_values[0])
    idx = p * (n - 1)
    low = int(idx)
    high = min(low + 1, n - 1)
    weight = idx - low
    return float(sorted_values[low] * (1.0 - weight) + sorted_values[high] * weight)


def _c_factor(n: int) -> float:
    """Average path length of unsuccessful search in a Binary Search Tree (BST)."""
    if n <= 1:
        return 1.0
    if n == 2:
        return 1.0
    return float(2.0 * (math.log(n - 1) + EULER_MASCHERONI) - (2.0 * (n - 1) / n))


# ──────────────────────────────────────────────────────────────────────────────
# Pure-Python Isolation Forest Fallback
# ──────────────────────────────────────────────────────────────────────────────


class _IsolationTreeNode:
    """Node in an isolation tree."""

    def __init__(
        self,
        feature_idx: int = -1,
        split_val: float = 0.0,
        left: "_IsolationTreeNode | None" = None,
        right: "_IsolationTreeNode | None" = None,
        size: int = 0,
    ) -> None:
        self.feature_idx = feature_idx
        self.split_val = split_val
        self.left = left
        self.right = right
        self.size = size

    @property
    def is_leaf(self) -> bool:
        return self.left is None and self.right is None


class PurePythonIsolationForest:
    """Lightweight, deterministic pure-Python Isolation Forest implementation."""

    def __init__(
        self,
        n_trees: int = 50,
        max_samples: int = 256,
        contamination: float = 0.05,
        random_state: int = 42,
    ) -> None:
        self.n_trees = n_trees
        self.max_samples = max_samples
        self.contamination = contamination
        self.random_state = random_state
        self.trees: list[_IsolationTreeNode] = []
        self._n_samples_trained: int = 0

    def fit(self, x: Sequence[Sequence[float]]) -> "PurePythonIsolationForest":
        """Build the isolation trees ensemble."""
        n_samples = len(x)
        if n_samples == 0:
            return self

        self._n_samples_trained = n_samples
        rng = random.Random(self.random_state)
        sample_size = min(self.max_samples, n_samples)
        max_height = math.ceil(math.log2(max(2, sample_size)))

        self.trees = []
        for _ in range(self.n_trees):
            indices = (
                rng.sample(range(n_samples), sample_size)
                if sample_size < n_samples
                else list(range(n_samples))
            )
            sub_x = [x[i] for i in indices]
            tree = self._build_tree(sub_x, current_height=0, max_height=max_height, rng=rng)
            self.trees.append(tree)

        return self

    def _build_tree(
        self,
        x: list[Sequence[float]],
        current_height: int,
        max_height: int,
        rng: random.Random,
    ) -> _IsolationTreeNode:
        """Recursively partition feature space."""
        n = len(x)
        if current_height >= max_height or n <= 1:
            return _IsolationTreeNode(size=n)

        n_features = len(x[0])
        # Find features with varying values
        valid_features: list[tuple[int, float, float]] = []
        for feat in range(n_features):
            vals = [row[feat] for row in x]
            min_v, max_v = min(vals), max(vals)
            if max_v > min_v:
                valid_features.append((feat, min_v, max_v))

        if not valid_features:
            return _IsolationTreeNode(size=n)

        chosen_feat, min_v, max_v = rng.choice(valid_features)
        split_val = rng.uniform(min_v, max_v)

        left_x = [row for row in x if row[chosen_feat] < split_val]
        right_x = [row for row in x if row[chosen_feat] >= split_val]

        left_node = self._build_tree(left_x, current_height + 1, max_height, rng)
        right_node = self._build_tree(right_x, current_height + 1, max_height, rng)

        return _IsolationTreeNode(
            feature_idx=chosen_feat,
            split_val=split_val,
            left=left_node,
            right=right_node,
            size=n,
        )

    def _path_length(self, point: Sequence[float], node: _IsolationTreeNode, depth: int) -> float:
        """Compute path length for a single observation."""
        if node.is_leaf:
            return float(depth + _c_factor(node.size))
        if point[node.feature_idx] < node.split_val:
            if node.left is not None:
                return self._path_length(point, node.left, depth + 1)
        else:
            if node.right is not None:
                return self._path_length(point, node.right, depth + 1)
        return float(depth + 1)

    def score_samples(self, x: Sequence[Sequence[float]]) -> list[float]:
        """Compute anomaly score for each observation in [0, 1]."""
        if not self.trees or not x:
            return [0.0] * len(x)

        c = _c_factor(self._n_samples_trained)
        scores: list[float] = []
        for point in x:
            avg_path = sum(self._path_length(point, t, 0) for t in self.trees) / len(self.trees)
            score = float(2.0 ** (-avg_path / c)) if c > 0 else 0.5
            scores.append(round(score, 4))
        return scores

    def predict(self, x: Sequence[Sequence[float]]) -> list[int]:
        """Predict whether observations are outliers (-1) or inliers (1)."""
        scores = self.score_samples(x)
        if not scores:
            return []

        # Mark top contamination fraction as outliers
        k = max(1, int(math.ceil(len(scores) * self.contamination)))
        sorted_scores = sorted(scores, reverse=True)
        threshold = sorted_scores[min(k - 1, len(sorted_scores) - 1)]

        return [-1 if s >= threshold and s > 0.5 else 1 for s in scores]


# ──────────────────────────────────────────────────────────────────────────────
# Main Pipeline Detector
# ──────────────────────────────────────────────────────────────────────────────


class TimeSeriesAnomalyDetector:
    """Production financial time-series anomaly detection pipeline.

    Provides univariate spike detection (Z-score, IQR) and multivariate
    anomaly detection (Isolation Forest) across prices, volumes, and returns.
    """

    def __init__(
        self,
        zscore_threshold: float | None = None,
        iqr_multiplier: float | None = None,
        iforest_contamination: float | None = None,
        isolation_forest_model: object | None = None,
    ) -> None:
        """Initialize the anomaly detection engine.

        Args:
            zscore_threshold: Critical Z-score threshold (default from settings or 3.0).
            iqr_multiplier: IQR fence multiplier (default from settings or 1.5).
            iforest_contamination: Expected proportion of outliers in Isolation Forest.
            isolation_forest_model: Optional pre-configured Isolation Forest estimator.
        """
        settings = get_settings()

        self.zscore_threshold = (
            zscore_threshold
            if zscore_threshold is not None
            else settings.anomaly_zscore_threshold
            if hasattr(settings, "anomaly_zscore_threshold")
            else DEFAULT_ZSCORE_THRESHOLD
        )
        self.iqr_multiplier = (
            iqr_multiplier
            if iqr_multiplier is not None
            else settings.anomaly_iqr_multiplier
            if hasattr(settings, "anomaly_iqr_multiplier")
            else DEFAULT_IQR_MULTIPLIER
        )
        self.iforest_contamination = (
            iforest_contamination
            if iforest_contamination is not None
            else settings.anomaly_iforest_contamination
            if hasattr(settings, "anomaly_iforest_contamination")
            else DEFAULT_IFOREST_CONTAMINATION
        )

        self._custom_model = isolation_forest_model

    def detect_zscore(
        self,
        values: Sequence[float],
        threshold: float | None = None,
    ) -> list[AnomalyResult]:
        """Detect anomalies in a univariate numeric sequence using Z-score.

        Args:
            values: Sequence of numeric values (e.g., closing prices or volumes).
            threshold: Standard deviations threshold (default: self.zscore_threshold).

        Returns:
            List of AnomalyResult items corresponding to input values.
        """
        if not values:
            return []

        effective_threshold = threshold if threshold is not None else self.zscore_threshold
        n = len(values)

        if n < 2:
            return [
                AnomalyResult(
                    is_anomaly=False,
                    score=0.0,
                    method="zscore",
                    details={"reason": "insufficient_data", "count": n},
                )
                for _ in values
            ]

        mean_val = compute_mean(values)
        stdev_val = compute_stdev(values, mean_val=mean_val)

        # Constant sequence / zero variance
        if stdev_val < 1e-9:
            return [
                AnomalyResult(
                    is_anomaly=False,
                    score=0.0,
                    method="zscore",
                    details={
                        "value": float(x),
                        "mean": round(mean_val, 4),
                        "stdev": 0.0,
                        "z_score": 0.0,
                        "threshold": effective_threshold,
                    },
                )
                for x in values
            ]

        results: list[AnomalyResult] = []
        for x in values:
            z = (float(x) - mean_val) / stdev_val
            abs_z = abs(z)
            is_anomaly = bool(abs_z > effective_threshold)

            results.append(
                AnomalyResult(
                    is_anomaly=is_anomaly,
                    score=round(abs_z, 4),
                    method="zscore",
                    details={
                        "value": float(x),
                        "mean": round(mean_val, 4),
                        "stdev": round(stdev_val, 4),
                        "z_score": round(z, 4),
                        "threshold": effective_threshold,
                    },
                )
            )

        return results

    def detect_iqr(
        self,
        values: Sequence[float],
        multiplier: float | None = None,
    ) -> list[AnomalyResult]:
        """Detect anomalies in a univariate sequence using Interquartile Range (IQR).

        Fences:
            Lower: Q1 - multiplier * IQR
            Upper: Q3 + multiplier * IQR

        Args:
            values: Sequence of numeric observations.
            multiplier: IQR multiplier (default: self.iqr_multiplier).

        Returns:
            List of AnomalyResult items corresponding to input values.
        """
        if not values:
            return []

        effective_multiplier = multiplier if multiplier is not None else self.iqr_multiplier
        n = len(values)

        if n < 4:
            return [
                AnomalyResult(
                    is_anomaly=False,
                    score=0.0,
                    method="iqr",
                    details={"reason": "insufficient_data", "count": n},
                )
                for _ in values
            ]

        sorted_vals = sorted(float(x) for x in values)
        q1 = compute_percentile(sorted_vals, 0.25)
        q3 = compute_percentile(sorted_vals, 0.75)
        iqr = max(0.0, q3 - q1)

        lower_bound = q1 - (effective_multiplier * iqr)
        upper_bound = q3 + (effective_multiplier * iqr)

        results: list[AnomalyResult] = []
        for x in values:
            fx = float(x)
            is_anomaly = bool(fx < lower_bound or fx > upper_bound)

            # Score expresses relative distance beyond the fence normalized by IQR
            if iqr > 1e-9:
                if fx > upper_bound:
                    dist = (fx - upper_bound) / iqr
                elif fx < lower_bound:
                    dist = (lower_bound - fx) / iqr
                else:
                    dist = 0.0
                score = round(dist, 4)
            else:
                score = 0.0

            results.append(
                AnomalyResult(
                    is_anomaly=is_anomaly,
                    score=score,
                    method="iqr",
                    details={
                        "value": fx,
                        "q1": round(q1, 4),
                        "q3": round(q3, 4),
                        "iqr": round(iqr, 4),
                        "lower_bound": round(lower_bound, 4),
                        "upper_bound": round(upper_bound, 4),
                        "multiplier": effective_multiplier,
                    },
                )
            )

        return results

    def detect_isolation_forest(
        self,
        features: Sequence[Sequence[float]],
        contamination: float | None = None,
    ) -> list[AnomalyResult]:
        """Detect multivariate anomalies using Isolation Forest.

        Args:
            features: 2D array-like sequence of numeric feature vectors.
            contamination: Fraction of expected outliers in dataset.

        Returns:
            List of AnomalyResult items corresponding to input feature rows.
        """
        if not features:
            return []

        # Use injected mock/custom model if provided
        if self._custom_model is not None:
            model_any = cast(Any, self._custom_model)
            preds = model_any.predict(features)
            scores = (
                model_any.score_samples(features)
                if hasattr(model_any, "score_samples")
                else [0.8 if p == -1 else 0.2 for p in preds]
            )
            return [
                AnomalyResult(
                    is_anomaly=bool(p == -1),
                    score=round(float(s), 4),
                    method="isolation_forest",
                    details={"features": [float(v) for v in row]},
                )
                for row, p, s in zip(features, preds, scores, strict=True)
            ]

        effective_contamination = (
            contamination if contamination is not None else self.iforest_contamination
        )
        n = len(features)

        if n < 4:
            return [
                AnomalyResult(
                    is_anomaly=False,
                    score=0.0,
                    method="isolation_forest",
                    details={"reason": "insufficient_data", "count": n},
                )
                for _ in features
            ]

        # Try sklearn if available
        try:
            from sklearn.ensemble import IsolationForest

            model = IsolationForest(
                contamination=effective_contamination,
                random_state=42,
            )
            x_matrix = [[float(v) for v in row] for row in features]
            preds = model.fit_predict(x_matrix)
            dec_scores = model.decision_function(x_matrix)

            results: list[AnomalyResult] = []
            for row, p, dec in zip(features, preds, dec_scores, strict=True):
                # Lower decision score means more anomalous; invert for intuitive anomaly score
                raw_score = max(0.0, -float(dec))
                results.append(
                    AnomalyResult(
                        is_anomaly=bool(p == -1),
                        score=round(raw_score, 4),
                        method="isolation_forest",
                        details={
                            "decision_score": round(float(dec), 4),
                            "features": [float(v) for v in row],
                        },
                    )
                )
            return results
        except ImportError:
            # Fallback to pure-Python implementation
            pure_model = PurePythonIsolationForest(
                contamination=effective_contamination,
                random_state=42,
            )
            x_matrix = [[float(v) for v in row] for row in features]
            pure_model.fit(x_matrix)
            scores = pure_model.score_samples(x_matrix)
            preds = pure_model.predict(x_matrix)

            return [
                AnomalyResult(
                    is_anomaly=bool(p == -1),
                    score=round(s, 4),
                    method="isolation_forest",
                    details={
                        "score": round(s, 4),
                        "features": [float(v) for v in row],
                    },
                )
                for row, p, s in zip(features, preds, scores, strict=True)
            ]

    def detect_price_volume_anomalies(
        self,
        records: Sequence[PriceSchema | dict[str, object]],
        method: str = "zscore",
    ) -> list[AnomalyResult]:
        """Detect anomalies across structured price and volume records.

        Args:
            records: Collection of PriceSchema models or dictionary records with
                'close' and 'volume' keys.
            method: Anomaly detection method ('zscore', 'iqr', or 'isolation_forest').

        Returns:
            List of AnomalyResult items corresponding to input records.
        """
        if not records:
            return []

        prices: list[float] = []
        volumes: list[float] = []
        feature_matrix: list[list[float]] = []

        for item in records:
            if isinstance(item, PriceSchema):
                c = float(item.close)
                v = float(item.volume)
            else:
                c = float(item.get("close", 0.0))  # type: ignore[arg-type]
                v = float(item.get("volume", 0.0))  # type: ignore[arg-type]
            prices.append(c)
            volumes.append(v)
            feature_matrix.append([c, v])

        if method == "isolation_forest":
            return self.detect_isolation_forest(feature_matrix)

        if method == "iqr":
            price_anomalies = self.detect_iqr(prices)
            vol_anomalies = self.detect_iqr(volumes)
        else:
            price_anomalies = self.detect_zscore(prices)
            vol_anomalies = self.detect_zscore(volumes)

        results: list[AnomalyResult] = []
        for p_res, v_res, c_val, v_val in zip(
            price_anomalies, vol_anomalies, prices, volumes, strict=True
        ):
            is_anomaly = bool(p_res.is_anomaly or v_res.is_anomaly)
            max_score = max(p_res.score, v_res.score)
            results.append(
                AnomalyResult(
                    is_anomaly=is_anomaly,
                    score=max_score,
                    method=method,
                    details={
                        "price": c_val,
                        "volume": v_val,
                        "price_anomaly": p_res.is_anomaly,
                        "price_score": p_res.score,
                        "volume_anomaly": v_res.is_anomaly,
                        "volume_score": v_res.score,
                    },
                )
            )

        return results
