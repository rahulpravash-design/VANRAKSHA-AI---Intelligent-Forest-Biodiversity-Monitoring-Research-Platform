"""Forest zones and the map feeds."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Body, Query, Request, status

from app.core.deps import AdminUser, DbSession, OfficerUser, OptionalUser
from app.models.enums import ObservationType, VerificationStatus
from app.schemas.common import Message
from app.schemas.observation import ObservationFilter
from app.schemas.zone import (
    GeoJSONFeatureCollection,
    ZoneCreate,
    ZoneRead,
    ZoneUpdate,
    ZoneWithStats,
)
from app.services import zone_service

router = APIRouter(prefix="/zones", tags=["gis"])


@router.get("", response_model=list[ZoneWithStats], summary="List forest zones with counts")
def list_zones(db: DbSession) -> list[ZoneWithStats]:
    return zone_service.list_zones(db)


@router.get(
    "/geojson",
    response_model=GeoJSONFeatureCollection,
    summary="Zone boundaries as GeoJSON",
)
def zones_geojson(db: DbSession) -> GeoJSONFeatureCollection:
    """Features carry `approximate_boundary` when only a centroid and radius are
    known, so the map draws a circle rather than implying a surveyed boundary."""
    return zone_service.zone_geojson(db)


@router.get(
    "/observations/geojson",
    response_model=GeoJSONFeatureCollection,
    summary="Observation markers as GeoJSON, with location privacy applied",
)
def observations_geojson(
    db: DbSession,
    viewer: OptionalUser,
    species_id: int | None = Query(default=None),
    zone_id: int | None = Query(default=None),
    observation_type: ObservationType | None = Query(default=None),
    verification_status: VerificationStatus | None = Query(default=None),
    category: str | None = Query(default=None),
    observed_from: date | None = Query(default=None),
    observed_to: date | None = Query(default=None),
    latitude: float | None = Query(default=None, ge=-90, le=90),
    longitude: float | None = Query(default=None, ge=-180, le=180),
    radius_km: float | None = Query(default=None, gt=0, le=500),
    limit: int = Query(default=2000, ge=1, le=10000),
) -> GeoJSONFeatureCollection:
    """Markers for the biodiversity map.

    Coordinates of sensitive taxa are snapped to a coarse grid for callers
    without precise-location rights; each feature reports its own
    `location_generalised` flag so the map can render it honestly.
    """
    from datetime import datetime, time

    filters = ObservationFilter(
        species_id=species_id,
        zone_id=zone_id,
        observation_type=observation_type,
        verification_status=verification_status,
        category=category,
        observed_from=datetime.combine(observed_from, time.min) if observed_from else None,
        observed_to=datetime.combine(observed_to, time.max) if observed_to else None,
    )
    near = None
    if latitude is not None and longitude is not None and radius_km is not None:
        near = (latitude, longitude, radius_km)
    return zone_service.observations_geojson(
        db, viewer=viewer, filters=filters, limit=limit, near=near
    )


@router.get("/{zone_id}", response_model=ZoneWithStats, summary="Read a zone")
def get_zone(db: DbSession, zone_id: int) -> ZoneWithStats:
    zones = {zone.id: zone for zone in zone_service.list_zones(db)}
    zone = zones.get(zone_id)
    if zone is None:
        from app.core.errors import NotFoundError

        raise NotFoundError(f"No forest zone with id {zone_id}.")
    return zone


@router.get(
    "/{zone_id}/species",
    response_model=list[dict],
    summary="Species recorded in a zone, most frequent first",
)
def zone_species(
    db: DbSession,
    zone_id: int,
    start: date | None = Query(default=None),
    end: date | None = Query(default=None),
) -> list[dict]:
    return zone_service.zone_species_list(db, zone_id, start=start, end=end)


@router.post(
    "",
    response_model=ZoneRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a forest zone",
    responses={409: {"description": "Zone code already in use"}},
)
def create_zone(
    db: DbSession, request: Request, actor: OfficerUser, payload: ZoneCreate = Body(...)
) -> ZoneRead:
    zone = zone_service.create_zone(db, payload, actor=actor, request=request)
    return ZoneRead.model_validate(zone)


@router.patch("/{zone_id}", response_model=ZoneRead, summary="Update a zone")
def update_zone(
    db: DbSession,
    request: Request,
    actor: OfficerUser,
    zone_id: int,
    payload: ZoneUpdate = Body(...),
) -> ZoneRead:
    """Changing a zone's geometry re-evaluates which observations fall inside it."""
    zone = zone_service.update_zone(db, zone_id, payload, actor=actor, request=request)
    return ZoneRead.model_validate(zone)


@router.delete("/{zone_id}", response_model=Message, summary="Delete a zone")
def delete_zone(db: DbSession, request: Request, admin: AdminUser, zone_id: int) -> Message:
    zone_service.delete_zone(db, zone_id, actor=admin, request=request)
    return Message(detail="Zone deleted. Observations inside it were kept and unassigned.")
