"""Field monitoring nodes and their environmental readings."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin
from app.models.enums import DeviceKind, sa_enum

if TYPE_CHECKING:  # pragma: no cover
    from app.models.zone import ForestZone


class Device(Base, TimestampMixin):
    __tablename__ = "devices"

    id: Mapped[int] = mapped_column(primary_key=True)
    device_code: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    kind: Mapped[DeviceKind] = mapped_column(
        sa_enum(DeviceKind, 24), nullable=False
    )
    zone_id: Mapped[int | None] = mapped_column(
        ForeignKey("forest_zones.id", ondelete="SET NULL"), index=True
    )
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    firmware_version: Mapped[str | None] = mapped_column(String(40))
    #: Expected reporting interval — used to raise DEVICE_OFFLINE / DATA_GAP.
    report_interval_minutes: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    #: Hashed ingest key; devices authenticate with it on /sensors/readings.
    ingest_key_hash: Mapped[str | None] = mapped_column(String(255))

    zone: Mapped[ForestZone | None] = relationship(back_populates="devices")
    readings: Mapped[list[SensorReading]] = relationship(
        back_populates="device", cascade="all, delete-orphan"
    )


class SensorReading(Base):
    __tablename__ = "sensor_readings"
    __table_args__ = (Index("ix_sensor_readings_device_recorded", "device_id", "recorded_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    device_id: Mapped[int] = mapped_column(
        ForeignKey("devices.id", ondelete="CASCADE"), index=True, nullable=False
    )
    zone_id: Mapped[int | None] = mapped_column(
        ForeignKey("forest_zones.id", ondelete="SET NULL"), index=True
    )
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), index=True, nullable=False
    )
    temperature_c: Mapped[float | None] = mapped_column(Float)
    humidity_pct: Mapped[float | None] = mapped_column(Float)
    illuminance_lux: Mapped[float | None] = mapped_column(Float)
    soil_moisture_pct: Mapped[float | None] = mapped_column(Float)
    sound_level_db: Mapped[float | None] = mapped_column(Float)
    motion_events: Mapped[int | None] = mapped_column(Integer)
    battery_volts: Mapped[float | None] = mapped_column(Float)
    raw: Mapped[dict[str, Any] | None] = mapped_column(JSON)

    device: Mapped[Device] = relationship(back_populates="readings")
