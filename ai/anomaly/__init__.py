"""Unusual-observation-pattern detection.

The detector answers one question — *is this window unlike the recent
baseline?* — and never the question of *why*.  Every finding carries ranked
candidate causes for a human to investigate; see
:func:`ai.anomaly.detector.candidate_causes`.
"""

from ai.anomaly.detector import (
    AnomalyFinding,
    BiodiversityAnomalyDetector,
    candidate_causes,
)
from ai.anomaly.isolation_forest import IsolationForest
from ai.anomaly.robust_z import RobustBaseline, robust_z_scores

__all__ = [
    "AnomalyFinding",
    "BiodiversityAnomalyDetector",
    "IsolationForest",
    "RobustBaseline",
    "candidate_causes",
    "robust_z_scores",
]
