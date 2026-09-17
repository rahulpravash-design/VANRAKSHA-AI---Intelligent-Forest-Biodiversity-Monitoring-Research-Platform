"""Device registration and sensor-ingest schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.models.enums import DeviceKind
from app.schemas.common import ORMModel


class DeviceCreate(BaseModel):
    device_code: str = Field(min_length=3, max_length=64)
    name: str = Field(min_length=2, max_length=160)
    kind: DeviceKind
    zone_id: int | None = None
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    firmware_version: str | None = Field(default=None, max_length=40)
    report_interval_minutes: int = Field(default=30, ge=1, le=1440)


class DeviceUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=160)
    zone_id: int | None = None
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    firmware_version: str | None = Field(default=None, max_length=40)
    report_interval_minutes: int | None = Field(default=None, ge=1, le=1440)
    is_active: bool | None = None


class DeviceRead(ORMModel):
    id: int
    device_code: str
    name: str
    kind: DeviceKind
    zone_id: int | None = None
    latitude: float | None = None
    longitude: float | None = None
    firmware_version: str | None = None
    report_interval_minutes: int
    is_active: bool
    last_seen_at: datetime | None = None
    created_at: datetime


class DeviceRegistered(DeviceRead):
    """Returned once, at registration: the plaintext ingest key is not stored."""

    ingest_key: str


class SensorReadingIn(BaseModel):
    recorded_at: datetime
    temperature_c: float | None = Field(default=None, ge=-60, le=80)
    humidity_pct: float | None = Field(default=None, ge=0, le=100)
    illuminance_lux: float | None = Field(default=None, ge=0, le=200_000)
    soil_moisture_pct: float | None = Field(default=None, ge=0, le=100)
    sound_level_db: float | None = Field(default=None, ge=0, le=200)
    motion_events: int | None = Field(default=None, ge=0, le=100_000)
    battery_volts: float | None = Field(default=None, ge=0, le=30)
    raw: dict[str, Any] | None = None


class SensorBatchIn(BaseModel):
    device_code: str
    #: Devices authenticate with the key issued at registration.
    ingest_key: str
    readings: list[SensorReadingIn] = Field(min_length=1, max_length=500)


class SensorReadingRead(ORMModel):
    id: int
    device_id: int
    zone_id: int | None = None
    recorded_at: datetime
    temperature_c: float | None = None
    humidity_pct: float | None = None
    illuminance_lux: float | None = None
    soil_moisture_pct: float | None = None
    sound_level_db: float | None = None
    motion_events: int | None = None
    battery_volts: float | None = None


class SensorIngestResult(BaseModel):
    accepted: int
    rejected: int
    device_id: int
    warnings: list[str] = Field(default_factory=list)
