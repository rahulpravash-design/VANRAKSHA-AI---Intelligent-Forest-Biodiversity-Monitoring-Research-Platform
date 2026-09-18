"""Expert verification schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, model_validator

from app.models.enums import VerificationDecision
from app.schemas.common import ORMModel
from app.schemas.observation import ObservationRead
from app.schemas.species import SpeciesSummary
from app.schemas.user import UserPublic


class VerificationCreate(BaseModel):
    decision: VerificationDecision
    corrected_species_id: int | None = None
    comments: str | None = Field(default=None, max_length=4000)

    @model_validator(mode="after")
    def _correction_needs_species(self):
        if self.decision == VerificationDecision.CORRECT and self.corrected_species_id is None:
            raise ValueError("corrected_species_id is required when decision is CORRECT")
        if self.decision != VerificationDecision.CORRECT and self.corrected_species_id is not None:
            raise ValueError("corrected_species_id is only valid when decision is CORRECT")
        return self


class VerificationRead(ORMModel):
    id: int
    observation_id: int
    expert: UserPublic | None = None
    decision: VerificationDecision
    corrected_species: SpeciesSummary | None = None
    previous_species: SpeciesSummary | None = None
    ai_predicted_label: str | None = None
    ai_confidence: float | None = None
    comments: str | None = None
    verified_at: datetime


class ReviewQueueItem(BaseModel):
    observation: ObservationRead
    ai_predicted_label: str | None = None
    ai_confidence: float | None = None
    reported_species: SpeciesSummary | None = None
    #: Days the item has been waiting — the queue is ordered by this.
    waiting_days: float = 0.0
    has_image: bool = False
    has_audio: bool = False


class AgreementCell(BaseModel):
    ai_label: str
    expert_label: str
    count: int


class VerificationStats(BaseModel):
    """AI-versus-expert agreement over expert-reviewed observations."""

    reviewed_count: int
    confirmed: int
    rejected: int
    corrected: int
    uncertain: int
    #: Share of reviewed observations where the expert confirmed the AI's label.
    ai_agreement_rate: float | None = None
    mean_confidence_when_agreed: float | None = None
    mean_confidence_when_disagreed: float | None = None
    top_confusions: list[AgreementCell] = Field(default_factory=list)
    note: str = (
        "Agreement is computed only over observations an expert has reviewed, so it "
        "reflects review coverage rather than overall model accuracy."
    )
