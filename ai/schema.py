"""Value types shared by every AI pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

UNCERTAIN_LABEL = "UNCERTAIN"


@dataclass(frozen=True)
class SpeciesReference:
    """A species as the AI engine sees it.

    Built from the platform's species table.  ``visual_traits`` and
    ``acoustic_signature`` are the reference descriptors the baseline backends
    match against; trained backends ignore them and use their own class index.
    """

    species_id: int | None
    label: str
    scientific_name: str | None = None
    category: str = "OTHER"
    visual_traits: dict[str, Any] = field(default_factory=dict)
    acoustic_signature: dict[str, Any] = field(default_factory=dict)

    @property
    def is_audible(self) -> bool:
        """Only species with a reference acoustic signature can be matched by ear."""
        return bool(self.acoustic_signature)

    @property
    def is_visual(self) -> bool:
        return bool(self.visual_traits)


@dataclass(frozen=True)
class Candidate:
    species_id: int | None
    label: str
    confidence: float
    scientific_name: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "species_id": self.species_id,
            "label": self.label,
            "scientific_name": self.scientific_name,
            "confidence": round(float(self.confidence), 6),
        }


@dataclass(frozen=True)
class Detection:
    """A detected object in normalised ``[x, y, w, h]`` image coordinates."""

    bbox: tuple[float, float, float, float]
    score: float
    label: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "bbox": [round(float(v), 6) for v in self.bbox],
            "score": round(float(self.score), 6),
            "label": self.label,
        }


@dataclass(frozen=True)
class Prediction:
    """The single result type every pipeline returns."""

    modality: str
    model_name: str
    model_version: str
    label: str
    confidence: float
    is_uncertain: bool
    species_id: int | None = None
    scientific_name: str | None = None
    top_k: tuple[Candidate, ...] = ()
    detections: tuple[Detection, ...] = ()
    diagnostics: dict[str, Any] = field(default_factory=dict)
    latency_ms: int | None = None

    @property
    def requires_expert_verification(self) -> bool:
        """Always true — a model output is an AI-assisted identification only."""
        return True

    def as_dict(self) -> dict[str, Any]:
        return {
            "modality": self.modality,
            "model_name": self.model_name,
            "model_version": self.model_version,
            "predicted_label": self.label,
            "confidence": round(float(self.confidence), 6),
            "is_uncertain": self.is_uncertain,
            "species_id": self.species_id,
            "scientific_name": self.scientific_name,
            "requires_expert_verification": True,
            "top_k": [c.as_dict() for c in self.top_k],
            "detections": [d.as_dict() for d in self.detections],
            "diagnostics": self.diagnostics,
            "latency_ms": self.latency_ms,
        }


def uncertain(
    modality: str,
    model_name: str,
    model_version: str,
    *,
    confidence: float = 0.0,
    top_k: tuple[Candidate, ...] = (),
    detections: tuple[Detection, ...] = (),
    diagnostics: dict[str, Any] | None = None,
    latency_ms: int | None = None,
) -> Prediction:
    """Build the explicit 'the model declines to identify this' result."""
    return Prediction(
        modality=modality,
        model_name=model_name,
        model_version=model_version,
        label=UNCERTAIN_LABEL,
        confidence=confidence,
        is_uncertain=True,
        top_k=top_k,
        detections=detections,
        diagnostics=diagnostics or {},
        latency_ms=latency_ms,
    )
