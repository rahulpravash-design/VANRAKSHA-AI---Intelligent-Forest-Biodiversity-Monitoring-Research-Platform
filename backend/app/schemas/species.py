"""Species knowledge-base schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.models.enums import ConservationStatus, SpeciesCategory
from app.schemas.common import ORMModel


class SpeciesBase(BaseModel):
    common_name: str = Field(min_length=2, max_length=160)
    scientific_name: str = Field(min_length=3, max_length=160)
    category: SpeciesCategory
    family: str | None = Field(default=None, max_length=120)
    genus: str | None = Field(default=None, max_length=120)
    description: str | None = None
    habitat: str | None = None
    conservation_status: ConservationStatus = ConservationStatus.NOT_EVALUATED
    is_location_sensitive: bool = False
    image_url: str | None = Field(default=None, max_length=500)
    reference_url: str | None = Field(default=None, max_length=500)
    visual_traits: dict[str, Any] | None = None
    acoustic_signature: dict[str, Any] | None = None
    research_notes: dict[str, Any] | None = None


class SpeciesCreate(SpeciesBase):
    pass


class SpeciesUpdate(BaseModel):
    common_name: str | None = Field(default=None, min_length=2, max_length=160)
    scientific_name: str | None = Field(default=None, min_length=3, max_length=160)
    category: SpeciesCategory | None = None
    family: str | None = Field(default=None, max_length=120)
    genus: str | None = Field(default=None, max_length=120)
    description: str | None = None
    habitat: str | None = None
    conservation_status: ConservationStatus | None = None
    is_location_sensitive: bool | None = None
    image_url: str | None = Field(default=None, max_length=500)
    reference_url: str | None = Field(default=None, max_length=500)
    visual_traits: dict[str, Any] | None = None
    acoustic_signature: dict[str, Any] | None = None
    research_notes: dict[str, Any] | None = None


class SpeciesSummary(ORMModel):
    """Compact form embedded in observation and prediction payloads."""

    id: int
    common_name: str
    scientific_name: str
    category: SpeciesCategory
    conservation_status: ConservationStatus


class SpeciesRead(SpeciesSummary):
    family: str | None = None
    genus: str | None = None
    description: str | None = None
    habitat: str | None = None
    is_location_sensitive: bool
    image_url: str | None = None
    reference_url: str | None = None
    visual_traits: dict[str, Any] | None = None
    acoustic_signature: dict[str, Any] | None = None
    research_notes: dict[str, Any] | None = None
    created_at: datetime
    updated_at: datetime


class SpeciesWithStats(SpeciesRead):
    observation_count: int = 0
    verified_observation_count: int = 0
    last_observed_at: datetime | None = None
