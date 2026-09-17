"""Trained vision backend (Ultralytics YOLO + optional classifier head).

Active only when the ``ultralytics`` package is installed *and* weights are
configured, so importing this module is always safe.  The detector locates
animals; a classification head — either YOLO's own class index or a separate
fine-tuned classifier — maps a crop to a species.

Class names coming out of the weights are mapped onto the platform's species
table by scientific name first, then by common name, so retraining with new
class names does not require a code change.  Unmapped classes are still
returned as labels with ``species_id=None``: the observation records what the
model said, and an expert resolves it.
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np

from ai.schema import Candidate, Detection, SpeciesReference

logger = logging.getLogger(__name__)


def ultralytics_available() -> bool:
    try:  # pragma: no cover - environment dependent
        import ultralytics  # noqa: F401
    except ImportError:
        return False
    return True


class UltralyticsVisionBackend:
    """YOLO-based detector + species classifier."""

    backend = "ultralytics"
    name = "vanraksha-vision-yolo"

    def __init__(
        self,
        references: list[SpeciesReference],
        weights: str,
        *,
        image_size: int = 640,
        detection_score_threshold: float = 0.25,
        max_detections: int = 12,
        device: str | None = None,
    ) -> None:
        if not ultralytics_available():  # pragma: no cover
            raise RuntimeError("ultralytics is not installed")
        weights_path = Path(weights)
        if not weights_path.exists():  # pragma: no cover
            raise FileNotFoundError(f"vision weights not found: {weights_path}")

        from ultralytics import YOLO  # pragma: no cover - optional dependency

        self._model = YOLO(str(weights_path))
        self._references = list(references)
        self._image_size = image_size
        self._threshold = detection_score_threshold
        self._max_detections = max_detections
        self._device = device
        self.version = weights_path.stem
        self._by_name = self._build_name_index(references)

    # ------------------------------------------------------------- utilities
    @staticmethod
    def _normalise(value: str) -> str:
        return "".join(ch for ch in value.lower() if ch.isalnum())

    def _build_name_index(self, references: list[SpeciesReference]) -> dict[str, SpeciesReference]:
        index: dict[str, SpeciesReference] = {}
        for reference in references:
            if reference.scientific_name:
                index[self._normalise(reference.scientific_name)] = reference
            index.setdefault(self._normalise(reference.label), reference)
        return index

    def _resolve(self, class_name: str) -> tuple[int | None, str, str | None]:
        match = self._by_name.get(self._normalise(class_name))
        if match is None:
            return None, class_name, None
        return match.species_id, match.label, match.scientific_name

    @property
    def classes(self) -> list[SpeciesReference]:
        return list(self._references)

    # ------------------------------------------------------------- inference
    def _run(self, image: np.ndarray):  # pragma: no cover - optional dependency
        array = (np.clip(image, 0.0, 1.0) * 255).astype(np.uint8)
        return self._model.predict(
            array,
            imgsz=self._image_size,
            conf=self._threshold,
            device=self._device,
            verbose=False,
        )

    def detect(self, image: np.ndarray) -> list[Detection]:  # pragma: no cover
        height, width = image.shape[:2]
        detections: list[Detection] = []
        for result in self._run(image):
            boxes = getattr(result, "boxes", None)
            if boxes is None:
                continue
            names = getattr(result, "names", {}) or {}
            for box in boxes:
                x1, y1, x2, y2 = (float(v) for v in box.xyxy[0].tolist())
                score = float(box.conf[0])
                class_index = int(box.cls[0])
                detections.append(
                    Detection(
                        bbox=(
                            x1 / width,
                            y1 / height,
                            (x2 - x1) / width,
                            (y2 - y1) / height,
                        ),
                        score=score,
                        label=str(names.get(class_index, class_index)),
                    )
                )
        detections.sort(key=lambda d: d.score, reverse=True)
        return detections[: self._max_detections]

    def classify(self, image: np.ndarray, *, top_k: int = 5) -> list[Candidate]:  # pragma: no cover
        aggregated: dict[str, float] = {}
        for result in self._run(image):
            names = getattr(result, "names", {}) or {}
            probabilities = getattr(result, "probs", None)
            if probabilities is not None:  # classification weights
                values = probabilities.data.tolist()
                for index, score in enumerate(values):
                    label = str(names.get(index, index))
                    aggregated[label] = max(aggregated.get(label, 0.0), float(score))
                continue
            boxes = getattr(result, "boxes", None)
            if boxes is None:
                continue
            for box in boxes:  # detection weights: best box per class wins
                label = str(names.get(int(box.cls[0]), int(box.cls[0])))
                aggregated[label] = max(aggregated.get(label, 0.0), float(box.conf[0]))

        if not aggregated:
            return []
        total = sum(aggregated.values()) or 1.0
        ranked = sorted(aggregated.items(), key=lambda kv: kv[1], reverse=True)[:top_k]
        candidates: list[Candidate] = []
        for label, score in ranked:
            species_id, resolved_label, scientific_name = self._resolve(label)
            candidates.append(
                Candidate(
                    species_id=species_id,
                    label=resolved_label,
                    scientific_name=scientific_name,
                    confidence=float(score / total),
                )
            )
        return candidates
