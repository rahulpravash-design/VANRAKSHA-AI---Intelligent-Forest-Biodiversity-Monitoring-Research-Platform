"""The vision pipeline: validation → detection → classification → gating.

Thresholding lives here rather than in a backend so every backend is treated
identically: a low top-1 score, or a top-1/top-2 gap that is too small, produces
an explicit ``UNCERTAIN`` result instead of a forced species name.
"""

from __future__ import annotations

import logging
import time

import numpy as np

from ai.config import AIConfig, get_config
from ai.preprocessing.image import ImageValidationError, load_image
from ai.schema import Candidate, Detection, Prediction, SpeciesReference, uncertain
from ai.vision.baseline import BaselineVisionClassifier
from ai.vision.ultralytics_backend import UltralyticsVisionBackend, ultralytics_available

logger = logging.getLogger(__name__)


class VisionPipeline:
    """Identify a species from a photograph."""

    modality = "IMAGE"

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
                "Baseline descriptor classifier — install trained weights and set "
                "AI_VISION_WEIGHTS for field-grade accuracy."
                if self.backend_name == "baseline"
                else None
            ),
        }

    # ------------------------------------------------------------- inference
    def predict(self, source: bytes | str | np.ndarray) -> Prediction:
        started = time.perf_counter()
        image = self._as_array(source)

        detections: list[Detection] = []
        try:
            detections = list(self._backend.detect(image))
        except Exception:  # pragma: no cover - a detector failure must not 500
            logger.exception("vision detection failed; continuing with whole-frame classification")

        candidates: list[Candidate] = list(
            self._backend.classify(image, top_k=self._config.top_k)
        )
        latency_ms = int((time.perf_counter() - started) * 1000)

        diagnostics: dict = {
            "backend": self.backend_name,
            "detection_count": len(detections),
            "image_shape": list(image.shape),
        }
        explain = getattr(self._backend, "explain", None)
        if callable(explain):
            try:
                diagnostics["explanation"] = explain(image)
            except Exception:  # pragma: no cover - diagnostics are best-effort
                logger.debug("vision explanation failed", exc_info=True)

        if not candidates:
            diagnostics["reason"] = "no reference species available for this modality"
            return uncertain(
                self.modality,
                self.model_name,
                self.model_version,
                detections=tuple(detections),
                diagnostics=diagnostics,
                latency_ms=latency_ms,
            )

        top = candidates[0]
        runner_up = candidates[1].confidence if len(candidates) > 1 else 0.0
        margin = top.confidence - runner_up
        diagnostics.update(
            {
                "top_confidence": round(top.confidence, 6),
                "margin": round(margin, 6),
                "min_confidence": self._config.min_confidence,
                "uncertain_margin": self._config.uncertain_margin,
            }
        )

        if top.confidence < self._config.min_confidence:
            diagnostics["reason"] = "top-1 confidence below threshold"
            return uncertain(
                self.modality,
                self.model_name,
                self.model_version,
                confidence=top.confidence,
                top_k=tuple(candidates),
                detections=tuple(detections),
                diagnostics=diagnostics,
                latency_ms=latency_ms,
            )
        if margin < self._config.uncertain_margin:
            diagnostics["reason"] = "top-1 and top-2 are too close to separate"
            return uncertain(
                self.modality,
                self.model_name,
                self.model_version,
                confidence=top.confidence,
                top_k=tuple(candidates),
                detections=tuple(detections),
                diagnostics=diagnostics,
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
            detections=tuple(detections),
            diagnostics=diagnostics,
            latency_ms=latency_ms,
        )

    # ------------------------------------------------------------- internals
    def _as_array(self, source: bytes | str | np.ndarray) -> np.ndarray:
        if isinstance(source, np.ndarray):
            if source.ndim != 3 or source.shape[-1] != 3:
                raise ImageValidationError("expected an (H, W, 3) RGB array")
            return np.clip(source.astype(np.float32), 0.0, 1.0)
        return load_image(source, size=self._config.image_size)


def build_vision_pipeline(
    references: list[SpeciesReference], config: AIConfig | None = None
) -> VisionPipeline:
    """Choose a backend according to configuration and what is installed."""
    config = config or get_config()
    requested = (config.vision_backend or "auto").lower()

    if requested in {"auto", "ultralytics"} and config.vision_weights:
        if ultralytics_available():
            try:
                backend = UltralyticsVisionBackend(
                    references,
                    config.vision_weights,
                    image_size=640,
                    detection_score_threshold=config.detection_score_threshold,
                    max_detections=config.max_detections,
                )
                logger.info("vision backend: ultralytics (%s)", config.vision_weights)
                return VisionPipeline(backend, config)
            except Exception:  # pragma: no cover - fall back rather than fail
                logger.exception("could not load the trained vision backend; using baseline")
        elif requested == "ultralytics":
            logger.warning("AI_VISION_BACKEND=ultralytics but the package is not installed")

    logger.info("vision backend: baseline (%d reference species)", len(references))
    return VisionPipeline(
        BaselineVisionClassifier(
            references, temperature=config.score_temperature, image_size=config.image_size
        ),
        config,
    )
