"""Expert verification records — the provenance trail of the research dataset."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, utcnow
from app.models.enums import VerificationDecision, sa_enum

if TYPE_CHECKING:  # pragma: no cover
    from app.models.observation import Observation
    from app.models.species import Species
    from app.models.user import User


class ExpertVerification(Base):
    __tablename__ = "expert_verifications"

    id: Mapped[int] = mapped_column(primary_key=True)
    observation_id: Mapped[int] = mapped_column(
        ForeignKey("observations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    expert_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    decision: Mapped[VerificationDecision] = mapped_column(
        sa_enum(VerificationDecision, 20), nullable=False
    )
    corrected_species_id: Mapped[int | None] = mapped_column(
        ForeignKey("species.id", ondelete="SET NULL")
    )
    #: The species claimed before this review, retained so that AI-versus-expert
    #: and recorder-versus-expert agreement can be measured after the fact.
    previous_species_id: Mapped[int | None] = mapped_column(
        ForeignKey("species.id", ondelete="SET NULL")
    )
    #: What the model predicted at review time, and how confident it was.
    ai_predicted_label: Mapped[str | None] = mapped_column(String(160))
    ai_confidence: Mapped[float | None] = mapped_column(Float)
    comments: Mapped[str | None] = mapped_column(Text)
    verified_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )

    observation: Mapped[Observation] = relationship(back_populates="verifications")
    expert: Mapped[User] = relationship(back_populates="verifications")
    corrected_species: Mapped[Species | None] = relationship(
        foreign_keys=[corrected_species_id]
    )
    previous_species: Mapped[Species | None] = relationship(foreign_keys=[previous_species_id])
