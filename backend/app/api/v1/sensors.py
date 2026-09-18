"""IoT device registration and sensor ingest."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Body, Query, Request, status

from app.core.deps import AdminUser, CurrentUser, DbSession, OfficerUser
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
from app.services import sensor_service

router = APIRouter(prefix="/sensors", tags=["iot"])


@router.get("/devices", response_model=list[DeviceRead], summary="List monitoring nodes")
def list_devices(
    db: DbSession,
    _user: CurrentUser,
    zone_id: int | None = Query(default=None),
    active_only: bool = Query(default=False),
) -> list[DeviceRead]:
    return sensor_service.list_devices(db, zone_id=zone_id, active_only=active_only)


@router.get("/devices/health", response_model=list[dict], summary="Reporting status per node")
def device_health(db: DbSession, _user: CurrentUser) -> list[dict]:
    """`online`, `late`, `offline`, `never_reported` or `disabled`, judged
    against each node's configured reporting interval."""
    return sensor_service.device_health(db)


@router.post(
    "/devices",
    response_model=DeviceRegistered,
    status_code=status.HTTP_201_CREATED,
    summary="Register a monitoring node",
    responses={409: {"description": "Device code already registered"}},
)
def register_device(
    db: DbSession, request: Request, officer: OfficerUser, payload: DeviceCreate = Body(...)
) -> DeviceRegistered:
    """The response carries the node's ingest key. It is stored only as a hash,
    so this is the one and only time it can be read — copy it into the node's
    configuration now."""
    return sensor_service.register_device(db, payload, actor=officer, request=request)


@router.post(
    "/devices/{device_id}/rotate-key",
    response_model=DeviceRegistered,
    summary="Issue a new ingest key for a node",
)
def rotate_key(
    db: DbSession, request: Request, admin: AdminUser, device_id: int
) -> DeviceRegistered:
    return sensor_service.rotate_ingest_key(db, device_id, actor=admin, request=request)


@router.patch("/devices/{device_id}", response_model=DeviceRead, summary="Update a node")
def update_device(
    db: DbSession,
    request: Request,
    officer: OfficerUser,
    device_id: int,
    payload: DeviceUpdate = Body(...),
) -> DeviceRead:
    device = sensor_service.update_device(
        db, device_id, payload, actor=officer, request=request
    )
    return DeviceRead.model_validate(device)


@router.post(
    "/readings",
    response_model=SensorIngestResult,
    summary="Ingest a batch of sensor readings (device-authenticated)",
    responses={401: {"description": "Unknown device code or ingest key"}},
)
def ingest(
    db: DbSession, request: Request, payload: SensorBatchIn = Body(...)
) -> SensorIngestResult:
    """Called by field nodes, not by users.

    The node authenticates with its own ingest key rather than a user token, so
    a captured node cannot read observations or touch anything else. Readings
    dated in the future or older than the backfill window are rejected and
    reported in `warnings` — a node with a wrong clock would otherwise corrupt
    the baseline the anomaly detector fits.
    """
    return sensor_service.ingest_readings(db, payload, request=request)


@router.get(
    "/readings",
    response_model=Page[SensorReadingRead],
    summary="Query stored sensor readings",
)
def list_readings(
    db: DbSession,
    _user: CurrentUser,
    device_id: int | None = Query(default=None),
    zone_id: int | None = Query(default=None),
    since: datetime | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> Page[SensorReadingRead]:
    return sensor_service.list_readings(
        db, device_id=device_id, zone_id=zone_id, since=since, limit=limit, offset=offset
    )
