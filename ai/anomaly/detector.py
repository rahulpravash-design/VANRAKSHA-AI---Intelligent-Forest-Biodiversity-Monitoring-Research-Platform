"""Biodiversity anomaly detection over detection-count time series.

The detector aggregates daily counts into consecutive windows, fits a robust
baseline over the preceding history, and combines two independent views:

* **Robust z-score** — how far the window sits from the baseline median in MAD
  units.  Directly interpretable, and the primary signal.
* **Isolation Forest** — how isolated the window looks in a small feature space
  (level, change from the previous window, ratio to the rolling mean, share of
  active days).  Catches shapes a single z-score misses, such as a normal total
  achieved on one day instead of seven.

A window is flagged when either view crosses its threshold.  The result is
always a *question for a human*: :func:`candidate_causes` ranks the plausible
explanations from the evidence, and nothing in this module ever concludes that
poaching or ecological damage has occurred — that finding requires field
verification and is recorded by an officer on the alert itself.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

import numpy as np

from ai.anomaly.isolation_forest import IsolationForest
from ai.anomaly.robust_z import RobustBaseline, fit_robust_baseline
from ai.config import AIConfig, get_config

DIRECTION_DROP = "drop"
DIRECTION_SURGE = "surge"
DIRECTION_STABLE = "stable"


@dataclass(frozen=True)
class AnomalyFinding:
    """One scored window for one metric."""

    metric: str
    window_start: date
    window_end: date
    observed: float
    baseline: float
    spread: float
    robust_z: float
    isolation_score: float
    isolation_threshold: float
    score: float
    is_anomaly: bool
    direction: str
    method: str
    active_days: int
    baseline_windows: int
    details: dict = field(default_factory=dict)

    @property
    def relative_change(self) -> float | None:
        if self.baseline <= 0:
            return None
        return (self.observed - self.baseline) / self.baseline

    def as_dict(self) -> dict:
        return {
            "metric": self.metric,
            "window_start": self.window_start.isoformat(),
            "window_end": self.window_end.isoformat(),
            "observed_value": round(self.observed, 4),
            "baseline_value": round(self.baseline, 4),
            "baseline_spread": round(self.spread, 4),
            "robust_z": round(self.robust_z, 4),
            "isolation_score": round(self.isolation_score, 4),
            "isolation_threshold": round(self.isolation_threshold, 4),
            "score": round(self.score, 4),
            "is_anomaly": self.is_anomaly,
            "direction": self.direction,
            "method": self.method,
            "active_days": self.active_days,
            "baseline_windows": self.baseline_windows,
            "relative_change": (
                round(self.relative_change, 4) if self.relative_change is not None else None
            ),
            "details": self.details,
        }


def _bucket(points: dict[date, float], start: date, days: int) -> tuple[float, int]:
    """Sum a window and count how many of its days carry any data."""
    total = 0.0
    active = 0
    for offset in range(days):
        value = points.get(start + timedelta(days=offset))
        if value is None:
            continue
        total += float(value)
        if value > 0:
            active += 1
    return total, active


def _window_features(
    values: list[float], active_days: list[int], window_days: int
) -> np.ndarray:
    """Feature matrix for the Isolation Forest, one row per window."""
    array = np.asarray(values, dtype=np.float64)
    deltas = np.diff(array, prepend=array[0] if array.size else 0.0)
    rolling = np.array(
        [array[max(0, i - 3) : i + 1].mean() if i >= 0 else 0.0 for i in range(array.size)]
    )
    ratio = np.where(rolling > 1e-9, array / np.maximum(rolling, 1e-9), 1.0)
    activity = np.asarray(active_days, dtype=np.float64) / max(window_days, 1)
    # Concentration: how unevenly the window's total was accumulated.
    concentration = np.where(
        (array > 0) & (activity > 0), 1.0 - activity, 0.0
    )
    return np.column_stack([array, deltas, ratio, activity, concentration])


class BiodiversityAnomalyDetector:
    """Score consecutive windows of a detection-count series."""

    def __init__(self, config: AIConfig | None = None) -> None:
        self._config = config or get_config()

    def detect(
        self,
        metric: str,
        daily_counts: dict[date, float],
        *,
        window_days: int | None = None,
        baseline_days: int | None = None,
        z_threshold: float | None = None,
        contamination: float | None = None,
        evaluate_last_n: int | None = None,
        end_date: date | None = None,
    ) -> list[AnomalyFinding]:
        """Return a finding per evaluated window, most recent last.

        ``daily_counts`` maps a calendar day to that day's count; missing days
        are treated as *no data*, which the ``active_days`` feature and the
        data-gap cause both make visible instead of silently reading as zero.

        ``end_date`` is the last day to evaluate, and normally wants to be
        *today* rather than the last day that happens to carry data. Windowing
        only up to the final populated day would make the single most important
        signal invisible: if every camera in a zone stopped a fortnight ago, the
        series simply ends, and a detector anchored to its own last data point
        would never notice.
        """
        config = self._config
        window_days = int(window_days or config.window_days)
        baseline_days = int(baseline_days or config.baseline_days)
        z_threshold = float(z_threshold if z_threshold is not None else config.z_threshold)
        contamination = float(
            contamination if contamination is not None else config.contamination
        )
        if not daily_counts:
            return []

        first_day = min(daily_counts)
        last_day = end_date or max(daily_counts)
        if last_day < first_day:  # pragma: no cover - caller passed a stale date
            return []
        total_days = (last_day - first_day).days + 1
        window_count = total_days // window_days
        if window_count < 3:
            return []

        # Build consecutive windows, oldest first, ending on the latest full one.
        starts = [
            last_day - timedelta(days=window_days * (i + 1) - 1)
            for i in range(window_count)
        ][::-1]
        values: list[float] = []
        actives: list[int] = []
        for start in starts:
            total, active = _bucket(daily_counts, start, window_days)
            values.append(total)
            actives.append(active)

        baseline_window_count = max(3, baseline_days // window_days)
        features = _window_features(values, actives, window_days)

        if evaluate_last_n is None:
            evaluate_last_n = len(values)
        first_evaluated = max(1, len(values) - int(evaluate_last_n))

        findings: list[AnomalyFinding] = []
        for index in range(first_evaluated, len(values)):
            history_start = max(0, index - baseline_window_count)
            history = np.asarray(values[history_start:index], dtype=np.float64)
            if history.size < 2:
                continue
            baseline: RobustBaseline = fit_robust_baseline(history)
            observed = values[index]
            robust_z = (
                (observed - baseline.median) / baseline.sigma if baseline.sigma > 1e-9 else 0.0
            )

            isolation_score, isolation_threshold = self._isolation(
                features[history_start:index], features[index], contamination
            )

            z_flag = abs(robust_z) >= z_threshold and not baseline.is_weak
            # A zero threshold means the forest had no discriminating power, so
            # its score carries no information and must not flag anything.
            isolation_flag = isolation_threshold > 0 and isolation_score >= isolation_threshold
            if z_flag and isolation_flag:
                method = "ENSEMBLE"
            elif z_flag:
                method = "ROBUST_Z"
            elif isolation_flag:
                method = "ISOLATION_FOREST"
            else:
                method = "ENSEMBLE"

            # Normalised severity: 0 at the threshold, → 1 far beyond it.
            z_component = abs(robust_z) / (abs(robust_z) + z_threshold) if z_threshold else 0.0
            score = float(np.clip(0.6 * z_component + 0.4 * isolation_score, 0.0, 1.0))

            if robust_z <= -z_threshold:
                direction = DIRECTION_DROP
            elif robust_z >= z_threshold:
                direction = DIRECTION_SURGE
            else:
                direction = DIRECTION_STABLE

            findings.append(
                AnomalyFinding(
                    metric=metric,
                    window_start=starts[index],
                    window_end=starts[index] + timedelta(days=window_days - 1),
                    observed=float(observed),
                    baseline=float(baseline.median),
                    spread=float(baseline.sigma),
                    robust_z=float(robust_z),
                    isolation_score=float(isolation_score),
                    isolation_threshold=float(isolation_threshold),
                    score=score,
                    is_anomaly=bool(z_flag or isolation_flag),
                    direction=direction,
                    method=method,
                    active_days=actives[index],
                    baseline_windows=int(history.size),
                    details={
                        "window_days": window_days,
                        "baseline_is_weak": baseline.is_weak,
                        "baseline_mad": round(baseline.mad, 4),
                        "z_threshold": z_threshold,
                        "contamination": contamination,
                        "flagged_by": {
                            "robust_z": bool(z_flag),
                            "isolation_forest": bool(isolation_flag),
                        },
                    },
                )
            )
        return findings

    def _isolation(
        self, history: np.ndarray, point: np.ndarray, contamination: float
    ) -> tuple[float, float]:
        """Isolation-forest score for one window against its own history."""
        if history.shape[0] < 6:
            # Too little history for a meaningful forest — defer to the z-score.
            return 0.0, 0.0
        forest = IsolationForest(
            n_trees=self._config.isolation_trees,
            subsample_size=min(self._config.isolation_sample_size, history.shape[0]),
            random_state=self._config.random_seed,
        ).fit(history)
        if forest.score_spread < 1e-6:
            # Every training window looked identical: the forest cannot tell
            # anything apart, so defer entirely to the robust z-score.
            return 0.0, 0.0
        score = float(forest.score_samples(point[None, :])[0])
        return score, forest.threshold_for(contamination)


def candidate_causes(
    finding: AnomalyFinding,
    *,
    device_gap: bool = False,
    correlated_metrics: int = 0,
    total_metrics: int = 1,
    config: AIConfig | None = None,
) -> list[str]:
    """Rank plausible explanations for a flagged window.

    Ordering is evidence-driven, not a fixed list:

    * incomplete days in the window promote a collection/connectivity gap;
    * a device that stopped reporting promotes sensor malfunction;
    * every metric moving together points at the recording setup rather than at
      the wildlife, whereas one metric moving alone points at that taxon.

    The returned strings are hypotheses for a field officer to check.
    """
    config = config or get_config()
    window_days = int(finding.details.get("window_days", config.window_days))
    causes: list[str] = []

    incomplete = finding.active_days < max(1, window_days // 2)
    all_metrics_moved = total_metrics > 1 and correlated_metrics >= max(2, total_metrics - 1)

    if device_gap:
        causes.append("Sensor or camera malfunction")
    if incomplete or finding.observed == 0:
        causes.append("Gap in data collection or connectivity")
    if all_metrics_moved:
        causes.append("Sensor or camera malfunction")
        causes.append("Gap in data collection or connectivity")

    if finding.direction == DIRECTION_DROP:
        causes.extend(
            [
                "Seasonal migration or phenology",
                "Weather conditions during the window",
                "Habitat change (fire, felling, flooding)",
                "Human activity in the zone",
            ]
        )
    elif finding.direction == DIRECTION_SURGE:
        causes.extend(
            [
                "Seasonal migration or phenology",
                "Increased survey effort in the window",
                "Weather conditions during the window",
                "Habitat change (fire, felling, flooding)",
            ]
        )
    else:
        causes.extend(
            [
                "Change in the temporal distribution of detections",
                "Increased survey effort in the window",
                "Weather conditions during the window",
            ]
        )

    # De-duplicate while preserving the evidence-driven order.
    ordered: list[str] = []
    for cause in causes:
        if cause not in ordered:
            ordered.append(cause)
    return ordered
