"""Observation schemas, including the location-privacy fields."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator

from app.models.enums import ObservationType, VerificationStatus
from app.schemas.ai import AIPredictionRead
from app.schemas.common import ORMModel
from app.schemas.species import SpeciesSummary
from app.schemas.user import UserPublic


class ObservationBase(BaseModel):
    species_id: int | None = None
    zone_id: int | None = None
    observation_type: ObservationType = ObservationType.IMAGE
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    location_accuracy_m: float | None = Field(default=None, ge=0, le=100_000)
    elevation_m: float | None = Field(default=None, ge=-500, le=9000)
    observed_at: datetime
    notes: str | None = Field(default=None, max_length=4000)
    individual_count: int | None = Field(default=None, ge=0, le=100_000)
    conditions: dict[str, Any] | None = None

    @field_validator("observed_at")
    @classmethod
    def _not_in_future(cls, value: datetime) -> datetime:
        from datetime import UTC, timedelta

        reference = value if value.tzinfo else value.replace(tzinfo=UTC)
        if reference > datetime.now(UTC) + timedelta(minutes=5):
            raise ValueError("observed_at cannot be in the future")
        return value


class ObservationCreate(ObservationBase):
    """JSON creation (media can be attached afterwards via /media)."""


class ObservationUpdate(BaseModel):
    species_id: int | None = None
    zone_id: int | None = None
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    location_accuracy_m: float | None = Field(default=None, ge=0, le=100_000)
    elevation_m: float | None = Field(default=None, ge=-500, le=9000)
    observed_at: datetime | None = None
    notes: str | None = Field(default=None, max_length=4000)
    individual_count: int | None = Field(default=None, ge=0, le=100_000)
    conditions: dict[str, Any] | None = None


class MediaAssetRead(ORMModel):
    id: int
    kind: str
    public_url: str
    mime_type: str
    size_bytes: int
    checksum: str
    width: int | None = None
    height: int | None = None
    duration_seconds: float | None = None
    sample_rate: int | None = None
    original_filename: str | None = None
    created_at: datetime


class ObservationRead(ORMModel):
    id: int
    researcher_id: int
    observation_type: ObservationType
    species: SpeciesSummary | None = None
    zone_id: int | None = None
    zone_name: str | None = None
    image_url: str | None = None
    audio_url: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    location_accuracy_m: float | None = None
    elevation_m: float | None = None
    #: True when the coordinates above were coarsened to protect a sensitive
    #: species from being located by an unauthorised viewer.
    location_generalised: bool = False
    observed_at: datetime
    notes: str | None = None
    individual_count: int | None = None
    conditions: dict[str, Any] | None = None
    ai_prediction: str | None = None
    ai_confidence: float | None = None
    ai_model_version: str | None = None
    ai_predicted_species: SpeciesSummary | None = None
    verification_status: VerificationStatus
    verified_species: SpeciesSummary | None = None
    verified_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class ObservationDetail(ObservationRead):
    researcher: UserPublic | None = None
    media: list[MediaAssetRead] = Field(default_factory=list)
    predictions: list[AIPredictionRead] = Field(default_factory=list)
    final_species: SpeciesSummary | None = None


class ObservationFilter(BaseModel):
    species_id: int | None = None
    zone_id: int | None = None
    researcher_id: int | None = None
    observation_type: ObservationType | None = None
    verification_status: VerificationStatus | None = None
    category: str | None = None
    observed_from: datetime | None = None
    observed_to: datetime | None = None
    has_media: bool | None = None
    search: str | None = None
