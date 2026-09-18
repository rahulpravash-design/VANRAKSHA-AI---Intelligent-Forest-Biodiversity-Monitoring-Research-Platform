"""Evaluation metrics and the research experiment harness."""

from ai.evaluation.experiment import (
    VARIANTS,
    ComparisonReport,
    VariantResult,
    compare_variants,
    run_variant,
)
from ai.evaluation.metrics import (
    ClassificationReport,
    average_precision,
    confusion_matrix,
    expected_calibration_error,
    mean_average_precision,
    precision_recall_f1,
    top_k_accuracy,
)

__all__ = [
    "VARIANTS",
    "ClassificationReport",
    "ComparisonReport",
    "VariantResult",
    "average_precision",
    "compare_variants",
    "confusion_matrix",
    "expected_calibration_error",
    "mean_average_precision",
    "precision_recall_f1",
    "run_variant",
    "top_k_accuracy",
]
