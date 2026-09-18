"""Acoustic template matching.

Classical bioacoustic identification compares measured call parameters — peak
frequency, bandwidth, repetition (pulse) rate, duration and tonality — against
reference values for each species.  That is exactly what this backend does, over
the features produced by :func:`ai.preprocessing.audio.extract_audio_features`.

Each feature contributes a Gaussian match score around the reference value with
its own tolerance; the scores are combined in log space with per-feature weights
and turned into a distribution with a softmax.  Missing reference fields
contribute neutrally rather than penalising a species, so a partially described
call still competes.

This is the documented fallback: with a trained model available
(:mod:`ai.audio.torch_backend`) the pipeline prefers it.  The template matcher
remains valuable as an interpretable cross-check — :meth:`
BaselineAudioClassifier.explain` reports which call parameters matched.
"""

from __future__ import annotations

import math

import numpy as np

from ai.calibration import standardised_softmax
from ai.preprocessing.audio import AudioFeatures
from ai.schema import Candidate, SpeciesReference

#: Documentation of the ``species.acoustic_signature`` JSON contract.
ACOUSTIC_SCHEMA: dict[str, str] = {
    "peak_hz": "float — dominant frequency of the call",
    "peak_hz_tolerance": "float — acceptable spread around peak_hz (default 35%)",
    "bandwidth_hz": "float — spectral spread of the call",
    "pulse_rate_hz": "float — syllables or pulses per second (0 for continuous calls)",
    "pulse_rate_tolerance": "float — acceptable spread around pulse_rate_hz",
    "call_duration_s": "float — typical duration of a single call bout",
    "tonality": "float 0..1 — 1 for a pure whistle, 0 for broadband rasping",
    "band_profile": "list[float] — normalised energy in 8 mel bands (optional)",
    "vocal_type": "whistle | trill | hoot | call | bellow | screech | chirp | drum",
}

#: Relative weight of each call parameter in the combined log score.
FEATURE_WEIGHTS: dict[str, float] = {
    "peak_hz": 1.35,
    "bandwidth_hz": 0.65,
    "pulse_rate_hz": 1.00,
    "tonality": 0.80,
    "band_profile": 1.20,
    "call_duration_s": 0.35,
}

_DEFAULT_PEAK_TOLERANCE_SHARE = 0.35
_DEFAULT_PULSE_TOLERANCE = 1.6


def _gaussian(observed: float, reference: float, tolerance: float) -> float:
    tolerance = max(float(tolerance), 1e-6)
    return float(math.exp(-0.5 * ((observed - reference) / tolerance) ** 2))


def _bhattacharyya(observed: np.ndarray, reference: np.ndarray) -> float:
    """Overlap of two normalised energy profiles, in ``[0, 1]``."""
    if observed.size == 0 or reference.size == 0:
        return 0.5
    length = min(observed.size, reference.size)
    a = np.clip(observed[:length], 0.0, None)
    b = np.clip(reference[:length], 0.0, None)
    a = a / max(a.sum(), 1e-12)
    b = b / max(b.sum(), 1e-12)
    return float(np.sqrt(a * b).sum())


def feature_match_scores(
    features: AudioFeatures, signature: dict
) -> tuple[float, dict[str, float]]:
    """Return ``(combined_score, per_feature_scores)`` in ``[0, 1]``.

    A feature absent from the signature is scored ``None`` and excluded from the
    weighted mean, so species described only by their peak frequency are not
    penalised against fully described ones.
    """
    signature = signature or {}
    scores: dict[str, float] = {}

    peak_reference = signature.get("peak_hz")
    if peak_reference:
        tolerance = float(
            signature.get("peak_hz_tolerance")
            or max(float(peak_reference) * _DEFAULT_PEAK_TOLERANCE_SHARE, 150.0)
        )
        scores["peak_hz"] = _gaussian(features.peak_frequency_hz, float(peak_reference), tolerance)

    bandwidth_reference = signature.get("bandwidth_hz")
    if bandwidth_reference:
        scores["bandwidth_hz"] = _gaussian(
            features.bandwidth_hz,
            float(bandwidth_reference),
            max(float(bandwidth_reference) * 0.6, 200.0),
        )

    pulse_reference = signature.get("pulse_rate_hz")
    if pulse_reference is not None:
        pulse_reference = float(pulse_reference)
        tolerance = float(signature.get("pulse_rate_tolerance") or _DEFAULT_PULSE_TOLERANCE)
        if pulse_reference <= 0.0:
            # Continuous call: reward the *absence* of strong periodicity.
            scores["pulse_rate_hz"] = _gaussian(features.pulse_rate_hz, 0.0, 1.2)
        elif features.pulse_rate_hz <= 0.0:
            # A pulsed reference against a recording with no detectable rhythm.
            scores["pulse_rate_hz"] = 0.25
        else:
            scores["pulse_rate_hz"] = _gaussian(
                features.pulse_rate_hz, pulse_reference, tolerance
            )

    tonality_reference = signature.get("tonality")
    if tonality_reference is not None:
        scores["tonality"] = _gaussian(features.tonality, float(tonality_reference), 0.28)

    band_profile = signature.get("band_profile")
    if band_profile:
        scores["band_profile"] = _bhattacharyya(
            np.asarray(features.band_energies, dtype=np.float64),
            np.asarray(band_profile, dtype=np.float64),
        )

    duration_reference = signature.get("call_duration_s")
    if duration_reference:
        # Recordings are longer than a single call, so only penalise a recording
        # that is shorter than one call bout.
        reference = float(duration_reference)
        scores["call_duration_s"] = (
            1.0
            if features.duration_seconds >= reference
            else _gaussian(features.duration_seconds, reference, max(reference * 0.8, 0.2))
        )

    if not scores:
        return 0.0, {}

    weight_total = sum(FEATURE_WEIGHTS.get(name, 1.0) for name in scores)
    log_score = sum(
        FEATURE_WEIGHTS.get(name, 1.0) * math.log(max(value, 1e-6))
        for name, value in scores.items()
    )
    combined = math.exp(log_score / max(weight_total, 1e-9))
    return float(combined), {name: round(value, 6) for name, value in scores.items()}


class BaselineAudioClassifier:
    """Template-matching species classifier over acoustic features."""

    backend = "baseline"
    name = "vanraksha-audio-baseline"
    version = "1.0.0"

    def __init__(
        self, references: list[SpeciesReference], *, temperature: float = 0.45
    ) -> None:
        self._references = [r for r in references if r.is_audible]
        self._temperature = temperature

    @property
    def classes(self) -> list[SpeciesReference]:
        return list(self._references)

    def _scores(self, features: AudioFeatures) -> list[tuple[SpeciesReference, float, dict]]:
        results = []
        for reference in self._references:
            score, detail = feature_match_scores(features, reference.acoustic_signature)
            results.append((reference, score, detail))
        return results

    def classify(self, features: AudioFeatures, *, top_k: int = 5) -> list[Candidate]:
        raw = self._scores(features)
        if not raw:
            return []
        values = np.array([score for _, score, _ in raw], dtype=np.float64)
        # Standardised softmax, exactly as the vision baseline does, so both
        # modalities' confidences mean the same thing to the fusion layer and to
        # the shared confidence gate.
        probabilities = standardised_softmax(values, self._temperature, higher_is_better=True)
        order = np.argsort(probabilities)[::-1][:top_k]
        return [
            Candidate(
                species_id=raw[int(i)][0].species_id,
                label=raw[int(i)][0].label,
                scientific_name=raw[int(i)][0].scientific_name,
                confidence=float(probabilities[int(i)]),
            )
            for i in order
        ]

    def explain(self, features: AudioFeatures) -> dict:
        raw = self._scores(features)
        if not raw:
            return {"reason": "no species in the reference set has an acoustic signature"}
        best = max(raw, key=lambda item: item[1])
        reference, score, detail = best
        matched = sorted(detail.items(), key=lambda kv: kv[1], reverse=True)
        return {
            "backend": self.backend,
            "top_label": reference.label,
            "template_score": round(score, 6),
            "parameter_scores": detail,
            "strongest_parameters": [name for name, _ in matched[:3]],
            "weakest_parameters": [name for name, _ in matched[-2:]],
            "measured": features.as_dict(),
        }
