"""Log-linear late fusion.

Each modality contributes a distribution over species (its ``top_k``, with the
remaining probability mass assigned to an explicit "unlisted" outcome).  The
distributions are combined as a weighted geometric mean — a log-linear opinion
pool — which has two properties that matter here:

* **agreement compounds.** Two modalities that independently favour the same
  species produce a sharper posterior than either alone.
* **disagreement is punished, not averaged.** A species that one modality rules
  out cannot win on the strength of the other, which is the failure mode of a
  plain weighted average.

An optional context prior (habitat, time of day, what this zone has historically
recorded) is applied multiplicatively with a bounded strength, so context can
break a tie but cannot manufacture a detection on its own.

Fusion is offered as a *hypothesis to be tested*, not an assumed improvement:
:mod:`ai.evaluation.experiment` scores it against the single-modality baselines
on the same split, and the platform's research module reports the difference.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass

import numpy as np

from ai.calibration import reliability
from ai.config import AIConfig, get_config
from ai.schema import UNCERTAIN_LABEL, Candidate, Prediction, uncertain

MODEL_NAME = "vanraksha-multimodal-fusion"
MODEL_VERSION = "1.0.0"
#: Probability mass a modality keeps for "a species outside my top-k".
RESIDUAL_FLOOR = 1e-4
UNLISTED_KEY = ("__unlisted__", None)


@dataclass(frozen=True)
class FusionWeights:
    image: float = 0.6
    audio: float = 0.4

    def normalised(self, *, has_image: bool, has_audio: bool) -> tuple[float, float]:
        image = self.image if has_image else 0.0
        audio = self.audio if has_audio else 0.0
        total = image + audio
        if total <= 0:
            return 0.0, 0.0
        return image / total, audio / total


def _key(candidate: Candidate) -> tuple[str, int | None]:
    """Species id when known, otherwise the label — models may emit unmapped classes."""
    return (candidate.label, candidate.species_id)


def _distribution(prediction: Prediction | None) -> dict[tuple[str, int | None], float]:
    """Turn a prediction's top-k into a proper distribution.

    An ``UNCERTAIN`` prediction still carries information: its ranked candidates
    are used, and the mass it did not commit stays on the "unlisted" outcome.
    """
    if prediction is None:
        return {}
    candidates = list(prediction.top_k)
    if not candidates and prediction.label != UNCERTAIN_LABEL:
        candidates = [
            Candidate(
                species_id=prediction.species_id,
                label=prediction.label,
                scientific_name=prediction.scientific_name,
                confidence=prediction.confidence,
            )
        ]
    if not candidates:
        return {}
    distribution: dict[tuple[str, int | None], float] = {}
    for candidate in candidates:
        distribution[_key(candidate)] = max(float(candidate.confidence), RESIDUAL_FLOOR)
    total = sum(distribution.values())
    if total <= 0:
        return {}
    # Keep any residual mass explicit instead of renormalising it away.
    residual = max(0.0, 1.0 - total)
    distribution = {k: v / max(total + residual, 1e-12) for k, v in distribution.items()}
    if residual > RESIDUAL_FLOOR:
        distribution[UNLISTED_KEY] = residual / max(total + residual, 1e-12)
    return distribution


def context_prior_from_history(
    history: Mapping[tuple[str, int | None] | int | str, float],
    *,
    strength: float = 0.25,
    smoothing: float = 1.0,
) -> dict[tuple[str, int | None] | int | str, float]:
    """Build a bounded empirical prior from past detections.

    ``history`` maps a species key to how often it has been recorded in the
    relevant zone/season.  The prior is add-one smoothed and then flattened
    towards uniform by ``1 - strength``, so a species never seen before is
    unlikely but never impossible.
    """
    if not history:
        return {}
    strength = float(np.clip(strength, 0.0, 1.0))
    counts = {key: max(float(value), 0.0) + smoothing for key, value in history.items()}
    total = sum(counts.values())
    uniform = 1.0 / len(counts)
    return {
        key: (1.0 - strength) * uniform + strength * (value / total)
        for key, value in counts.items()
    }


def _prior_for(
    key: tuple[str, int | None],
    prior: Mapping | None,
    default: float,
) -> float:
    if not prior:
        return default
    label, species_id = key
    for lookup in (key, species_id, label):
        if lookup is not None and lookup in prior:
            return max(float(prior[lookup]), 1e-6)
    return default


def fuse_predictions(
    image: Prediction | None,
    audio: Prediction | None,
    *,
    context_prior: Mapping | None = None,
    weights: FusionWeights | None = None,
    config: AIConfig | None = None,
) -> Prediction:
    """Combine modality predictions into a single ``FUSED`` prediction."""
    config = config or get_config()
    weights = weights or FusionWeights(config.image_weight, config.audio_weight)

    image_distribution = _distribution(image)
    audio_distribution = _distribution(audio)
    has_image = bool(image_distribution)
    has_audio = bool(audio_distribution)

    latency = sum(
        p.latency_ms or 0 for p in (image, audio) if p is not None
    ) or None
    diagnostics: dict = {
        "modalities_used": [
            name for name, present in (("IMAGE", has_image), ("AUDIO", has_audio)) if present
        ],
        "image_backend": image.model_name if image else None,
        "audio_backend": audio.model_name if audio else None,
        "context_prior_applied": bool(context_prior),
        "context_strength": config.context_strength,
    }

    if not has_image and not has_audio:
        diagnostics["reason"] = "no modality produced any candidates"
        return uncertain(
            "FUSED", MODEL_NAME, MODEL_VERSION, diagnostics=diagnostics, latency_ms=latency
        )

    # Reliability weighting: a modality that spread its mass evenly over the
    # catalogue is saying "I don't know", and must not be able to dilute a
    # confident partner just because its configured weight is larger. Fixed
    # weights alone made fusion score *below* audio-only on the reference
    # benchmark; discounting by each modality's peakedness is what fixes it.
    image_reliability = reliability(np.fromiter(image_distribution.values(), dtype=float))
    audio_reliability = reliability(np.fromiter(audio_distribution.values(), dtype=float))
    exponent = max(float(config.reliability_exponent), 0.0)
    effective = FusionWeights(
        image=weights.image * (max(image_reliability, 1e-3) ** exponent),
        audio=weights.audio * (max(audio_reliability, 1e-3) ** exponent),
    )
    image_weight, audio_weight = effective.normalised(has_image=has_image, has_audio=has_audio)
    diagnostics["weights"] = {"image": round(image_weight, 4), "audio": round(audio_weight, 4)}
    diagnostics["reliability"] = {
        "image": round(image_reliability, 4) if has_image else None,
        "audio": round(audio_reliability, 4) if has_audio else None,
    }

    keys = set(image_distribution) | set(audio_distribution)
    keys.discard(UNLISTED_KEY)
    if not keys:  # pragma: no cover - only if both modalities were all-residual
        diagnostics["reason"] = "both modalities placed all mass outside their top-k"
        return uncertain(
            "FUSED", MODEL_NAME, MODEL_VERSION, diagnostics=diagnostics, latency_ms=latency
        )

    # A species missing from a modality's top-k inherits that modality's
    # residual mass — absence is weak evidence against, not proof against.
    image_residual = image_distribution.get(UNLISTED_KEY, RESIDUAL_FLOOR)
    audio_residual = audio_distribution.get(UNLISTED_KEY, RESIDUAL_FLOOR)
    default_prior = 1.0 / max(len(keys), 1)

    log_scores: dict[tuple[str, int | None], float] = {}
    per_key_detail: dict[str, dict[str, float]] = {}
    for key in keys:
        image_probability = image_distribution.get(key, image_residual)
        audio_probability = audio_distribution.get(key, audio_residual)
        log_score = 0.0
        if image_weight > 0:
            log_score += image_weight * math.log(max(image_probability, RESIDUAL_FLOOR))
        if audio_weight > 0:
            log_score += audio_weight * math.log(max(audio_probability, RESIDUAL_FLOOR))
        if context_prior:
            prior = _prior_for(key, context_prior, default_prior)
            log_score += config.context_strength * math.log(max(prior, 1e-6))
        log_scores[key] = log_score
        per_key_detail[key[0]] = {
            "image": round(image_probability, 6),
            "audio": round(audio_probability, 6),
        }

    ordered = sorted(log_scores.items(), key=lambda kv: kv[1], reverse=True)
    max_log = ordered[0][1]
    exponentials = {key: math.exp(value - max_log) for key, value in ordered}
    normaliser = sum(exponentials.values()) or 1.0
    probabilities = [(key, value / normaliser) for key, value in exponentials.items()]
    probabilities.sort(key=lambda kv: kv[1], reverse=True)

    scientific_names = {
        _key(c): c.scientific_name
        for prediction in (image, audio)
        if prediction is not None
        for c in prediction.top_k
    }
    candidates = tuple(
        Candidate(
            species_id=key[1],
            label=key[0],
            scientific_name=scientific_names.get(key),
            confidence=float(probability),
        )
        for key, probability in probabilities[: config.top_k]
    )

    top = candidates[0]
    runner_up = candidates[1].confidence if len(candidates) > 1 else 0.0
    margin = top.confidence - runner_up

    image_top = image.top_k[0].label if image and image.top_k else None
    audio_top = audio.top_k[0].label if audio and audio.top_k else None
    diagnostics.update(
        {
            "modality_top_labels": {"image": image_top, "audio": audio_top},
            "modalities_agree": bool(image_top and audio_top and image_top == audio_top),
            "per_candidate": per_key_detail,
            "top_confidence": round(top.confidence, 6),
            "margin": round(margin, 6),
        }
    )

    if top.confidence < config.min_confidence:
        diagnostics["reason"] = "fused top-1 confidence below threshold"
    elif margin < config.uncertain_margin:
        diagnostics["reason"] = "fused top-1 and top-2 are too close to separate"
    else:
        return Prediction(
            modality="FUSED",
            model_name=MODEL_NAME,
            model_version=MODEL_VERSION,
            label=top.label,
            confidence=top.confidence,
            is_uncertain=False,
            species_id=top.species_id,
            scientific_name=top.scientific_name,
            top_k=candidates,
            detections=tuple(image.detections) if image else (),
            diagnostics=diagnostics,
            latency_ms=latency,
        )

    return uncertain(
        "FUSED",
        MODEL_NAME,
        MODEL_VERSION,
        confidence=top.confidence,
        top_k=candidates,
        detections=tuple(image.detections) if image else (),
        diagnostics=diagnostics,
        latency_ms=latency,
    )
