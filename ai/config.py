"""AI engine configuration.

Reads the same environment variables as the backend so a single ``.env`` drives
both processes, but has no dependency on the backend package — the AI engine can
be imported, trained and served on its own.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ[name])
    except (KeyError, ValueError):
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ[name])
    except (KeyError, ValueError):
        return default


@dataclass(frozen=True)
class AIConfig:
    # --------------------------------------------------------------- backends
    #: ``auto`` prefers a trained backend and falls back to the baseline.
    vision_backend: str = "auto"
    audio_backend: str = "auto"
    vision_weights: str = ""
    audio_weights: str = ""

    # ------------------------------------------------------------ thresholds
    #: Below this top-1 confidence the pipeline reports ``UNCERTAIN``.
    min_confidence: float = 0.45
    #: Minimum top1 − top2 gap; a close call is reported as ``UNCERTAIN`` too.
    uncertain_margin: float = 0.08
    #: Softmax temperature for the vision descriptor distances. Chosen so the
    #: confidence gate commits on the decisive minority of frames rather than on
    #: everything — see docs/research/ai-methodology.md.
    score_temperature: float = 0.30
    #: Softmax temperature for acoustic template-match scores.
    audio_temperature: float = 0.25
    #: How sharply a modality's entropy discounts its fusion weight
    #: (0 = fixed weights, 1 = fully reliability-weighted).
    reliability_exponent: float = 1.0
    #: Number of alternatives returned alongside the top prediction.
    top_k: int = 5

    # --------------------------------------------------------------- vision
    image_size: int = 224
    detection_score_threshold: float = 0.25
    max_detections: int = 12

    # ---------------------------------------------------------------- audio
    audio_sample_rate: int = 22_050
    n_fft: int = 1024
    hop_length: int = 256
    n_mels: int = 64
    fmin_hz: float = 60.0
    fmax_hz: float = 10_000.0
    #: Spectral-gating strength for noise reduction (0 = off, 1 = aggressive).
    noise_reduction: float = 0.6
    max_audio_seconds: float = 60.0

    # -------------------------------------------------------------- anomaly
    baseline_days: int = 90
    window_days: int = 7
    z_threshold: float = 3.0
    contamination: float = 0.08
    isolation_trees: int = 128
    isolation_sample_size: int = 256

    # ------------------------------------------------------------- fusion
    image_weight: float = 0.6
    audio_weight: float = 0.4
    #: How strongly contextual priors (hour of day, habitat) may move a score.
    context_strength: float = 0.25

    random_seed: int = 20260917
    candidate_causes: tuple[str, ...] = field(
        default_factory=lambda: (
            "Seasonal migration or phenology",
            "Weather conditions during the window",
            "Sensor or camera malfunction",
            "Gap in data collection or connectivity",
            "Habitat change (fire, felling, flooding)",
            "Human activity in the zone",
        )
    )

    @classmethod
    def from_env(cls) -> AIConfig:
        return cls(
            vision_backend=os.environ.get("AI_VISION_BACKEND", "auto"),
            audio_backend=os.environ.get("AI_AUDIO_BACKEND", "auto"),
            vision_weights=os.environ.get("AI_VISION_WEIGHTS", ""),
            audio_weights=os.environ.get("AI_AUDIO_WEIGHTS", ""),
            min_confidence=_env_float("AI_MIN_CONFIDENCE", 0.45),
            uncertain_margin=_env_float("AI_UNCERTAIN_MARGIN", 0.08),
            baseline_days=_env_int("ANOMALY_BASELINE_DAYS", 90),
            window_days=_env_int("ANOMALY_WINDOW_DAYS", 7),
            z_threshold=_env_float("ANOMALY_Z_THRESHOLD", 3.0),
            contamination=_env_float("ANOMALY_CONTAMINATION", 0.08),
        )


@lru_cache
def get_config() -> AIConfig:
    return AIConfig.from_env()
