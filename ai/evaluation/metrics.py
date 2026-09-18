"""Classification metrics, written out on NumPy.

Everything the research module reports is computed here: per-class precision /
recall / F1, macro and micro averages, a confusion matrix, average precision and
mAP from ranked scores, top-k accuracy, and expected calibration error.

Abstentions are handled explicitly.  A model that declines to identify a sample
(``UNCERTAIN``) is not credited with a correct answer and is not charged with a
wrong one: ``coverage`` reports how often it committed, and the precision-style
metrics are computed over committed predictions while recall is computed over
all ground-truth samples.  Reporting a single accuracy number for an abstaining
model is exactly the kind of comparison that flatters fusion unfairly, so the
report keeps the two apart.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from itertools import pairwise

import numpy as np

UNCERTAIN_LABEL = "UNCERTAIN"


@dataclass(frozen=True)
class ClassificationReport:
    labels: list[str]
    support: dict[str, int]
    precision: dict[str, float]
    recall: dict[str, float]
    f1: dict[str, float]
    macro_precision: float
    macro_recall: float
    macro_f1: float
    micro_precision: float
    micro_recall: float
    micro_f1: float
    weighted_f1: float
    #: Correct ÷ all samples, with an abstention counted as incorrect.
    accuracy: float
    #: Correct ÷ committed samples — accuracy where the model did answer.
    selective_accuracy: float
    #: Share of samples where the model committed to a species.
    coverage: float
    balanced_accuracy: float
    matrix: list[list[int]] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "labels": self.labels,
            "support": self.support,
            "precision": {k: round(v, 6) for k, v in self.precision.items()},
            "recall": {k: round(v, 6) for k, v in self.recall.items()},
            "f1": {k: round(v, 6) for k, v in self.f1.items()},
            "macro_precision": round(self.macro_precision, 6),
            "macro_recall": round(self.macro_recall, 6),
            "macro_f1": round(self.macro_f1, 6),
            "micro_precision": round(self.micro_precision, 6),
            "micro_recall": round(self.micro_recall, 6),
            "micro_f1": round(self.micro_f1, 6),
            "weighted_f1": round(self.weighted_f1, 6),
            "accuracy": round(self.accuracy, 6),
            "selective_accuracy": round(self.selective_accuracy, 6),
            "coverage": round(self.coverage, 6),
            "balanced_accuracy": round(self.balanced_accuracy, 6),
        }


def confusion_matrix(
    y_true: list[str], y_pred: list[str], labels: list[str] | None = None
) -> tuple[np.ndarray, list[str]]:
    """Confusion matrix with ``UNCERTAIN`` kept as its own prediction column."""
    if len(y_true) != len(y_pred):
        raise ValueError("y_true and y_pred must have the same length")
    row_labels = labels or sorted({*y_true})
    column_labels = list(row_labels)
    if any(p == UNCERTAIN_LABEL for p in y_pred) and UNCERTAIN_LABEL not in column_labels:
        column_labels.append(UNCERTAIN_LABEL)
    for prediction in y_pred:
        if prediction not in column_labels:
            column_labels.append(prediction)

    row_index = {label: i for i, label in enumerate(row_labels)}
    column_index = {label: i for i, label in enumerate(column_labels)}
    matrix = np.zeros((len(row_labels), len(column_labels)), dtype=np.int64)
    for truth, prediction in zip(y_true, y_pred, strict=True):
        if truth not in row_index:  # pragma: no cover - caller passed partial labels
            continue
        matrix[row_index[truth], column_index[prediction]] += 1
    return matrix, column_labels


def precision_recall_f1(
    y_true: list[str], y_pred: list[str], labels: list[str] | None = None
) -> ClassificationReport:
    """Full per-class and averaged report."""
    if not y_true:
        raise ValueError("cannot compute metrics on an empty sample")
    labels = labels or sorted({*y_true})
    committed = [
        (truth, prediction)
        for truth, prediction in zip(y_true, y_pred, strict=True)
        if prediction != UNCERTAIN_LABEL
    ]

    precision: dict[str, float] = {}
    recall: dict[str, float] = {}
    f1: dict[str, float] = {}
    support: dict[str, int] = {}
    true_positive_total = 0
    predicted_total = len(committed)
    actual_total = len(y_true)

    for label in labels:
        true_positive = sum(
            1 for truth, prediction in committed if truth == label and prediction == label
        )
        false_positive = sum(
            1 for truth, prediction in committed if truth != label and prediction == label
        )
        label_support = sum(1 for truth in y_true if truth == label)
        support[label] = label_support
        true_positive_total += true_positive

        label_precision = (
            true_positive / (true_positive + false_positive)
            if (true_positive + false_positive) > 0
            else 0.0
        )
        label_recall = true_positive / label_support if label_support > 0 else 0.0
        precision[label] = label_precision
        recall[label] = label_recall
        f1[label] = (
            2 * label_precision * label_recall / (label_precision + label_recall)
            if (label_precision + label_recall) > 0
            else 0.0
        )

    present = [label for label in labels if support[label] > 0] or labels
    macro_precision = float(np.mean([precision[label] for label in present]))
    macro_recall = float(np.mean([recall[label] for label in present]))
    macro_f1 = float(np.mean([f1[label] for label in present]))
    micro_precision = true_positive_total / predicted_total if predicted_total else 0.0
    micro_recall = true_positive_total / actual_total if actual_total else 0.0
    micro_f1 = (
        2 * micro_precision * micro_recall / (micro_precision + micro_recall)
        if (micro_precision + micro_recall) > 0
        else 0.0
    )
    support_total = sum(support[label] for label in present) or 1
    weighted_f1 = float(
        sum(f1[label] * support[label] for label in present) / support_total
    )

    correct = sum(1 for truth, prediction in committed if truth == prediction)
    accuracy = correct / actual_total
    selective_accuracy = correct / predicted_total if predicted_total else 0.0
    coverage = predicted_total / actual_total
    balanced_accuracy = float(np.mean([recall[label] for label in present]))

    matrix, _ = confusion_matrix(y_true, y_pred, labels)
    return ClassificationReport(
        labels=list(labels),
        support=support,
        precision=precision,
        recall=recall,
        f1=f1,
        macro_precision=macro_precision,
        macro_recall=macro_recall,
        macro_f1=macro_f1,
        micro_precision=float(micro_precision),
        micro_recall=float(micro_recall),
        micro_f1=float(micro_f1),
        weighted_f1=weighted_f1,
        accuracy=float(accuracy),
        selective_accuracy=float(selective_accuracy),
        coverage=float(coverage),
        balanced_accuracy=balanced_accuracy,
        matrix=matrix.tolist(),
    )


def average_precision(
    y_true_binary: list[int] | np.ndarray, scores: list[float] | np.ndarray
) -> float:
    """Area under the precision-recall curve, by the step-wise (VOC-style) rule."""
    truth = np.asarray(y_true_binary, dtype=np.int64)
    score = np.asarray(scores, dtype=np.float64)
    if truth.size == 0 or truth.sum() == 0:
        return 0.0
    order = np.argsort(-score, kind="stable")
    truth = truth[order]
    true_positives = np.cumsum(truth)
    false_positives = np.cumsum(1 - truth)
    recall = true_positives / truth.sum()
    precision = true_positives / np.maximum(true_positives + false_positives, 1)
    # Sum precision at each point where recall increases.
    recall_previous = np.concatenate([[0.0], recall[:-1]])
    return float(np.sum((recall - recall_previous) * precision))


def mean_average_precision(
    y_true: list[str], score_rows: list[dict[str, float]], labels: list[str] | None = None
) -> tuple[float, dict[str, float]]:
    """mAP over per-class ranked scores.

    ``score_rows[i][label]`` is the score sample ``i`` received for ``label``;
    missing labels count as score 0.
    """
    labels = labels or sorted({*y_true})
    per_class: dict[str, float] = {}
    for label in labels:
        binary = [1 if truth == label else 0 for truth in y_true]
        if sum(binary) == 0:
            continue
        scores = [float(row.get(label, 0.0)) for row in score_rows]
        per_class[label] = average_precision(binary, scores)
    value = float(np.mean(list(per_class.values()))) if per_class else 0.0
    return value, per_class


def top_k_accuracy(
    y_true: list[str], ranked_predictions: list[list[str]], k: int = 3
) -> float:
    """Share of samples whose true label appears in the top ``k`` candidates."""
    if not y_true:
        return 0.0
    hits = sum(
        1
        for truth, ranked in zip(y_true, ranked_predictions, strict=True)
        if truth in ranked[:k]
    )
    return hits / len(y_true)


def expected_calibration_error(
    correct: list[bool] | np.ndarray, confidence: list[float] | np.ndarray, bins: int = 10
) -> float:
    """ECE: the average gap between stated confidence and observed accuracy.

    A model whose 0.9-confidence predictions are right 90% of the time scores 0.
    Reported alongside accuracy because an over-confident model is dangerous in a
    verification workflow: experts start trusting scores that do not earn it.
    """
    correct_array = np.asarray(correct, dtype=bool)
    confidence_array = np.asarray(confidence, dtype=np.float64)
    if correct_array.size == 0:
        return 0.0
    edges = np.linspace(0.0, 1.0, bins + 1)
    error = 0.0
    for lower, upper in pairwise(edges):
        in_bin = (confidence_array > lower) & (confidence_array <= upper)
        if lower == 0.0:
            in_bin |= confidence_array == 0.0
        if not in_bin.any():
            continue
        bin_weight = in_bin.mean()
        bin_accuracy = correct_array[in_bin].mean()
        bin_confidence = confidence_array[in_bin].mean()
        error += bin_weight * abs(bin_accuracy - bin_confidence)
    return float(error)


def confidence_histogram(
    confidence: list[float], bins: int = 10
) -> list[dict[str, float | int]]:
    """Confidence distribution, for the dashboard's AI panel."""
    values = np.asarray(confidence, dtype=np.float64)
    edges = np.linspace(0.0, 1.0, bins + 1)
    output: list[dict[str, float | int]] = []
    for lower, upper in pairwise(edges):
        mask = (values > lower) & (values <= upper)
        if lower == 0.0:
            mask |= values == 0.0
        output.append({"lower": float(lower), "upper": float(upper), "count": int(mask.sum())})
    return output
