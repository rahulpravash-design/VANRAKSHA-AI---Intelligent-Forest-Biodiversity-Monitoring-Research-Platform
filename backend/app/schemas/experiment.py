"""Research experiment schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.models.enums import ExperimentStatus
from app.schemas.common import ORMModel

VARIANTS = ("image_only", "audio_only", "image_audio", "image_audio_context")


class ExperimentCreate(BaseModel):
    name: str = Field(min_length=4, max_length=200)
    research_question: str = Field(min_length=10)
    hypothesis: str | None = None
    config: dict[str, Any] | None = None


class ExperimentRunRead(ORMModel):
    id: int
    variant: str
    metrics: dict[str, Any] | None = None
    per_class_metrics: dict[str, Any] | None = None
    confusion_matrix: dict[str, Any] | None = None
    sample_count: int | None = None
    random_seed: int | None = None
    notes: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None


class ExperimentRead(ORMModel):
    id: int
    name: str
    research_question: str
    hypothesis: str | None = None
    status: ExperimentStatus
    config: dict[str, Any] | None = None
    created_by_id: int | None = None
    created_at: datetime
    runs: list[ExperimentRunRead] = Field(default_factory=list)


class ExperimentExecuteRequest(BaseModel):
    """Run the modality comparison for an experiment."""

    variants: list[str] = Field(default_factory=lambda: list(VARIANTS))
    sample_count: int = Field(default=240, ge=40, le=5000)
    random_seed: int = Field(default=20260917, ge=0)
    #: ``synthetic`` uses the seeded reference generator so results are
    #: reproducible anywhere; ``verified`` uses expert-verified observations.
    dataset: str = Field(default="synthetic", pattern="^(synthetic|verified)$")


class VariantComparison(BaseModel):
    variant: str
    accuracy: float
    macro_precision: float
    macro_recall: float
    macro_f1: float
    mean_average_precision: float
    expected_calibration_error: float
    uncertain_share: float
    mean_latency_ms: float


class ExperimentReport(BaseModel):
    experiment_id: int
    name: str
    research_question: str
    dataset: str
    sample_count: int
    random_seed: int
    comparisons: list[VariantComparison]
    best_variant: str
    #: Difference in macro-F1 between the best fused and best single modality.
    fusion_gain_f1: float
    conclusion: str
    caveat: str = (
        "Multimodal fusion is compared against single-modality baselines on the same "
        "held-out split; a gain here does not transfer automatically to field data."
    )
