"""The dependency-free vision classifier.

This is a *nearest-prototype classifier in an interpretable descriptor space*.
For every species the platform knows about, its ``visual_traits`` record is
converted into a synthetic descriptor (:func:`prototype_from_traits`) that lives
in the same 44-dimensional space as the descriptor computed from a photograph
(:func:`ai.preprocessing.image.image_descriptor`).  Classification is then a
block-weighted distance plus a softmax.

Why keep this rather than require trained weights?

* the whole platform — API, dashboard, tests, demos — stays runnable and
  reproducible on any machine, with no model download;
* it produces genuinely informative rankings for visually distinctive species
  (a dark bovid in dense canopy versus a pale wader on water), which is enough
  to exercise and evaluate the verification workflow end to end;
* it is transparent: :meth:`BaselineVisionClassifier.explain` reports which
  descriptor blocks drove a decision.

Its limits are real and documented in ``docs/research/ai-methodology.md``: it
cannot separate congeners that differ only in fine markings, and it is sensitive
to strong backlighting.  Those cases are what the trained backend is for.
"""

from __future__ import annotations

import numpy as np

from ai.calibration import standardised_softmax
from ai.preprocessing.image import (
    BLOCKS,
    DESCRIPTOR_LENGTH,
    HUE_BINS,
    ORIENTATION_BINS,
    SAT_BINS,
    VAL_BINS,
    image_descriptor,
)
from ai.schema import Candidate, Detection, SpeciesReference
from ai.vision.detect import crop_to_detection, saliency_detections

#: Documentation of the ``species.visual_traits`` JSON contract.
TRAIT_SCHEMA: dict[str, str] = {
    "dominant_hues": "list[float] 0..1 — hue turns of the subject's main colours",
    "saturation": "float 0..1 — typical colour purity of the subject",
    "brightness": "float 0..1 — typical subject lightness",
    "pattern": "uniform | mottled | spotted | striped | feathered | leafy | barred",
    "edge_density": "float 0..1 — how much fine structure the subject shows",
    "body_aspect": "float — subject width / height (a bovid ~1.8, a tree ~0.5)",
    "subject_fill": "float 0..1 — share of the frame the subject usually occupies",
    "scene": "canopy | understory | grassland | wetland | bark | rock | sky",
}

#: How much the subject crop (versus the whole frame) drives the descriptor.
SUBJECT_DESCRIPTOR_WEIGHT = 0.85

#: Relative importance of each descriptor block in the distance metric.
BLOCK_WEIGHTS: dict[str, float] = {
    "hue": 1.15,
    "saturation": 0.60,
    "value": 0.50,
    "orientation": 0.80,
    "texture": 1.00,
    "region": 0.70,
    "vegetation": 0.95,
}

#: Orientation-histogram signatures for each coat/leaf pattern.
_PATTERN_ORIENTATION: dict[str, list[float]] = {
    "uniform": [1, 1, 1, 1, 1, 1, 1, 1],
    "mottled": [1.2, 1.0, 1.1, 1.0, 1.2, 1.0, 1.1, 1.0],
    "spotted": [1.3, 0.9, 1.1, 0.9, 1.3, 0.9, 1.1, 0.9],
    "striped": [2.6, 0.5, 0.4, 0.5, 2.6, 0.5, 0.4, 0.5],
    "barred": [0.5, 0.4, 2.6, 0.4, 0.5, 0.4, 2.6, 0.4],
    "feathered": [1.4, 1.1, 0.8, 1.1, 1.4, 1.1, 0.8, 1.1],
    "leafy": [1.0, 1.6, 1.0, 1.6, 1.0, 1.6, 1.0, 1.6],
}

#: ``(edge_contrast, roughness, entropy)`` prior per pattern.
_PATTERN_TEXTURE: dict[str, tuple[float, float, float]] = {
    "uniform": (0.18, 0.14, 0.62),
    "mottled": (0.34, 0.30, 0.78),
    "spotted": (0.42, 0.34, 0.80),
    "striped": (0.52, 0.40, 0.74),
    "barred": (0.50, 0.38, 0.74),
    "feathered": (0.38, 0.32, 0.76),
    "leafy": (0.46, 0.42, 0.82),
}

#: ``(greenness, brownness, sky_water, bark_gray)`` prior per scene.
_SCENE_VEGETATION: dict[str, tuple[float, float, float, float]] = {
    "canopy": (0.66, 0.14, 0.08, 0.10),
    "understory": (0.48, 0.30, 0.03, 0.16),
    "grassland": (0.40, 0.42, 0.10, 0.08),
    "wetland": (0.30, 0.16, 0.42, 0.08),
    "bark": (0.22, 0.34, 0.03, 0.44),
    "rock": (0.16, 0.24, 0.10, 0.52),
    "sky": (0.14, 0.06, 0.62, 0.14),
}


def _circular_bump(centres: list[float], bins: int, sigma: float = 0.085) -> np.ndarray:
    """A normalised histogram with wrapped Gaussian bumps at ``centres``."""
    positions = (np.arange(bins) + 0.5) / bins
    histogram = np.zeros(bins, dtype=np.float64)
    for centre in centres or [0.3]:
        delta = np.abs(positions - (float(centre) % 1.0))
        delta = np.minimum(delta, 1.0 - delta)  # hue is circular
        histogram += np.exp(-0.5 * (delta / sigma) ** 2)
    total = histogram.sum()
    return histogram / total if total > 0 else np.full(bins, 1.0 / bins)


def _linear_bump(centre: float, bins: int, sigma: float = 0.16) -> np.ndarray:
    positions = (np.arange(bins) + 0.5) / bins
    histogram = np.exp(-0.5 * ((positions - float(centre)) / sigma) ** 2)
    total = histogram.sum()
    return histogram / total if total > 0 else np.full(bins, 1.0 / bins)


def prototype_from_traits(traits: dict) -> np.ndarray:
    """Convert a species' ``visual_traits`` record into a reference descriptor.

    Unspecified traits fall back to neutral values, so a partially described
    species still participates in ranking — it simply competes less sharply.
    """
    traits = traits or {}
    hues = traits.get("dominant_hues") or [0.28]
    if isinstance(hues, (int, float)):
        hues = [float(hues)]
    pattern = str(traits.get("pattern", "uniform")).lower()
    scene = str(traits.get("scene", "understory")).lower()

    hue_hist = _circular_bump([float(h) for h in hues], HUE_BINS)
    sat_hist = _linear_bump(float(traits.get("saturation", 0.35)), SAT_BINS)
    val_hist = _linear_bump(float(traits.get("brightness", 0.45)), VAL_BINS)

    orientation = np.array(
        _PATTERN_ORIENTATION.get(pattern, _PATTERN_ORIENTATION["uniform"]), dtype=np.float64
    )
    orientation = orientation[:ORIENTATION_BINS] / orientation[:ORIENTATION_BINS].sum()

    edge_density = float(np.clip(traits.get("edge_density", 0.3), 0.0, 1.0))
    contrast, roughness, entropy = _PATTERN_TEXTURE.get(pattern, _PATTERN_TEXTURE["uniform"])
    texture = np.array([edge_density, contrast, roughness, entropy])

    aspect = float(traits.get("body_aspect", 1.2))
    fill = float(np.clip(traits.get("subject_fill", 0.3), 0.0, 1.0))
    region = np.array([min(aspect / 3.0, 1.0), min(fill * 2.0, 1.0), 0.22, 0.42])

    vegetation = np.array(_SCENE_VEGETATION.get(scene, _SCENE_VEGETATION["understory"]))

    prototype = np.concatenate(
        [hue_hist, sat_hist, val_hist, orientation, texture, region, vegetation]
    ).astype(np.float32)
    assert prototype.shape[0] == DESCRIPTOR_LENGTH, prototype.shape
    return np.clip(prototype, 0.0, 1.0)


def discriminative_scale(prototypes: np.ndarray) -> np.ndarray:
    """Per-dimension weights learned from the reference set itself.

    A descriptor dimension on which every species agrees carries no information
    about *which* species this is, while a dimension that varies widely between
    species carries a lot.  Scaling each dimension by the inverse of its
    across-species standard deviation — a diagonal Mahalanobis metric — makes the
    distance reflect that, instead of letting 44 equally-weighted dimensions bury
    the few that actually separate the catalogue.
    """
    if prototypes.shape[0] < 2:
        return np.ones(prototypes.shape[1], dtype=np.float64)
    spread = prototypes.std(axis=0)
    # A floor keeps a near-constant dimension from exploding into the metric.
    floor = max(float(np.median(spread)) * 0.25, 1e-3)
    scale = 1.0 / np.maximum(spread, floor)
    return scale / scale.mean()


def block_distance(
    descriptor: np.ndarray, prototype: np.ndarray, scale: np.ndarray | None = None
) -> tuple[float, dict[str, float]]:
    """Block-weighted RMS distance, plus the per-block contributions."""
    difference = (descriptor - prototype).astype(np.float64)
    if scale is not None:
        difference = difference * scale
    contributions: dict[str, float] = {}
    total = 0.0
    weight_sum = 0.0
    for name, span in BLOCKS.items():
        weight = BLOCK_WEIGHTS.get(name, 1.0)
        block_error = float(np.sqrt(np.mean(difference[span] ** 2)))
        contributions[name] = round(block_error, 6)
        total += weight * block_error**2
        weight_sum += weight
    return float(np.sqrt(total / max(weight_sum, 1e-9))), contributions


def softmax_from_distances(distances: np.ndarray, temperature: float) -> np.ndarray:
    """Turn descriptor distances into a probability-like score vector.

    Delegates to :func:`ai.calibration.standardised_softmax`, so the confidence
    reflects how far the best match stands out from its rivals rather than the
    absolute distance scale — see that module for why that matters here.
    """
    return standardised_softmax(distances, temperature, higher_is_better=False)


class BaselineVisionClassifier:
    """Nearest-prototype species classifier over image descriptors."""

    backend = "baseline"
    name = "vanraksha-vision-baseline"
    version = "1.0.0"

    def __init__(
        self,
        references: list[SpeciesReference],
        *,
        temperature: float = 0.55,
        image_size: int = 224,
    ) -> None:
        self._references = [r for r in references if r.is_visual] or list(references)
        self._temperature = temperature
        self._image_size = image_size
        if self._references:
            self._prototypes = np.stack(
                [prototype_from_traits(r.visual_traits) for r in self._references]
            )
        else:
            self._prototypes = np.zeros((0, DESCRIPTOR_LENGTH), dtype=np.float32)
        self._scale = discriminative_scale(self._prototypes)

    # ------------------------------------------------------------ properties
    @property
    def classes(self) -> list[SpeciesReference]:
        return list(self._references)

    # -------------------------------------------------------------- inference
    def detect(self, image: np.ndarray) -> list[Detection]:
        return saliency_detections(image)

    def _rank(self, descriptor: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        distances = np.array(
            [
                block_distance(descriptor, prototype, self._scale)[0]
                for prototype in self._prototypes
            ]
        )
        return distances, softmax_from_distances(distances, self._temperature)

    def classify(self, image: np.ndarray, *, top_k: int = 5) -> list[Candidate]:
        if not self._references:
            return []
        descriptor = self._descriptor_for(image)
        _, scores = self._rank(descriptor)
        order = np.argsort(scores)[::-1][:top_k]
        return [
            Candidate(
                species_id=self._references[int(i)].species_id,
                label=self._references[int(i)].label,
                scientific_name=self._references[int(i)].scientific_name,
                confidence=float(scores[int(i)]),
            )
            for i in order
        ]

    def _descriptor_for(self, image: np.ndarray) -> np.ndarray:
        """Descriptor of the most salient subject, falling back to the full frame.

        The subject crop dominates and the whole frame contributes the remainder:
        habitat is real but weak evidence, and on the reference benchmark a
        subject-dominant descriptor ranks clearly better than a balanced one
        (top-3 0.48 versus 0.44 over 32 classes).
        """
        detections = saliency_detections(image, max_detections=1)
        if detections:
            cropped = crop_to_detection(image, detections[0])
            if cropped.shape[0] >= 16 and cropped.shape[1] >= 16:
                subject = SUBJECT_DESCRIPTOR_WEIGHT
                return subject * image_descriptor(cropped) + (1.0 - subject) * image_descriptor(
                    image
                )
        return image_descriptor(image)

    # -------------------------------------------------------- explainability
    def explain(self, image: np.ndarray) -> dict:
        """Report why the top candidate won — per-block distance contributions."""
        if not self._references:
            return {"reason": "no reference species available"}
        descriptor = self._descriptor_for(image)
        distances, scores = self._rank(descriptor)
        best = int(np.argmax(scores))
        _, contributions = block_distance(descriptor, self._prototypes[best], self._scale)
        ranked_blocks = sorted(contributions.items(), key=lambda kv: kv[1])
        return {
            "backend": self.backend,
            "top_label": self._references[best].label,
            "distance": round(float(distances[best]), 6),
            "block_contributions": contributions,
            "best_matching_blocks": [name for name, _ in ranked_blocks[:3]],
            "weakest_blocks": [name for name, _ in ranked_blocks[-2:]],
        }
