"""Forest-zone and spatial-query schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class ZoneBase(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    code: str = Field(min_length=1, max_length=32)
    description: str | None = None
    habitat_type: str | None = Field(default=None, max_length=120)
    area_hectares: float | None = Field(default=None, ge=0)
    center_latitude: float = Field(ge=-90, le=90)
    center_longitude: float = Field(ge=-180, le=180)
    radius_km: float = Field(default=5.0, gt=0, le=500)
    boundary_geojson: dict[str, Any] | None = None


class ZoneCreate(ZoneBase):
    pass


class ZoneUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=160)
    description: str | None = None
    habitat_type: str | None = Field(default=None, max_length=120)
    area_hectares: float | None = Field(default=None, ge=0)
    center_latitude: float | None = Field(default=None, ge=-90, le=90)
    center_longitude: float | None = Field(default=None, ge=-180, le=180)
    radius_km: float | None = Field(default=None, gt=0, le=500)
    boundary_geojson: dict[str, Any] | None = None


class ZoneRead(ORMModel):
    id: int
    name: str
    code: str
    description: str | None = None
    habitat_type: str | None = None
    area_hectares: float | None = None
    center_latitude: float
    center_longitude: float
    radius_km: float
    boundary_geojson: dict[str, Any] | None = None
    created_at: datetime


class ZoneWithStats(ZoneRead):
    observation_count: int = 0
    species_count: int = 0
    device_count: int = 0
    last_observed_at: datetime | None = None


class RadiusQuery(BaseModel):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    radius_km: float = Field(gt=0, le=500)


class GeoJSONFeature(BaseModel):
    type: str = "Feature"
    geometry: dict[str, Any]
    properties: dict[str, Any]


class GeoJSONFeatureCollection(BaseModel):
    """Observation markers for the map, in a form Leaflet consumes directly."""

    type: str = "FeatureCollection"
    features: list[GeoJSONFeature]
    #: True when at least one coordinate was generalised for location privacy.
    location_generalised: bool = False
    total: int = 0
