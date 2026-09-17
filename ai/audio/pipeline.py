"""The audio pipeline: decode → denoise → features → classify → gate.

Two gates are applied before a species is reported:

1. **Signal gate** — a recording whose energy never rises above the estimated
   noise floor is reported as ``UNCERTAIN`` with the reason "no acoustic
   activity detected", not as a species at low confidence.
2. **Confidence gate** — the same top-1 / margin thresholds the vision pipeline
   uses, so both modalities decline to commit under the same rules.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path


from ai.audio.baseline import BaselineAudioClassifier
from ai.audio.torch_backend import TorchAudioBackend, torch_available
from ai.config import AIConfig, get_config
from ai.preprocessing.audio import (
    AudioFeatures,
    DecodedAudio,
    decode_audio,
    extract_audio_features,
)
from ai.schema import Candidate, Prediction, SpeciesReference, uncertain

logger = logging.getLogger(__name__)

MIN_ACTIVITY_RATIO = 0.02
MIN_SNR_DB = 1.0


class AudioPipeline:
    """Identify a species from a field recording."""

    modality = "AUDIO"

    def __init__(self, backend, config: AIConfig | None = None) -> None:
        self._backend = backend
        self._config = config or get_config()

    # ------------------------------------------------------------ properties
    @property
    def backend_name(self) -> str:
        return getattr(self._backend, "backend", "unknown")

    @property
    def model_name(self) -> str:
        return getattr(self._backend, "name", "unknown")

    @property
    def model_version(self) -> str:
        return getattr(self._backend, "version", "0")

    @property
    def classes(self) -> list[SpeciesReference]:
        return list(getattr(self._backend, "classes", []))

    def info(self) -> dict:
        return {
            "modality": self.modality,
            "name": self.model_name,
            "version": self.model_version,
            "backend": self.backend_name,
            "class_count": len(self.classes),
            "min_confidence": self._config.min_confidence,
            "uncertain_margin": self._config.uncertain_margin,
            "notes": (
                "Acoustic template matching — set AI_AUDIO_WEIGHTS to use a trained "
                "spectrogram CNN."
                if self.backend_name == "baseline"
                else None
            ),
        }

    # ------------------------------------------------------------- inference
    def analyse(
        self, source: bytes | str | Path | DecodedAudio, *, filename: str | None = None
    ) -> tuple[DecodedAudio, AudioFeatures]:
        """Decode and measure a recording without classifying it."""
        audio = (
            source
            if isinstance(source, DecodedAudio)
            else decode_audio(
                source,
                filename=filename,
                target_sample_rate=self._config.audio_sample_rate,
                max_seconds=self._config.max_audio_seconds,
            )
        )
        features = extract_audio_features(
            audio,
            n_fft=self._config.n_fft,
            hop_length=self._config.hop_length,
            n_mels=self._config.n_mels,
            fmin=self._config.fmin_hz,
            fmax=self._config.fmax_hz,
            noise_reduction=self._config.noise_reduction,
        )
        return audio, features

    def predict(
        self, source: bytes | str | Path | DecodedAudio, *, filename: str | None = None
    ) -> Prediction:
        started = time.perf_counter()
        audio, features = self.analyse(source, filename=filename)

        diagnostics: dict = {
            "backend": self.backend_name,
            "features": features.as_dict(),
            "sample_rate": audio.sample_rate,
            "source_format": audio.source_format,
            "noise_reduction": self._config.noise_reduction,
        }

        # ---- gate 1: is there anything to classify? -----------------------
        if audio.is_silent or (
            features.activity_ratio < MIN_ACTIVITY_RATIO and features.snr_db < MIN_SNR_DB
        ):
            diagnostics["reason"] = "no acoustic activity above the estimated noise floor"
            return uncertain(
                self.modality,
                self.model_name,
                self.model_version,
                diagnostics=diagnostics,
                latency_ms=int((time.perf_counter() - started) * 1000),
            )

        classifier_input = audio if self.backend_name == "torch" else features
        candidates: list[Candidate] = list(
            self._backend.classify(classifier_input, top_k=self._config.top_k)
        )
        explain = getattr(self._backend, "explain", None)
        if callable(explain):
            try:
                diagnostics["explanation"] = explain(classifier_input)
            except Exception:  # pragma: no cover - diagnostics are best-effort
                logger.debug("audio explanation failed", exc_info=True)
        latency_ms = int((time.perf_counter() - started) * 1000)

        if not candidates:
            diagnostics["reason"] = "no reference species has an acoustic signature"
            return uncertain(
                self.modality,
                self.model_name,
                self.model_version,
                diagnostics=diagnostics,
                latency_ms=latency_ms,
            )

        top = candidates[0]
        runner_up = candidates[1].confidence if len(candidates) > 1 else 0.0
        margin = top.confidence - runner_up
        diagnostics.update(
            {"top_confidence": round(top.confidence, 6), "margin": round(margin, 6)}
        )

        # ---- gate 2: is the model confident enough to commit? -------------
        if top.confidence < self._config.min_confidence:
            diagnostics["reason"] = "top-1 confidence below threshold"
        elif margin < self._config.uncertain_margin:
            diagnostics["reason"] = "top-1 and top-2 are too close to separate"
        else:
            return Prediction(
                modality=self.modality,
                model_name=self.model_name,
                model_version=self.model_version,
                label=top.label,
                confidence=top.confidence,
                is_uncertain=False,
                species_id=top.species_id,
                scientific_name=top.scientific_name,
                top_k=tuple(candidates),
                diagnostics=diagnostics,
                latency_ms=latency_ms,
            )

        return uncertain(
            self.modality,
            self.model_name,
            self.model_version,
            confidence=top.confidence,
            top_k=tuple(candidates),
            diagnostics=diagnostics,
            latency_ms=latency_ms,
        )

    def predict_from_features(self, features: AudioFeatures) -> Prediction:
        """Classify pre-computed features (used by the evaluation harness)."""
        started = time.perf_counter()
        candidates = list(self._backend.classify(features, top_k=self._config.top_k))
        latency_ms = int((time.perf_counter() - started) * 1000)
        if not candidates:
            return uncertain(self.modality, self.model_name, self.model_version,
                             latency_ms=latency_ms)
        top = candidates[0]
        runner_up = candidates[1].confidence if len(candidates) > 1 else 0.0
        if (
            top.confidence < self._config.min_confidence
            or (top.confidence - runner_up) < self._config.uncertain_margin
        ):
            return uncertain(
                self.modality,
                self.model_name,
                self.model_version,
                confidence=top.confidence,
                top_k=tuple(candidates),
                latency_ms=latency_ms,
            )
        return Prediction(
            modality=self.modality,
            model_name=self.model_name,
            model_version=self.model_version,
            label=top.label,
            confidence=top.confidence,
            is_uncertain=False,
            species_id=top.species_id,
            scientific_name=top.scientific_name,
            top_k=tuple(candidates),
            latency_ms=latency_ms,
        )


def build_audio_pipeline(
    references: list[SpeciesReference], config: AIConfig | None = None
) -> AudioPipeline:
    """Choose a backend according to configuration and what is installed."""
    config = config or get_config()
    requested = (config.audio_backend or "auto").lower()

    if requested in {"auto", "torch"} and config.audio_weights:
        if torch_available():
            try:
                backend = TorchAudioBackend(
                    references, config.audio_weights, n_mels=config.n_mels
                )
                logger.info("audio backend: torch (%s)", config.audio_weights)
                return AudioPipeline(backend, config)
            except Exception:  # pragma: no cover - fall back rather than fail
                logger.exception("could not load the trained audio backend; using baseline")
        elif requested == "torch":
            logger.warning("AI_AUDIO_BACKEND=torch but PyTorch is not installed")

    audible = [r for r in references if r.is_audible]
    logger.info("audio backend: baseline (%d species with acoustic signatures)", len(audible))
    return AudioPipeline(
        BaselineAudioClassifier(references, temperature=config.audio_temperature), config
    )
