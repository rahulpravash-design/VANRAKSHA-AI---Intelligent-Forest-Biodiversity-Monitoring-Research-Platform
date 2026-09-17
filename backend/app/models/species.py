"""The biodiversity knowledge base."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, Boolean, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin
from app.models.enums import (
    THREATENED_STATUSES,
    ConservationStatus,
    SpeciesCategory,
    sa_enum,
)

if TYPE_CHECKING:  # pragma: no cover
    from app.models.observation import Observation


class Species(Base, TimestampMixin):
    __tablename__ = "species"
    __table_args__ = (
        Index("ix_species_category_common_name", "category", "common_name"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    common_name: Mapped[str] = mapped_column(String(160), index=True, nullable=False)
    scientific_name: Mapped[str] = mapped_column(
        String(160), unique=True, index=True, nullable=False
    )
    category: Mapped[SpeciesCategory] = mapped_column(
        sa_enum(SpeciesCategory, 20), nullable=False
    )
    family: Mapped[str | None] = mapped_column(String(120), index=True)
    genus: Mapped[str | None] = mapped_column(String(120))
    description: Mapped[str | None] = mapped_column(Text)
    habitat: Mapped[str | None] = mapped_column(Text)
    conservation_status: Mapped[ConservationStatus] = mapped_column(
        sa_enum(ConservationStatus, 4),
        default=ConservationStatus.NOT_EVALUATED,
        nullable=False,
    )
    #: When true, coordinates are generalised for users without precise-location
    #: rights regardless of the IUCN status (e.g. locally poached species).
    is_location_sensitive: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    image_url: Mapped[str | None] = mapped_column(String(500))
    reference_url: Mapped[str | None] = mapped_column(String(500))

    #: Reference traits consumed by the dependency-free vision baseline.
    visual_traits: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    #: Reference acoustic signature consumed by the audio baseline
    #: (peak frequency band in Hz, pulse rate in Hz, typical call duration).
    acoustic_signature: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    #: Free-form research notes (medicinal relevance, phenology, references…).
    research_notes: Mapped[dict[str, Any] | None] = mapped_column(JSON)

    observations: Mapped[list[Observation]] = relationship(
        back_populates="species", foreign_keys="Observation.species_id"
    )

    @property
    def requires_location_generalisation(self) -> bool:
        return self.is_location_sensitive or self.conservation_status in THREATENED_STATUSES

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Species {self.id} {self.scientific_name}>"
