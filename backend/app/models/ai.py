"""Stored AI inference results.

Predictions are kept separate from :class:`~app.models.observation.Observation`
so that a single observation can carry an image prediction, an audio prediction
and a fused prediction, and so that re-running a newer model version never
destroys the earlier record — which is what makes model-versus-expert analysis
possible later.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, NullableJSON, TimestampMixin
from app.models.enums import Modality, sa_enum

if TYPE_CHECKING:  # pragma: no cover
    from app.models.observation import Observation
    from app.models.species import Species


class AIPrediction(Base, TimestampMixin):
    __tablename__ = "ai_predictions"
    __table_args__ = (
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="confidence_range"),
        Index("ix_ai_predictions_modality_model", "modality", "model_name"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    observation_id: Mapped[int | None] = mapped_column(
        ForeignKey("observations.id", ondelete="CASCADE"), index=True
    )
    modality: Mapped[Modality] = mapped_column(
        sa_enum(Modality, 12), nullable=False
    )
    model_name: Mapped[str] = mapped_column(String(80), nullable=False)
    model_version: Mapped[str] = mapped_column(String(40), nullable=False)

    predicted_species_id: Mapped[int | None] = mapped_column(
        ForeignKey("species.id", ondelete="SET NULL")
    )
    #: Human-readable label; ``UNCERTAIN`` when the model declines to commit.
    predicted_label: Mapped[str] = mapped_column(String(160), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    #: True when confidence/margin fell below the configured thresholds. The API
    #: never presents such a result as an identification.
    is_uncertain: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    #: ``[{"species_id": 3, "label": "...", "confidence": 0.71}, ...]``
    top_k: Mapped[list[dict[str, Any]] | None] = mapped_column(NullableJSON)
    #: Detection boxes for vision models: ``[{"bbox":[x,y,w,h],"score":0.9}]``
    detections: Mapped[list[dict[str, Any]] | None] = mapped_column(NullableJSON)
    #: Backend-specific diagnostics (features, spectrogram stats, thresholds…).
    diagnostics: Mapped[dict[str, Any] | None] = mapped_column(NullableJSON)
    latency_ms: Mapped[int | None] = mapped_column(Integer)

    observation: Mapped[Observation | None] = relationship(back_populates="predictions")
    predicted_species: Mapped[Species | None] = relationship()

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<AIPrediction {self.id} {self.modality} {self.predicted_label} "
            f"{self.confidence:.2f}>"
        )
