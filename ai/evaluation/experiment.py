"""The modality-comparison harness.

Answers the platform's headline research question — *does combining image and
acoustic evidence identify species better than either alone?* — by scoring four
variants on one identical split:

===========================  =================================================
variant                       evidence used
===========================  =================================================
``image_only``                photograph
``audio_only``                recording
``image_audio``               both, log-linear late fusion
``image_audio_context``       both, plus an empirical time-of-day/zone prior
===========================  =================================================

Three design choices keep the comparison honest:

* **One split, one seed.** Every variant sees the same samples in the same
  order, so a difference cannot come from an easier draw.
* **No prior leakage.** The contextual prior for ``image_audio_context`` is
  fitted on a disjoint slice of the data and never on the evaluated samples.
* **Abstentions counted, not hidden.** A variant that answers less often scores
  a lower ``coverage``; ``selective_accuracy`` shows how it did when it *did*
  answer. Reporting only one of the two is how abstaining models get flattered.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

import numpy as np

from ai.audio.pipeline import AudioPipeline
from ai.config import AIConfig, get_config
from ai.datasets.synthetic import SyntheticSample
from ai.evaluation.metrics import (
    UNCERTAIN_LABEL,
    ClassificationReport,
    expected_calibration_error,
    mean_average_precision,
    precision_recall_f1,
    top_k_accuracy,
)
from ai.multimodal.fusion import (
    FusionWeights,
    context_prior_from_history,
    fuse_predictions,
)
from ai.schema import Prediction, uncertain
from ai.vision.pipeline import VisionPipeline

VARIANTS: tuple[str, ...] = (
    "image_only",
    "audio_only",
    "image_audio",
    "image_audio_context",
)
#: Share of the dataset reserved for fitting the contextual prior.
PRIOR_SPLIT = 0.35


@dataclass
class VariantResult:
    variant: str
    report: ClassificationReport
    mean_average_precision: float
    per_class_average_precision: dict[str, float]
    top_3_accuracy: float
    expected_calibration_error: float
    uncertain_share: float
    mean_latency_ms: float
    sample_count: int
    confusion_labels: list[str] = field(default_factory=list)

    def metrics(self) -> dict:
        data = self.report.as_dict()
        data.update(
            {
                "mean_average_precision": round(self.mean_average_precision, 6),
                "top_3_accuracy": round(self.top_3_accuracy, 6),
                "expected_calibration_error": round(self.expected_calibration_error, 6),
                "uncertain_share": round(self.uncertain_share, 6),
                "mean_latency_ms": round(self.mean_latency_ms, 3),
                "sample_count": self.sample_count,
            }
        )
        return data


def _predict_image(
    sample: SyntheticSample, vision: VisionPipeline
) -> Prediction | None:
    if not sample.has_image:
        return None
    return vision.predict(sample.image)


def _predict_audio(
    sample: SyntheticSample, audio: AudioPipeline
) -> Prediction | None:
    if not sample.has_audio:
        return None
    return audio.predict_from_features(sample.audio_features)


def _fit_context_prior(
    samples: Sequence[SyntheticSample],
) -> dict[int, dict[str, float]]:
    """Hour-of-day → species prior, fitted on the held-out prior slice."""
    counts: dict[int, dict[str, float]] = {}
    for sample in samples:
        hour = int(sample.context.get("hour", 12))
        bucket = counts.setdefault(hour, {})
        bucket[sample.label] = bucket.get(sample.label, 0.0) + 1.0
    return {
        hour: context_prior_from_history(bucket, strength=0.5)
        for hour, bucket in counts.items()
    }


def run_variant(
    variant: str,
    samples: Sequence[SyntheticSample],
    *,
    vision: VisionPipeline,
    audio: AudioPipeline,
    config: AIConfig | None = None,
    context_priors: dict[int, dict[str, float]] | None = None,
) -> VariantResult:
    """Score one variant over ``samples``."""
    if variant not in VARIANTS:
        raise ValueError(f"unknown variant {variant!r}; expected one of {VARIANTS}")
    config = config or get_config()
    weights = FusionWeights(config.image_weight, config.audio_weight)

    truths: list[str] = []
    predictions: list[str] = []
    score_rows: list[dict[str, float]] = []
    ranked: list[list[str]] = []
    confidences: list[float] = []
    correct_flags: list[bool] = []
    latencies: list[float] = []
    uncertain_count = 0

    for sample in samples:
        image_prediction = (
            _predict_image(sample, vision)
            if variant != "audio_only"
            else None
        )
        audio_prediction = (
            _predict_audio(sample, audio) if variant != "image_only" else None
        )

        if variant == "image_only":
            prediction = image_prediction
        elif variant == "audio_only":
            prediction = audio_prediction
        else:
            prior = None
            if variant == "image_audio_context" and context_priors:
                prior = context_priors.get(int(sample.context.get("hour", 12)))
            prediction = fuse_predictions(
                image_prediction,
                audio_prediction,
                context_prior=prior,
                weights=weights,
                config=config,
            )

        if prediction is None:
            prediction = uncertain("NONE", "no-evidence", "0", diagnostics={})

        label = UNCERTAIN_LABEL if prediction.is_uncertain else prediction.label
        truths.append(sample.label)
        predictions.append(label)
        if prediction.is_uncertain:
            uncertain_count += 1
        confidences.append(float(prediction.confidence))
        correct_flags.append(label == sample.label)
        latencies.append(float(prediction.latency_ms or 0))
        row = {c.label: float(c.confidence) for c in prediction.top_k}
        if not row and not prediction.is_uncertain:
            row = {prediction.label: float(prediction.confidence)}
        score_rows.append(row)
        ranked.append([c.label for c in prediction.top_k] or ([label] if label else []))

    labels = sorted(set(truths))
    report = precision_recall_f1(truths, predictions, labels)
    map_value, per_class = mean_average_precision(truths, score_rows, labels)
    return VariantResult(
        variant=variant,
        report=report,
        mean_average_precision=map_value,
        per_class_average_precision={k: round(v, 6) for k, v in per_class.items()},
        top_3_accuracy=top_k_accuracy(truths, ranked, k=3),
        expected_calibration_error=expected_calibration_error(correct_flags, confidences),
        uncertain_share=uncertain_count / max(len(samples), 1),
        mean_latency_ms=float(np.mean(latencies)) if latencies else 0.0,
        sample_count=len(samples),
        confusion_labels=labels,
    )


def _metric(result: VariantResult, attribute: str) -> float:
    """Read a metric from a :class:`VariantResult`, wherever it lives."""
    if hasattr(result.report, attribute):
        return float(getattr(result.report, attribute))
    return float(getattr(result, attribute))


@dataclass
class ComparisonReport:
    results: dict[str, VariantResult]
    best_variant: str
    fusion_gain_f1: float
    conclusion: str
    sample_count: int
    random_seed: int

    def as_dict(self) -> dict:
        return {
            "results": {name: result.metrics() for name, result in self.results.items()},
            "best_variant": self.best_variant,
            "fusion_gain_f1": round(self.fusion_gain_f1, 6),
            "conclusion": self.conclusion,
            "sample_count": self.sample_count,
            "random_seed": self.random_seed,
        }


def compare_variants(
    samples: Sequence[SyntheticSample],
    *,
    vision: VisionPipeline,
    audio: AudioPipeline,
    variants: Sequence[str] = VARIANTS,
    config: AIConfig | None = None,
    random_seed: int = 20260917,
) -> ComparisonReport:
    """Run every requested variant on the same evaluation split."""
    if not samples:
        raise ValueError("cannot run an experiment on an empty dataset")
    config = config or get_config()

    split = max(1, int(len(samples) * PRIOR_SPLIT))
    prior_samples, evaluation_samples = samples[:split], samples[split:]
    if not evaluation_samples:  # pragma: no cover - tiny datasets
        prior_samples, evaluation_samples = samples, samples
    context_priors = _fit_context_prior(prior_samples)

    results: dict[str, VariantResult] = {}
    for variant in variants:
        results[variant] = run_variant(
            variant,
            evaluation_samples,
            vision=vision,
            audio=audio,
            config=config,
            context_priors=context_priors,
        )

    best_variant = max(results, key=lambda name: results[name].report.macro_f1)
    single_names = [n for n in ("image_only", "audio_only") if n in results]
    fused_names = [n for n in ("image_audio", "image_audio_context") if n in results]

    def best_of(names: list[str], attribute: str) -> tuple[str, float] | None:
        if not names:
            return None
        scored = [(n, float(_metric(results[n], attribute))) for n in names]
        return max(scored, key=lambda kv: kv[1])

    best_single_f1 = best_of(single_names, "macro_f1")
    best_fused_f1 = best_of(fused_names, "macro_f1")
    gain = (best_fused_f1[1] - best_single_f1[1]) if (best_single_f1 and best_fused_f1) else 0.0

    if not best_single_f1 or not best_fused_f1:
        conclusion = (
            "Not enough variants were run to compare fusion against a single-modality "
            "baseline."
        )
    else:
        single_name, single_f1 = best_single_f1
        fused_name, fused_f1 = best_fused_f1
        coverage_gain = (
            results[fused_name].report.coverage - results[single_name].report.coverage
        )
        map_gain = (
            results[fused_name].mean_average_precision
            - results[single_name].mean_average_precision
        )
        headline = (
            f"macro-F1 {fused_f1:.3f} for '{fused_name}' versus {single_f1:.3f} for the best "
            f"single modality ('{single_name}')"
        )
        if abs(gain) <= 0.02:
            verdict = f"Fusion and the best single modality are within {abs(gain):.3f} macro-F1"
        elif gain > 0:
            verdict = f"Fusion improved macro-F1 by {gain:.3f}"
        else:
            verdict = f"Fusion scored {abs(gain):.3f} macro-F1 below the best single modality"
        # Macro-F1 alone hides the effect fusion actually has here: it changes how
        # often the system is willing to answer at all, and how well it ranks the
        # alternatives it offers an expert. Both are reported explicitly.
        detail = (
            f"It answered on {coverage_gain:+.1%} more samples "
            f"(coverage {results[fused_name].report.coverage:.3f} versus "
            f"{results[single_name].report.coverage:.3f}) and its ranking quality changed by "
            f"{map_gain:+.3f} mAP."
        )
        caveat = (
            "Measured on the seeded reference benchmark, not on field recordings; the "
            "comparison establishes the relative ordering of the variants under identical "
            "conditions, and field validation is still required before any claim of "
            "accuracy."
        )
        conclusion = f"{verdict} — {headline}. {detail} {caveat}"

    return ComparisonReport(
        results=results,
        best_variant=best_variant,
        fusion_gain_f1=float(gain),
        conclusion=conclusion,
        sample_count=len(evaluation_samples),
        random_seed=random_seed,
    )
