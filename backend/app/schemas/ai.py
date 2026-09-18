"""AI inference schemas.

An identification produced by a model is always labelled as *AI-assisted*: the
response carries ``is_uncertain``, the confidence, the model version and the
top-k alternatives, and ``requires_expert_verification`` is true until a
qualified expert has reviewed it.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.models.enums import Modality
from app.schemas.common import ORMModel
from app.schemas.species import SpeciesSummary

UNCERTAIN_LABEL = "UNCERTAIN"


class PredictionCandidate(BaseModel):
    species_id: int | None = None
    label: str
    scientific_name: str | None = None
    confidence: float = Field(ge=0, le=1)


class Detection(BaseModel):
    """One vision detection box in normalised ``[x, y, w, h]`` coordinates."""

    bbox: list[float] = Field(min_length=4, max_length=4)
    score: float = Field(ge=0, le=1)
    label: str | None = None


class PredictionResult(BaseModel):
    modality: Modality
    model_name: str
    model_version: str
    #: ``UNCERTAIN`` when the model declines to commit to a species.
    predicted_label: str
    predicted_species: SpeciesSummary | None = None
    confidence: float = Field(ge=0, le=1)
    is_uncertain: bool
    requires_expert_verification: bool = True
    identification_basis: str = Field(
        default="AI-assisted identification — not confirmed taxonomy",
        description="Wording the UI must show beside any model output",
    )
    top_k: list[PredictionCandidate] = Field(default_factory=list)
    detections: list[Detection] = Field(default_factory=list)
    diagnostics: dict[str, Any] | None = None
    latency_ms: int | None = None


class AIPredictionRead(ORMModel):
    """A stored prediction.

    Carries the same AI-assisted labelling as a freshly computed
    :class:`PredictionResult`, so a client rendering a model output never has to
    know which of the two shapes it received in order to caption it correctly.
    """

    id: int
    observation_id: int | None = None
    modality: Modality
    model_name: str
    model_version: str
    predicted_label: str
    predicted_species: SpeciesSummary | None = None
    confidence: float
    is_uncertain: bool
    requires_expert_verification: bool = True
    identification_basis: str = (
        "AI-assisted identification — not confirmed taxonomy"
    )
    top_k: list[dict[str, Any]] | None = None
    detections: list[dict[str, Any]] | None = None
    diagnostics: dict[str, Any] | None = None
    latency_ms: int | None = None
    created_at: datetime


class FusionRequest(BaseModel):
    """Combine an image prediction with an audio prediction (and context)."""

    image: PredictionResult | None = None
    audio: PredictionResult | None = None
    #: Optional contextual priors: hour of day, zone id, season, habitat.
    context: dict[str, Any] | None = None
    image_weight: float = Field(default=0.6, ge=0, le=1)
    audio_weight: float = Field(default=0.4, ge=0, le=1)


class ModelInfo(BaseModel):
    modality: Modality
    name: str
    version: str
    backend: str
    class_count: int
    min_confidence: float
    uncertain_margin: float
    notes: str | None = None


class AIEngineStatus(BaseModel):
    vision: ModelInfo
    audio: ModelInfo
    anomaly_methods: list[str]
    fusion_available: bool
