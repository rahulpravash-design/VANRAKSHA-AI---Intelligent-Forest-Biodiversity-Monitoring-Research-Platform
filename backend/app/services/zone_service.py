"""Forest zones and the map's GeoJSON feed."""

from __future__ import annotations

from datetime import date, datetime

from fastapi import Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.core.errors import ConflictError, NotFoundError
from app.models.alert import Alert
from app.models.enums import AlertStatus, VerificationStatus
from app.models.iot import Device
from app.models.observation import Observation
from app.models.user import User
from app.models.zone import ForestZone
from app.schemas.observation import ObservationFilter
from app.schemas.zone import (
    GeoJSONFeature,
    GeoJSONFeatureCollection,
    ZoneCreate,
    ZoneRead,
    ZoneUpdate,
    ZoneWithStats,
)
from app.services import audit, observation_service
from app.services.geo import haversine_km


def get_zone(db: Session, zone_id: int) -> ForestZone:
    zone = db.get(ForestZone, zone_id)
    if zone is None:
        raise NotFoundError(f"No forest zone with id {zone_id}.")
    return zone


def list_zones(db: Session) -> list[ZoneWithStats]:
    zones = db.execute(select(ForestZone).order_by(ForestZone.code)).scalars().all()
    results: list[ZoneWithStats] = []
    for zone in zones:
        observations, species_count, last_seen = db.execute(
            select(
                func.count(Observation.id),
                func.count(
                    func.distinct(
                        func.coalesce(Observation.verified_species_id, Observation.species_id)
                    )
                ),
                func.max(Observation.observed_at),
            ).where(Observation.zone_id == zone.id)
        ).one()
        devices = db.execute(
            select(func.count(Device.id)).where(Device.zone_id == zone.id)
        ).scalar_one()
        results.append(
            ZoneWithStats(
                **ZoneRead.model_validate(zone).model_dump(),
                observation_count=int(observations or 0),
                species_count=int(species_count or 0),
                device_count=int(devices or 0),
                last_observed_at=last_seen,
            )
        )
    return results


def create_zone(
    db: Session, payload: ZoneCreate, *, actor: User, request: Request | None = None
) -> ForestZone:
    code = payload.code.strip().upper()
    existing = db.execute(
        select(ForestZone).where(func.upper(ForestZone.code) == code)
    ).scalar_one_or_none()
    if existing is not None:
        raise ConflictError(f"Zone code '{code}' is already in use (id {existing.id}).")
    data = payload.model_dump()
    data["code"] = code
    zone = ForestZone(**data)
    db.add(zone)
    db.flush()
    audit.record(
        db,
        "zone.create",
        user=actor,
        entity="zone",
        entity_id=zone.id,
        request=request,
        context={"code": zone.code},
    )
    db.commit()
    db.refresh(zone)
    return zone


def update_zone(
    db: Session,
    zone_id: int,
    payload: ZoneUpdate,
    *,
    actor: User,
    request: Request | None = None,
) -> ForestZone:
    zone = get_zone(db, zone_id)
    changes = payload.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(zone, field, value)
    audit.record(
        db,
        "zone.update",
        user=actor,
        entity="zone",
        entity_id=zone.id,
        request=request,
        context={"fields": sorted(changes)},
    )
    db.commit()
    db.refresh(zone)

    # Re-assigning geometry can move observations between zones.
    if {"center_latitude", "center_longitude", "radius_km"} & set(changes):
        reassign_observations(db, zone)
    return zone


def reassign_observations(db: Session, zone: ForestZone) -> int:
    """Re-evaluate zone membership for observations near a changed zone."""
    candidates = (
        db.execute(
            select(Observation).where(
                Observation.latitude.is_not(None), Observation.longitude.is_not(None)
            )
        )
        .scalars()
        .all()
    )
    changed = 0
    for observation in candidates:
        distance = haversine_km(
            observation.latitude, observation.longitude, zone.center_latitude,
            zone.center_longitude
        )
        inside = distance <= zone.radius_km
        if inside and observation.zone_id != zone.id:
            observation.zone_id = zone.id
            changed += 1
        elif not inside and observation.zone_id == zone.id:
            observation.zone_id = observation_service.resolve_zone(
                db, observation.latitude, observation.longitude
            )
            changed += 1
    if changed:
        db.commit()
    return changed


def delete_zone(
    db: Session, zone_id: int, *, actor: User, request: Request | None = None
) -> None:
    zone = get_zone(db, zone_id)
    audit.record(
        db,
        "zone.delete",
        user=actor,
        entity="zone",
        entity_id=zone_id,
        request=request,
        context={"code": zone.code},
    )
    db.delete(zone)
    db.commit()


def zone_geojson(db: Session) -> GeoJSONFeatureCollection:
    """Zone boundaries for the map layer."""
    zones = db.execute(select(ForestZone).order_by(ForestZone.code)).scalars().all()
    features: list[GeoJSONFeature] = []
    for zone in zones:
        open_alerts = db.execute(
            select(func.count(Alert.id)).where(
                Alert.zone_id == zone.id,
                Alert.status.in_([AlertStatus.OPEN, AlertStatus.INVESTIGATING]),
            )
        ).scalar_one()
        geometry = zone.boundary_geojson or {
            "type": "Point",
            "coordinates": [zone.center_longitude, zone.center_latitude],
        }
        features.append(
            GeoJSONFeature(
                geometry=geometry,
                properties={
                    "id": zone.id,
                    "code": zone.code,
                    "name": zone.name,
                    "habitat_type": zone.habitat_type,
                    "area_hectares": zone.area_hectares,
                    "radius_km": zone.radius_km,
                    "center": [zone.center_longitude, zone.center_latitude],
                    "open_alerts": int(open_alerts),
                    # True when the map should draw a circle instead of a polygon.
                    "approximate_boundary": zone.boundary_geojson is None,
                },
            )
        )
    return GeoJSONFeatureCollection(features=features, total=len(features))


def observations_geojson(
    db: Session,
    *,
    viewer: User | None,
    filters: ObservationFilter | None = None,
    limit: int = 2000,
    near: tuple[float, float, float] | None = None,
) -> GeoJSONFeatureCollection:
    """Observation markers for the map, with location privacy applied.

    The feature properties carry ``location_generalised`` per marker, so the map
    can draw a generalised record as a cell rather than a pin — showing a coarse
    position as a precise dot would misrepresent the data.
    """
    from app.services.geo import within_radius_filter

    filters = filters or ObservationFilter()
    statement = (
        select(Observation)
        .options(
            selectinload(Observation.species),
            selectinload(Observation.verified_species),
            selectinload(Observation.zone),
        )
        .where(Observation.latitude.is_not(None), Observation.longitude.is_not(None))
    )
    statement = observation_service._apply_filters(statement, filters)  # noqa: SLF001
    if near is not None:
        statement = statement.where(within_radius_filter(*near))
    rows = (
        db.execute(statement.order_by(Observation.observed_at.desc()).limit(limit))
        .scalars()
        .all()
    )

    any_generalised = False
    features: list[GeoJSONFeature] = []
    for row in rows:
        serialised = observation_service.serialise_observation(row, viewer)
        if serialised.latitude is None or serialised.longitude is None:
            continue
        any_generalised = any_generalised or serialised.location_generalised
        species = serialised.verified_species or serialised.species
        features.append(
            GeoJSONFeature(
                geometry={
                    "type": "Point",
                    "coordinates": [serialised.longitude, serialised.latitude],
                },
                properties={
                    "id": serialised.id,
                    "observation_type": str(serialised.observation_type),
                    "species_id": species.id if species else None,
                    "species": species.common_name if species else None,
                    "scientific_name": species.scientific_name if species else None,
                    "category": str(species.category) if species else None,
                    "conservation_status": (
                        str(species.conservation_status) if species else None
                    ),
                    "observed_at": serialised.observed_at.isoformat(),
                    "verification_status": str(serialised.verification_status),
                    "ai_prediction": serialised.ai_prediction,
                    "ai_confidence": serialised.ai_confidence,
                    "zone_id": serialised.zone_id,
                    "zone_name": serialised.zone_name,
                    "image_url": serialised.image_url,
                    "audio_url": serialised.audio_url,
                    "location_generalised": serialised.location_generalised,
                    "location_accuracy_m": serialised.location_accuracy_m,
                },
            )
        )
    return GeoJSONFeatureCollection(
        features=features,
        location_generalised=any_generalised,
        total=len(features),
    )


def zone_species_list(
    db: Session, zone_id: int, *, start: date | None = None, end: date | None = None
) -> list[dict]:
    """Species recorded in a zone, most frequent first."""
    from app.models.species import Species

    get_zone(db, zone_id)
    effective = func.coalesce(Observation.verified_species_id, Observation.species_id)
    statement = (
        select(
            Species.id,
            Species.common_name,
            Species.scientific_name,
            Species.category,
            Species.conservation_status,
            func.count(Observation.id),
            func.max(Observation.observed_at),
        )
        .join(Observation, effective == Species.id)
        .where(Observation.zone_id == zone_id)
        .group_by(
            Species.id,
            Species.common_name,
            Species.scientific_name,
            Species.category,
            Species.conservation_status,
        )
        .order_by(func.count(Observation.id).desc())
    )
    if start is not None:
        statement = statement.where(
            Observation.observed_at >= datetime.combine(start, datetime.min.time())
        )
    if end is not None:
        statement = statement.where(
            Observation.observed_at <= datetime.combine(end, datetime.max.time())
        )
    return [
        {
            "species_id": row[0],
            "common_name": row[1],
            "scientific_name": row[2],
            "category": str(row[3]),
            "conservation_status": str(row[4]),
            "detections": int(row[5]),
            "last_detected_at": row[6].isoformat() if row[6] else None,
        }
        for row in db.execute(statement).all()
    ]


def pending_in_zone(db: Session, zone_id: int) -> int:
    return int(
        db.execute(
            select(func.count(Observation.id)).where(
                Observation.zone_id == zone_id,
                Observation.verification_status == VerificationStatus.PENDING,
            )
        ).scalar_one()
    )
