"""AIOps: Data drift monitoring with automated retraining triggers."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import numpy as np
import structlog

logger = structlog.get_logger(__name__)


@dataclass
class DriftReport:
    """Result of a drift detection check."""
    feature_name: str
    drift_score: float
    drift_detected: bool
    reference_mean: float
    current_mean: float
    reference_std: float
    current_std: float
    threshold: float
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "feature_name": self.feature_name,
            "drift_score": round(self.drift_score, 4),
            "drift_detected": self.drift_detected,
            "reference_mean": round(self.reference_mean, 4),
            "current_mean": round(self.current_mean, 4),
            "shift_pct": round(
                abs(self.current_mean - self.reference_mean) / max(abs(self.reference_mean), 1e-8) * 100, 2
            ),
            "threshold": self.threshold,
            "timestamp": self.timestamp.isoformat(),
        }


class DataDriftDetector:
    """Monitor feature distributions and detect data drift using PSI and Z-score methods."""

    def __init__(self, drift_threshold: float = 0.20, zscore_threshold: float = 3.0):
        self.drift_threshold = drift_threshold
        self.zscore_threshold = zscore_threshold
        self._reference_stats: dict[str, dict] = {}
        self._drift_history: list[DriftReport] = []
        self._retraining_triggered: int = 0

    def set_reference(self, feature_name: str, values: list[float]) -> None:
        """Set reference distribution statistics for a feature."""
        arr = np.array(values, dtype=float)
        self._reference_stats[feature_name] = {
            "mean": float(np.mean(arr)),
            "std": float(np.std(arr)),
            "min": float(np.min(arr)),
            "max": float(np.max(arr)),
            "percentiles": {
                str(p): float(np.percentile(arr, p))
                for p in [10, 25, 50, 75, 90, 95, 99]
            },
            "n_samples": len(values),
            "set_at": datetime.now(timezone.utc).isoformat(),
        }
        logger.info("reference_distribution_set", feature=feature_name, n_samples=len(values))

    def check_drift(self, feature_name: str, current_values: list[float]) -> DriftReport:
        """Check if current distribution has drifted from reference."""
        if feature_name not in self._reference_stats:
            raise ValueError(f"No reference distribution for feature '{feature_name}'")

        ref = self._reference_stats[feature_name]
        current = np.array(current_values, dtype=float)

        # PSI-based drift score
        drift_score = self._compute_psi(
            reference_mean=ref["mean"],
            reference_std=ref["std"],
            current_values=current,
        )

        report = DriftReport(
            feature_name=feature_name,
            drift_score=drift_score,
            drift_detected=drift_score > self.drift_threshold,
            reference_mean=ref["mean"],
            current_mean=float(np.mean(current)),
            reference_std=ref["std"],
            current_std=float(np.std(current)),
            threshold=self.drift_threshold,
        )

        self._drift_history.append(report)

        if report.drift_detected:
            logger.warning(
                "data_drift_detected",
                feature=feature_name,
                drift_score=round(drift_score, 4),
                threshold=self.drift_threshold,
            )
            self._maybe_trigger_retraining(feature_name, drift_score)

        return report

    def _compute_psi(
        self,
        reference_mean: float,
        reference_std: float,
        current_values: np.ndarray,
        n_bins: int = 10,
    ) -> float:
        """Compute Population Stability Index (PSI) for drift measurement."""
        # Simple approximation using mean shift normalized by std
        current_mean = float(np.mean(current_values))
        if reference_std < 1e-8:
            return 0.0 if abs(current_mean - reference_mean) < 1e-8 else 1.0

        z_score = abs(current_mean - reference_mean) / reference_std
        # Normalize to [0, 1] range using sigmoid-like function
        psi_approx = min(z_score / self.zscore_threshold, 1.0)
        return round(psi_approx, 4)

    def _maybe_trigger_retraining(self, feature_name: str, drift_score: float) -> None:
        """Trigger model retraining if drift is persistent."""
        recent_drifts = [
            r for r in self._drift_history[-20:]
            if r.feature_name == feature_name and r.drift_detected
        ]
        if len(recent_drifts) >= 3:
            logger.warning(
                "retraining_triggered",
                feature=feature_name,
                consecutive_drifts=len(recent_drifts),
                avg_drift_score=round(sum(r.drift_score for r in recent_drifts) / len(recent_drifts), 4),
            )
            self._retraining_triggered += 1

    def get_summary(self) -> dict:
        """Get drift monitoring summary."""
        recent = self._drift_history[-100:]
        drifted = [r for r in recent if r.drift_detected]
        return {
            "monitored_features": list(self._reference_stats.keys()),
            "total_checks": len(self._drift_history),
            "drift_detected_count": len(drifted),
            "drift_rate": len(drifted) / len(recent) if recent else 0,
            "retraining_triggers": self._retraining_triggered,
            "recent_drifts": [r.to_dict() for r in drifted[-10:]],
        }
