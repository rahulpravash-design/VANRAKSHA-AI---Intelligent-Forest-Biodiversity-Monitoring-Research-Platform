"""Observation creation, querying and serialisation.

Two rules are enforced here rather than in the routers, so no endpoint can
forget them:

* **A model output is never written to ``species_id``.** The AI's opinion lives
  in ``ai_prediction`` / ``ai_predicted_species_id`` and in the
  :class:`~app.models.ai.AIPrediction` rows; ``species_id`` only ever holds what
  a human reported, and ``verified_species_id`` what an expert concluded.
* **Coordinates are generalised on the way out.** Serialisation goes through
  :func:`serialise_observation`, which applies the location-privacy rules for the
  requesting user.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import Request
from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.core.errors import NotFoundError, PermissionDeniedError, ValidationError
from app.models.ai import AIPrediction
from app.models.enums import (
    MediaKind,
    Modality,
    ObservationType,
    UserRole,
    VerificationStatus,
)
from app.models.observation import MediaAsset, Observation
from app.models.species import Species
from app.models.user import User
from app.models.zone import ForestZone
from app.schemas.ai import AIPredictionRead
from app.schemas.common import Page
from app.schemas.observation import (
    MediaAssetRead,
    ObservationCreate,
    ObservationDetail,
    ObservationFilter,
    ObservationRead,
    ObservationUpdate,
)
from app.schemas.species import SpeciesSummary
from app.schemas.user import UserPublic
from app.services import audit
from app.services.geo import apply_location_privacy, haversine_km, within_radius_filter
from app.services.storage import StoredMedia

logger = logging.getLogger(__name__)

_LOAD_OPTIONS = (
    selectinload(Observation.species),
    selectinload(Observation.verified_species),
    selectinload(Observation.ai_predicted_species),
    selectinload(Observation.zone),
    selectinload(Observation.media),
    selectinload(Observation.researcher),
    selectinload(Observation.predictions).selectinload(AIPrediction.predicted_species),
)


# --------------------------------------------------------------------------- #
# lookup
# --------------------------------------------------------------------------- #
def get_observation(db: Session, observation_id: int) -> Observation:
    observation = db.execute(
        select(Observation).options(*_LOAD_OPTIONS).where(Observation.id == observation_id)
    ).scalar_one_or_none()
    if observation is None:
        raise NotFoundError(f"No observation with id {observation_id}.")
    return observation


def assert_can_modify(observation: Observation, user: User) -> None:
    """Only the recorder or an administrator may edit or delete a record."""
    if user.role == UserRole.ADMIN or observation.researcher_id == user.id:
        return
    raise PermissionDeniedError(
        "Only the researcher who recorded this observation, or an administrator, "
        "can modify it."
    )


def resolve_zone(db: Session, latitude: float | None, longitude: float | None) -> int | None:
    """Assign an observation to the nearest zone whose radius contains it."""
    if latitude is None or longitude is None:
        return None
    zones = db.execute(select(ForestZone)).scalars().all()
    best: tuple[float, int] | None = None
    for zone in zones:
        distance = haversine_km(
            latitude, longitude, zone.center_latitude, zone.center_longitude
        )
        if distance <= zone.radius_km and (best is None or distance < best[0]):
            best = (distance, zone.id)
    return best[1] if best else None


# --------------------------------------------------------------------------- #
# serialisation
# --------------------------------------------------------------------------- #
def _species_summary(species: Species | None) -> SpeciesSummary | None:
    return SpeciesSummary.model_validate(species) if species is not None else None


def serialise_observation(observation: Observation, viewer: User | None) -> ObservationRead:
    """Build the response model, applying location privacy for ``viewer``."""
    latitude, longitude, accuracy, generalised = apply_location_privacy(observation, viewer)
    return ObservationRead(
        id=observation.id,
        researcher_id=observation.researcher_id,
        observation_type=observation.observation_type,
        species=_species_summary(observation.species),
        zone_id=observation.zone_id,
        zone_name=observation.zone.name if observation.zone else None,
        image_url=observation.image_url,
        audio_url=observation.audio_url,
        latitude=latitude,
        longitude=longitude,
        location_accuracy_m=accuracy,
        elevation_m=observation.elevation_m,
        location_generalised=generalised,
        observed_at=observation.observed_at,
        notes=observation.notes,
        individual_count=observation.individual_count,
        conditions=observation.conditions,
        ai_prediction=observation.ai_prediction,
        ai_confidence=observation.ai_confidence,
        ai_model_version=observation.ai_model_version,
        ai_predicted_species=_species_summary(observation.ai_predicted_species),
        verification_status=observation.verification_status,
        verified_species=_species_summary(observation.verified_species),
        verified_at=observation.verified_at,
        created_at=observation.created_at,
        updated_at=observation.updated_at,
    )


def serialise_detail(observation: Observation, viewer: User | None) -> ObservationDetail:
    base = serialise_observation(observation, viewer).model_dump()
    final_species = None
    final_id = observation.final_species_id
    if final_id is not None:
        for candidate in (observation.verified_species, observation.species):
            if candidate is not None and candidate.id == final_id:
                final_species = _species_summary(candidate)
                break
    return ObservationDetail(
        **base,
        researcher=UserPublic.model_validate(observation.researcher)
        if observation.researcher
        else None,
        media=[MediaAssetRead.model_validate(asset) for asset in observation.media],
        predictions=[
            AIPredictionRead.model_validate(prediction)
            for prediction in sorted(
                observation.predictions, key=lambda p: p.created_at, reverse=True
            )
        ],
        final_species=final_species,
    )


# --------------------------------------------------------------------------- #
# listing
# --------------------------------------------------------------------------- #
def _apply_filters(statement: Select, filters: ObservationFilter) -> Select:
    if filters.species_id is not None:
        statement = statement.where(
            or_(
                Observation.species_id == filters.species_id,
                Observation.verified_species_id == filters.species_id,
            )
        )
    if filters.zone_id is not None:
        statement = statement.where(Observation.zone_id == filters.zone_id)
    if filters.researcher_id is not None:
        statement = statement.where(Observation.researcher_id == filters.researcher_id)
    if filters.observation_type is not None:
        statement = statement.where(Observation.observation_type == filters.observation_type)
    if filters.verification_status is not None:
        statement = statement.where(
            Observation.verification_status == filters.verification_status
        )
    if filters.category:
        statement = statement.where(
            Observation.species_id.in_(
                select(Species.id).where(Species.category == filters.category)
            )
        )
    if filters.observed_from is not None:
        statement = statement.where(Observation.observed_at >= filters.observed_from)
    if filters.observed_to is not None:
        statement = statement.where(Observation.observed_at <= filters.observed_to)
    if filters.has_media is True:
        statement = statement.where(
            or_(Observation.image_url.is_not(None), Observation.audio_url.is_not(None))
        )
    elif filters.has_media is False:
        statement = statement.where(
            Observation.image_url.is_(None), Observation.audio_url.is_(None)
        )
    if filters.search:
        pattern = f"%{filters.search.strip().lower()}%"
        statement = statement.where(
            or_(
                func.lower(func.coalesce(Observation.notes, "")).like(pattern),
                func.lower(func.coalesce(Observation.ai_prediction, "")).like(pattern),
                Observation.species_id.in_(
                    select(Species.id).where(
                        or_(
                            func.lower(Species.common_name).like(pattern),
                            func.lower(Species.scientific_name).like(pattern),
                        )
                    )
                ),
            )
        )
    return statement


def list_observations(
    db: Session,
    filters: ObservationFilter,
    *,
    viewer: User | None,
    limit: int = 50,
    offset: int = 0,
    sort: str = "-observed_at",
    near: tuple[float, float, float] | None = None,
) -> Page[ObservationRead]:
    statement = select(Observation).options(*_LOAD_OPTIONS)
    statement = _apply_filters(statement, filters)
    if near is not None:
        statement = statement.where(within_radius_filter(*near))

    total = db.execute(select(func.count()).select_from(statement.subquery())).scalar_one()
    order = {
        "-observed_at": Observation.observed_at.desc(),
        "observed_at": Observation.observed_at.asc(),
        "-created_at": Observation.created_at.desc(),
        "created_at": Observation.created_at.asc(),
        "-ai_confidence": Observation.ai_confidence.desc().nulls_last(),
    }.get(sort, Observation.observed_at.desc())
    rows = (
        db.execute(statement.order_by(order, Observation.id.desc()).limit(limit).offset(offset))
        .scalars()
        .all()
    )
    return Page[ObservationRead](
        items=[serialise_observation(row, viewer) for row in rows],
        total=int(total),
        limit=limit,
        offset=offset,
    )


# --------------------------------------------------------------------------- #
# mutation
# --------------------------------------------------------------------------- #
def _validate_species(db: Session, species_id: int | None) -> Species | None:
    if species_id is None:
        return None
    species = db.get(Species, species_id)
    if species is None:
        raise ValidationError(f"No species with id {species_id}.")
    return species


def _validate_zone(db: Session, zone_id: int | None) -> ForestZone | None:
    if zone_id is None:
        return None
    zone = db.get(ForestZone, zone_id)
    if zone is None:
        raise ValidationError(f"No forest zone with id {zone_id}.")
    return zone


def create_observation(
    db: Session,
    payload: ObservationCreate,
    *,
    recorder: User,
    media: list[StoredMedia] | None = None,
    request: Request | None = None,
) -> Observation:
    """Record an observation, optionally with already-stored media attached."""
    _validate_species(db, payload.species_id)
    zone = _validate_zone(db, payload.zone_id)

    observed_at = payload.observed_at
    if observed_at.tzinfo is None:
        observed_at = observed_at.replace(tzinfo=UTC)

    zone_id = zone.id if zone else resolve_zone(db, payload.latitude, payload.longitude)
    observation = Observation(
        researcher_id=recorder.id,
        species_id=payload.species_id,
        zone_id=zone_id,
        observation_type=payload.observation_type,
        latitude=payload.latitude,
        longitude=payload.longitude,
        location_accuracy_m=payload.location_accuracy_m,
        elevation_m=payload.elevation_m,
        observed_at=observed_at,
        notes=payload.notes,
        individual_count=payload.individual_count,
        conditions=payload.conditions,
        verification_status=VerificationStatus.PENDING,
    )
    db.add(observation)
    db.flush()

    for asset in media or []:
        attach_media(db, observation, asset, commit=False)

    audit.record(
        db,
        "observation.create",
        user=recorder,
        entity="observation",
        entity_id=observation.id,
        request=request,
        context={
            "type": str(observation.observation_type),
            "species_id": observation.species_id,
            "zone_id": observation.zone_id,
            "has_coordinates": observation.latitude is not None,
        },
    )
    db.commit()
    return get_observation(db, observation.id)


def attach_media(
    db: Session, observation: Observation, asset: StoredMedia, *, commit: bool = True
) -> MediaAsset:
    """Attach stored media and mirror the primary URL onto the observation."""
    record = MediaAsset(
        observation_id=observation.id,
        kind=asset.kind,
        storage_key=asset.storage_key,
        public_url=asset.public_url,
        mime_type=asset.mime_type,
        size_bytes=asset.size_bytes,
        checksum=asset.checksum,
        width=asset.width,
        height=asset.height,
        duration_seconds=asset.duration_seconds,
        sample_rate=asset.sample_rate,
        original_filename=asset.original_filename,
    )
    db.add(record)
    if asset.kind == MediaKind.IMAGE and not observation.image_url:
        observation.image_url = asset.public_url
    elif asset.kind == MediaKind.AUDIO and not observation.audio_url:
        observation.audio_url = asset.public_url
    if commit:
        db.commit()
        db.refresh(record)
    return record


def update_observation(
    db: Session,
    observation_id: int,
    payload: ObservationUpdate,
    *,
    actor: User,
    request: Request | None = None,
) -> Observation:
    observation = get_observation(db, observation_id)
    assert_can_modify(observation, actor)
    changes = payload.model_dump(exclude_unset=True)

    if "species_id" in changes:
        _validate_species(db, changes["species_id"])
    if "zone_id" in changes:
        _validate_zone(db, changes["zone_id"])
    if "observed_at" in changes and changes["observed_at"] is not None:
        value = changes["observed_at"]
        changes["observed_at"] = value if value.tzinfo else value.replace(tzinfo=UTC)

    for field, value in changes.items():
        setattr(observation, field, value)

    if ("latitude" in changes or "longitude" in changes) and "zone_id" not in changes:
        observation.zone_id = resolve_zone(db, observation.latitude, observation.longitude)

    # Changing the reported species invalidates any completed review.
    if "species_id" in changes and observation.verification_status != VerificationStatus.PENDING:
        observation.verification_status = VerificationStatus.PENDING
        observation.verified_species_id = None
        observation.verified_at = None
        changes["verification_reset"] = True

    audit.record(
        db,
        "observation.update",
        user=actor,
        entity="observation",
        entity_id=observation.id,
        request=request,
        context={"fields": sorted(changes)},
    )
    db.commit()
    return get_observation(db, observation_id)


def delete_observation(
    db: Session, observation_id: int, *, actor: User, request: Request | None = None
) -> None:
    observation = get_observation(db, observation_id)
    assert_can_modify(observation, actor)
    keys = [asset.storage_key for asset in observation.media]
    audit.record(
        db,
        "observation.delete",
        user=actor,
        entity="observation",
        entity_id=observation_id,
        request=request,
        context={"media_removed": len(keys)},
    )
    db.delete(observation)
    db.commit()

    # Media is content-addressed, so only delete files no other record uses.
    from app.services.storage import get_storage

    storage = get_storage()
    for key in keys:
        still_referenced = db.execute(
            select(func.count(MediaAsset.id)).where(MediaAsset.storage_key == key)
        ).scalar_one()
        if not still_referenced:
            try:
                storage.delete(key)
            except Exception:  # pragma: no cover - best effort cleanup
                logger.warning("could not delete stored media %s", key, exc_info=True)


# --------------------------------------------------------------------------- #
# AI predictions
# --------------------------------------------------------------------------- #
def apply_primary_prediction(observation: Observation, prediction: Any) -> None:
    """Mirror a prediction onto the observation's ``ai_*`` summary columns.

    Separate from :func:`record_prediction` because promoting an already-stored
    prediction to "the primary one" must not insert a second row for the same
    inference — the predictions list is the audit trail of what each model
    version said, and a duplicate there corrupts the agreement statistics.

    It never touches ``species_id``: the reported species stays the human's
    until an expert decides otherwise.
    """
    observation.ai_prediction = prediction.label
    observation.ai_confidence = float(prediction.confidence)
    observation.ai_model_version = f"{prediction.model_name}@{prediction.model_version}"
    observation.ai_predicted_species_id = prediction.species_id


def record_prediction(
    db: Session,
    observation: Observation | None,
    prediction: Any,
    *,
    commit: bool = True,
    set_primary: bool = True,
) -> AIPrediction:
    """Persist a model output.

    ``set_primary`` mirrors the result onto the observation's ``ai_*`` columns
    for cheap listing, but never onto ``species_id``: the observation's species
    stays what the recorder reported until an expert decides otherwise.
    """
    row = AIPrediction(
        observation_id=observation.id if observation else None,
        modality=Modality(prediction.modality)
        if prediction.modality in {m.value for m in Modality}
        else Modality.IMAGE,
        model_name=prediction.model_name,
        model_version=prediction.model_version,
        predicted_species_id=prediction.species_id,
        predicted_label=prediction.label,
        confidence=float(prediction.confidence),
        is_uncertain=bool(prediction.is_uncertain),
        top_k=[candidate.as_dict() for candidate in prediction.top_k] or None,
        detections=[detection.as_dict() for detection in prediction.detections] or None,
        diagnostics=prediction.diagnostics or None,
        latency_ms=prediction.latency_ms,
    )
    db.add(row)
    if observation is not None and set_primary:
        apply_primary_prediction(observation, prediction)
    if commit:
        db.commit()
        db.refresh(row)
    return row


def recent_for_user(
    db: Session, user: User, *, limit: int = 5
) -> list[ObservationRead]:
    rows = (
        db.execute(
            select(Observation)
            .options(*_LOAD_OPTIONS)
            .where(Observation.researcher_id == user.id)
            .order_by(Observation.created_at.desc())
            .limit(limit)
        )
        .scalars()
        .all()
    )
    return [serialise_observation(row, user) for row in rows]


def pending_review_count(db: Session) -> int:
    return int(
        db.execute(
            select(func.count(Observation.id)).where(
                Observation.verification_status == VerificationStatus.PENDING
            )
        ).scalar_one()
    )


def stale_pending(db: Session, *, days: int = 14) -> int:
    """Observations awaiting review for longer than ``days`` — a queue-health signal."""
    cutoff = datetime.now(UTC) - timedelta(days=days)
    return int(
        db.execute(
            select(func.count(Observation.id)).where(
                Observation.verification_status == VerificationStatus.PENDING,
                Observation.created_at < cutoff,
            )
        ).scalar_one()
    )


def media_summary(db: Session) -> dict[str, int]:
    rows = db.execute(
        select(MediaAsset.kind, func.count(MediaAsset.id)).group_by(MediaAsset.kind)
    ).all()
    summary = {str(kind): int(count) for kind, count in rows}
    total_bytes = db.execute(select(func.sum(MediaAsset.size_bytes))).scalar() or 0
    summary["total_bytes"] = int(total_bytes)
    return summary


def observation_types() -> list[str]:
    return [t.value for t in ObservationType]


