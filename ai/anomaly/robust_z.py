"""Median/MAD baseline — the statistical starting point.

A mean-and-standard-deviation baseline is a poor fit for detection counts: one
festival week with no fieldwork, or one camera-trap burst, inflates the standard
deviation enough to hide the next real change.  The median and the median
absolute deviation are unaffected by up to half the window being atypical, which
is why they are the default here.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

#: Scale factor making the MAD a consistent estimator of sigma for normal data.
MAD_TO_SIGMA = 1.4826


@dataclass(frozen=True)
class RobustBaseline:
    median: float
    mad: float
    sigma: float
    sample_count: int
    #: True when the baseline has too few points to be trusted on its own.
    is_weak: bool

    @property
    def usable(self) -> bool:
        return self.sample_count >= 3 and self.sigma > 0


def fit_robust_baseline(values: np.ndarray, *, min_samples: int = 5) -> RobustBaseline:
    values = np.asarray([v for v in np.asarray(values, dtype=np.float64) if np.isfinite(v)])
    if values.size == 0:
        return RobustBaseline(median=0.0, mad=0.0, sigma=0.0, sample_count=0, is_weak=True)
    median = float(np.median(values))
    mad = float(np.median(np.abs(values - median)))
    sigma = mad * MAD_TO_SIGMA
    if sigma <= 1e-9:
        # A degenerate MAD means more than half the baseline is identical, so the
        # distribution has an atom at the median. The scale must still come from
        # somewhere — but *not* from the standard deviation: a series of twenty
        # 20s and one 500 has sigma ≈ 105, which is precisely the outlier
        # sensitivity the median/MAD baseline exists to avoid. These are
        # non-negative count-like series, so Poisson dispersion is the principled
        # default, and an all-zero baseline uses 1.0 so that any detection at all
        # is measurable against it.
        sigma = float(np.sqrt(median)) if median > 0 else 1.0
    return RobustBaseline(
        median=median,
        mad=mad,
        sigma=float(sigma),
        sample_count=int(values.size),
        is_weak=values.size < min_samples,
    )


def robust_z_scores(values: np.ndarray, baseline: RobustBaseline | None = None) -> np.ndarray:
    """Robust z-scores for ``values`` against ``baseline`` (fitted if omitted)."""
    values = np.asarray(values, dtype=np.float64)
    baseline = baseline or fit_robust_baseline(values)
    if baseline.sigma <= 1e-9:
        return np.zeros_like(values)
    return (values - baseline.median) / baseline.sigma
