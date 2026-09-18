"""Device registration and sensor-reading ingest.

Field nodes cannot hold a user's JWT, so they authenticate with a per-device
ingest key issued once at registration and stored only as a hash. A node can
therefore write its own readings and nothing else.
"""

from __future__ import annotations

import logging
import secrets
from datetime import UTC, datetime, timedelta

from fastapi import Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import AuthenticationError, ConflictError, NotFoundError, ValidationError
from app.core.security import hash_password, verify_password
from app.models.iot import Device, SensorReading
from app.models.user import User
from app.models.zone import ForestZone
from app.schemas.common import Page
from app.schemas.iot import (
    DeviceCreate,
    DeviceRead,
    DeviceRegistered,
    DeviceUpdate,
    SensorBatchIn,
    SensorIngestResult,
    SensorReadingRead,
)
from app.services import audit

logger = logging.getLogger(__name__)

#: Readings this far in the future are rejected — a node with a bad clock would
#: otherwise poison the baseline the anomaly detector fits.
MAX_CLOCK_SKEW = timedelta(hours=2)
#: Readings older than this are rejected as a replay or a misconfigured backfill.
MAX_BACKFILL = timedelta(days=30)


def get_device(db: Session, device_id: int) -> Device:
    device = db.get(Device, device_id)
    if device is None:
        raise NotFoundError(f"No device with id {device_id}.")
    return device


def register_device(
    db: Session, payload: DeviceCreate, *, actor: User, request: Request | None = None
) -> DeviceRegistered:
    """Register a node and return its ingest key — shown exactly once."""
    code = payload.device_code.strip().upper()
    if db.execute(select(Device).where(Device.device_code == code)).scalar_one_or_none():
        raise ConflictError(f"Device code '{code}' is already registered.")
    if payload.zone_id is not None and db.get(ForestZone, payload.zone_id) is None:
        raise ValidationError(f"No forest zone with id {payload.zone_id}.")

    ingest_key = f"vrk_{secrets.token_urlsafe(32)}"
    device = Device(
        device_code=code,
        name=payload.name.strip(),
        kind=payload.kind,
        zone_id=payload.zone_id,
        latitude=payload.latitude,
        longitude=payload.longitude,
        firmware_version=payload.firmware_version,
        report_interval_minutes=payload.report_interval_minutes,
        is_active=True,
        ingest_key_hash=hash_password(ingest_key),
    )
    db.add(device)
    db.flush()
    audit.record(
        db,
        "device.register",
        user=actor,
        entity="device",
        entity_id=device.id,
        request=request,
        context={"device_code": device.device_code, "kind": str(device.kind)},
    )
    db.commit()
    db.refresh(device)
    return DeviceRegistered(**DeviceRead.model_validate(device).model_dump(), ingest_key=ingest_key)


def rotate_ingest_key(
    db: Session, device_id: int, *, actor: User, request: Request | None = None
) -> DeviceRegistered:
    device = get_device(db, device_id)
    ingest_key = f"vrk_{secrets.token_urlsafe(32)}"
    device.ingest_key_hash = hash_password(ingest_key)
    audit.record(
        db,
        "device.rotate_key",
        user=actor,
        entity="device",
        entity_id=device.id,
        request=request,
    )
    db.commit()
    db.refresh(device)
    return DeviceRegistered(**DeviceRead.model_validate(device).model_dump(), ingest_key=ingest_key)


def update_device(
    db: Session,
    device_id: int,
    payload: DeviceUpdate,
    *,
    actor: User,
    request: Request | None = None,
) -> Device:
    device = get_device(db, device_id)
    changes = payload.model_dump(exclude_unset=True)
    if changes.get("zone_id") is not None and db.get(ForestZone, changes["zone_id"]) is None:
        raise ValidationError(f"No forest zone with id {changes['zone_id']}.")
    for field, value in changes.items():
        setattr(device, field, value)
    audit.record(
        db,
        "device.update",
        user=actor,
        entity="device",
        entity_id=device.id,
        request=request,
        context={"fields": sorted(changes)},
    )
    db.commit()
    db.refresh(device)
    return device


def list_devices(
    db: Session, *, zone_id: int | None = None, active_only: bool = False
) -> list[DeviceRead]:
    statement = select(Device).order_by(Device.device_code)
    if zone_id is not None:
        statement = statement.where(Device.zone_id == zone_id)
    if active_only:
        statement = statement.where(Device.is_active.is_(True))
    return [
        DeviceRead.model_validate(row) for row in db.execute(statement).scalars().all()
    ]


def authenticate_device(db: Session, device_code: str, ingest_key: str) -> Device:
    device = db.execute(
        select(Device).where(Device.device_code == device_code.strip().upper())
    ).scalar_one_or_none()
    # Unknown code and wrong key give the same answer, so the endpoint cannot be
    # used to enumerate deployed node identifiers.
    if device is None or not verify_password(ingest_key, device.ingest_key_hash):
        raise AuthenticationError("Unknown device code or ingest key.")
    if not device.is_active:
        raise AuthenticationError("This device has been deactivated.")
    return device


def ingest_readings(
    db: Session, payload: SensorBatchIn, *, request: Request | None = None
) -> SensorIngestResult:
    """Accept a batch of readings from an authenticated node."""
    device = authenticate_device(db, payload.device_code, payload.ingest_key)
    now = datetime.now(UTC)
    accepted = 0
    rejected = 0
    warnings: list[str] = []
    latest_seen: datetime | None = None

    for reading in payload.readings:
        recorded_at = reading.recorded_at
        if recorded_at.tzinfo is None:
            recorded_at = recorded_at.replace(tzinfo=UTC)
        if recorded_at > now + MAX_CLOCK_SKEW:
            rejected += 1
            warnings.append(
                f"Rejected a reading dated {recorded_at.isoformat()}: it is in the future, "
                "which usually means the node's clock is wrong."
            )
            continue
        if recorded_at < now - MAX_BACKFILL:
            rejected += 1
            warnings.append(
                f"Rejected a reading dated {recorded_at.isoformat()}: older than the "
                f"{MAX_BACKFILL.days}-day backfill window."
            )
            continue

        duplicate = db.execute(
            select(SensorReading.id).where(
                SensorReading.device_id == device.id,
                SensorReading.recorded_at == recorded_at,
            )
        ).first()
        if duplicate is not None:
            rejected += 1
            continue

        db.add(
            SensorReading(
                device_id=device.id,
                zone_id=device.zone_id,
                recorded_at=recorded_at,
                temperature_c=reading.temperature_c,
                humidity_pct=reading.humidity_pct,
                illuminance_lux=reading.illuminance_lux,
                soil_moisture_pct=reading.soil_moisture_pct,
                sound_level_db=reading.sound_level_db,
                motion_events=reading.motion_events,
                battery_volts=reading.battery_volts,
                raw=reading.raw,
            )
        )
        accepted += 1
        latest_seen = max(latest_seen or recorded_at, recorded_at)

    if latest_seen is not None:
        device.last_seen_at = latest_seen
    if rejected:
        logger.info(
            "device %s: accepted %d readings, rejected %d", device.device_code, accepted, rejected
        )
    db.commit()
    # Cap the warning list so a badly misconfigured node cannot return a
    # megabyte of near-identical messages.
    return SensorIngestResult(
        accepted=accepted, rejected=rejected, device_id=device.id, warnings=warnings[:10]
    )


def list_readings(
    db: Session,
    *,
    device_id: int | None = None,
    zone_id: int | None = None,
    since: datetime | None = None,
    limit: int = 200,
    offset: int = 0,
) -> Page[SensorReadingRead]:
    statement = select(SensorReading)
    if device_id is not None:
        statement = statement.where(SensorReading.device_id == device_id)
    if zone_id is not None:
        statement = statement.where(SensorReading.zone_id == zone_id)
    if since is not None:
        statement = statement.where(SensorReading.recorded_at >= since)
    total = db.execute(select(func.count()).select_from(statement.subquery())).scalar_one()
    rows = (
        db.execute(
            statement.order_by(SensorReading.recorded_at.desc()).limit(limit).offset(offset)
        )
        .scalars()
        .all()
    )
    return Page[SensorReadingRead](
        items=[SensorReadingRead.model_validate(row) for row in rows],
        total=int(total),
        limit=limit,
        offset=offset,
    )


def device_health(db: Session) -> list[dict]:
    """Reporting status per node — drives the sensors dashboard."""
    now = datetime.now(UTC)
    devices = db.execute(select(Device).order_by(Device.device_code)).scalars().all()
    health: list[dict] = []
    for device in devices:
        last_seen = device.last_seen_at
        if last_seen is not None and last_seen.tzinfo is None:
            last_seen = last_seen.replace(tzinfo=UTC)
        silent_minutes = (
            (now - last_seen).total_seconds() / 60.0 if last_seen is not None else None
        )
        expected = device.report_interval_minutes
        if not device.is_active:
            status = "disabled"
        elif silent_minutes is None:
            status = "never_reported"
        elif silent_minutes <= expected * 2:
            status = "online"
        elif silent_minutes <= expected * 4:
            status = "late"
        else:
            status = "offline"
        battery = db.execute(
            select(SensorReading.battery_volts)
            .where(SensorReading.device_id == device.id,
                   SensorReading.battery_volts.is_not(None))
            .order_by(SensorReading.recorded_at.desc())
            .limit(1)
        ).scalar()
        reading_count = db.execute(
            select(func.count(SensorReading.id)).where(SensorReading.device_id == device.id)
        ).scalar_one()
        health.append(
            {
                "device_id": device.id,
                "device_code": device.device_code,
                "name": device.name,
                "kind": str(device.kind),
                "zone_id": device.zone_id,
                "status": status,
                "last_seen_at": last_seen.isoformat() if last_seen else None,
                "silent_minutes": round(silent_minutes, 1) if silent_minutes else None,
                "report_interval_minutes": expected,
                "battery_volts": round(float(battery), 2) if battery is not None else None,
                "reading_count": int(reading_count),
            }
        )
    return health


def environmental_summary(
    db: Session, *, zone_id: int | None = None, hours: int = 24
) -> dict:
    """Recent environmental conditions, for context beside a detection drop."""
    since = datetime.now(UTC) - timedelta(hours=hours)
    statement = select(
        func.avg(SensorReading.temperature_c),
        func.min(SensorReading.temperature_c),
        func.max(SensorReading.temperature_c),
        func.avg(SensorReading.humidity_pct),
        func.avg(SensorReading.sound_level_db),
        func.sum(SensorReading.motion_events),
        func.count(SensorReading.id),
    ).where(SensorReading.recorded_at >= since)
    if zone_id is not None:
        statement = statement.where(SensorReading.zone_id == zone_id)
    row = db.execute(statement).one()
    return {
        "window_hours": hours,
        "zone_id": zone_id,
        "reading_count": int(row[6] or 0),
        "temperature_c": {
            "mean": round(float(row[0]), 2) if row[0] is not None else None,
            "min": round(float(row[1]), 2) if row[1] is not None else None,
            "max": round(float(row[2]), 2) if row[2] is not None else None,
        },
        "humidity_pct_mean": round(float(row[3]), 2) if row[3] is not None else None,
        "sound_level_db_mean": round(float(row[4]), 2) if row[4] is not None else None,
        "motion_events_total": int(row[5] or 0),
    }
