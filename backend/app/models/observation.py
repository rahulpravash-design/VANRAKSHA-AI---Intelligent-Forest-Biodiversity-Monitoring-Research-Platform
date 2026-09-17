"""Observations — the central data-collection record — and their media."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin
from app.models.enums import MediaKind, ObservationType, VerificationStatus, sa_enum

if TYPE_CHECKING:  # pragma: no cover
    from app.models.ai import AIPrediction
    from app.models.species import Species
    from app.models.user import User
    from app.models.verification import ExpertVerification
    from app.models.zone import ForestZone


class Observation(Base, TimestampMixin):
    __tablename__ = "observations"
    __table_args__ = (
        CheckConstraint(
            "latitude IS NULL OR (latitude >= -90 AND latitude <= 90)",
            name="latitude_range",
        ),
        CheckConstraint(
            "longitude IS NULL OR (longitude >= -180 AND longitude <= 180)",
            name="longitude_range",
        ),
        CheckConstraint(
            "ai_confidence IS NULL OR (ai_confidence >= 0 AND ai_confidence <= 1)",
            name="ai_confidence_range",
        ),
        Index("ix_observations_observed_at_zone", "observed_at", "zone_id"),
        Index("ix_observations_lat_lon", "latitude", "longitude"),
        Index("ix_observations_status_species", "verification_status", "species_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    researcher_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    #: The species the recorder reports. AI-assisted identifications live in
    #: ``ai_prediction`` / :class:`app.models.ai.AIPrediction` until an expert
    #: confirms them, so this column is never set from a model output alone.
    species_id: Mapped[int | None] = mapped_column(
        ForeignKey("species.id", ondelete="SET NULL"), index=True
    )
    zone_id: Mapped[int | None] = mapped_column(
        ForeignKey("forest_zones.id", ondelete="SET NULL"), index=True
    )

    observation_type: Mapped[ObservationType] = mapped_column(
        sa_enum(ObservationType, 20),
        default=ObservationType.IMAGE,
        nullable=False,
    )

    image_url: Mapped[str | None] = mapped_column(String(500))
    audio_url: Mapped[str | None] = mapped_column(String(500))

    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    location_accuracy_m: Mapped[float | None] = mapped_column(Float)
    elevation_m: Mapped[float | None] = mapped_column(Float)

    observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), index=True, nullable=False
    )
    notes: Mapped[str | None] = mapped_column(Text)
    individual_count: Mapped[int | None] = mapped_column(Integer)
    #: Field conditions recorded alongside the observation (weather, canopy…).
    conditions: Mapped[dict[str, Any] | None] = mapped_column(JSON)

    # ------------------------------------------------ AI-assisted identification
    ai_prediction: Mapped[str | None] = mapped_column(String(160))
    ai_confidence: Mapped[float | None] = mapped_column(Float)
    ai_model_version: Mapped[str | None] = mapped_column(String(80))
    ai_predicted_species_id: Mapped[int | None] = mapped_column(
        ForeignKey("species.id", ondelete="SET NULL")
    )

    # ------------------------------------------------------- expert verification
    verification_status: Mapped[VerificationStatus] = mapped_column(
        sa_enum(VerificationStatus, 20),
        default=VerificationStatus.PENDING,
        nullable=False,
        index=True,
    )
    verified_species_id: Mapped[int | None] = mapped_column(
        ForeignKey("species.id", ondelete="SET NULL")
    )
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # ------------------------------------------------------------ relationships
    researcher: Mapped[User] = relationship(
        back_populates="observations", foreign_keys=[researcher_id]
    )
    species: Mapped[Species | None] = relationship(
        back_populates="observations", foreign_keys=[species_id]
    )
    ai_predicted_species: Mapped[Species | None] = relationship(
        foreign_keys=[ai_predicted_species_id]
    )
    verified_species: Mapped[Species | None] = relationship(foreign_keys=[verified_species_id])
    zone: Mapped[ForestZone | None] = relationship(back_populates="observations")
    media: Mapped[list[MediaAsset]] = relationship(
        back_populates="observation", cascade="all, delete-orphan"
    )
    predictions: Mapped[list[AIPrediction]] = relationship(
        back_populates="observation", cascade="all, delete-orphan"
    )
    verifications: Mapped[list[ExpertVerification]] = relationship(
        back_populates="observation", cascade="all, delete-orphan"
    )

    # ------------------------------------------------------------------ helpers
    @property
    def final_species_id(self) -> int | None:
        """The species to use for analysis: expert-verified first, else reported."""
        if self.verification_status == VerificationStatus.CORRECTED:
            return self.verified_species_id
        if self.verification_status == VerificationStatus.CONFIRMED:
            return self.verified_species_id or self.species_id
        if self.verification_status == VerificationStatus.REJECTED:
            return None
        return self.species_id

    @property
    def is_expert_verified(self) -> bool:
        return self.verification_status in {
            VerificationStatus.CONFIRMED,
            VerificationStatus.CORRECTED,
        }

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Observation {self.id} type={self.observation_type} at={self.observed_at}>"


class MediaAsset(Base, TimestampMixin):
    """A stored image / audio / spectrogram file belonging to an observation."""

    __tablename__ = "media_assets"

    id: Mapped[int] = mapped_column(primary_key=True)
    observation_id: Mapped[int] = mapped_column(
        ForeignKey("observations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    kind: Mapped[MediaKind] = mapped_column(
        sa_enum(MediaKind, 20), nullable=False
    )
    storage_key: Mapped[str] = mapped_column(String(500), nullable=False)
    public_url: Mapped[str] = mapped_column(String(600), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(80), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    #: SHA-256 of the file, used for de-duplication and dataset provenance.
    checksum: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)
    duration_seconds: Mapped[float | None] = mapped_column(Float)
    sample_rate: Mapped[int | None] = mapped_column(Integer)
    original_filename: Mapped[str | None] = mapped_column(String(255))

    observation: Mapped[Observation] = relationship(back_populates="media")
