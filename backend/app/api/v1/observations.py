"""Observation endpoints, including the multipart capture workflow."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Body, File, Form, Query, Request, UploadFile, status

from app.core.config import settings
from app.core.deps import CurrentUser, DbSession, OptionalUser, RecorderUser
from app.core.errors import ValidationError
from app.models.enums import MediaKind, ObservationType, VerificationStatus
from app.schemas.ai import PredictionResult
from app.schemas.common import Message, Page
from app.schemas.observation import (
    MediaAssetRead,
    ObservationCreate,
    ObservationDetail,
    ObservationFilter,
    ObservationRead,
    ObservationUpdate,
)
from app.services import ai_client, observation_service, storage
from app.services.ai_client import AIEngine

router = APIRouter(prefix="/observations", tags=["observations"])


def _filters(
    species_id: int | None,
    zone_id: int | None,
    researcher_id: int | None,
    observation_type: ObservationType | None,
    verification_status: VerificationStatus | None,
    category: str | None,
    observed_from: datetime | None,
    observed_to: datetime | None,
    has_media: bool | None,
    search: str | None,
) -> ObservationFilter:
    return ObservationFilter(
        species_id=species_id,
        zone_id=zone_id,
        researcher_id=researcher_id,
        observation_type=observation_type,
        verification_status=verification_status,
        category=category,
        observed_from=observed_from,
        observed_to=observed_to,
        has_media=has_media,
        search=search,
    )


@router.get("", response_model=Page[ObservationRead], summary="List and filter observations")
def list_observations(
    db: DbSession,
    viewer: OptionalUser,
    species_id: int | None = Query(default=None),
    zone_id: int | None = Query(default=None),
    researcher_id: int | None = Query(default=None),
    observation_type: ObservationType | None = Query(default=None),
    verification_status: VerificationStatus | None = Query(default=None),
    category: str | None = Query(default=None),
    observed_from: datetime | None = Query(default=None),
    observed_to: datetime | None = Query(default=None),
    has_media: bool | None = Query(default=None),
    search: str | None = Query(default=None, max_length=200),
    latitude: float | None = Query(default=None, ge=-90, le=90),
    longitude: float | None = Query(default=None, ge=-180, le=180),
    radius_km: float | None = Query(default=None, gt=0, le=500),
    sort: str = Query(default="-observed_at"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> Page[ObservationRead]:
    """Coordinates of sensitive taxa are generalised for callers without
    precise-location rights; affected rows report `location_generalised: true`."""
    near = None
    if latitude is not None and longitude is not None and radius_km is not None:
        near = (latitude, longitude, radius_km)
    return observation_service.list_observations(
        db,
        _filters(
            species_id,
            zone_id,
            researcher_id,
            observation_type,
            verification_status,
            category,
            observed_from,
            observed_to,
            has_media,
            search,
        ),
        viewer=viewer,
        limit=limit,
        offset=offset,
        sort=sort,
        near=near,
    )


@router.get(
    "/me", response_model=Page[ObservationRead], summary="Your own observations"
)
def my_observations(
    db: DbSession,
    user: CurrentUser,
    verification_status: VerificationStatus | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> Page[ObservationRead]:
    return observation_service.list_observations(
        db,
        ObservationFilter(researcher_id=user.id, verification_status=verification_status),
        viewer=user,
        limit=limit,
        offset=offset,
    )


@router.post(
    "",
    response_model=ObservationDetail,
    status_code=status.HTTP_201_CREATED,
    summary="Record an observation (JSON)",
)
def create_observation(
    db: DbSession,
    request: Request,
    recorder: RecorderUser,
    payload: ObservationCreate = Body(...),
) -> ObservationDetail:
    observation = observation_service.create_observation(
        db, payload, recorder=recorder, request=request
    )
    return observation_service.serialise_detail(observation, recorder)


@router.post(
    "/capture",
    response_model=ObservationDetail,
    status_code=status.HTTP_201_CREATED,
    summary="Record an observation with media and run AI identification",
    responses={
        413: {"description": "Upload exceeds the configured size limit"},
        422: {"description": "Media failed validation, or the species/zone does not exist"},
    },
)
async def capture_observation(
    db: DbSession,
    request: Request,
    recorder: RecorderUser,
    observed_at: datetime = Form(..., description="When the observation was made"),
    species_id: int | None = Form(default=None, description="Species as reported by the recorder"),
    zone_id: int | None = Form(default=None),
    latitude: float | None = Form(default=None, ge=-90, le=90),
    longitude: float | None = Form(default=None, ge=-180, le=180),
    location_accuracy_m: float | None = Form(default=None, ge=0),
    elevation_m: float | None = Form(default=None),
    notes: str | None = Form(default=None, max_length=4000),
    individual_count: int | None = Form(default=None, ge=0),
    observation_type: ObservationType | None = Form(default=None),
    run_ai: bool = Form(default=True, description="Run AI-assisted identification"),
    image: UploadFile | None = File(default=None),
    audio: UploadFile | None = File(default=None),
) -> ObservationDetail:
    """The field-capture workflow: upload → validate → store → AI → save.

    The model's opinion is recorded as an AI-assisted identification on the
    observation's `ai_*` fields and as `AIPrediction` rows. It is never written
    to `species_id`: that stays what the recorder reported until an expert
    decides. When both media types are supplied the image and audio predictions
    are fused, and the fused result is recorded alongside the individual ones.
    """
    if image is None and audio is None and species_id is None:
        raise ValidationError(
            "Provide at least an image, a recording, or the species you observed."
        )

    stored = []
    if image is not None:
        data = await storage.read_upload(image, settings.max_image_bytes)
        stored.append(storage.store_image(data, image.filename))
        image_bytes = data
    else:
        image_bytes = None

    audio_bytes = None
    if audio is not None:
        audio_bytes = await storage.read_upload(audio, settings.max_audio_bytes)
        stored.append(storage.store_audio(audio_bytes, audio.filename))
        spectrogram = storage.store_spectrogram(audio_bytes, audio.filename)
        if spectrogram is not None:
            stored.append(spectrogram)

    if observation_type is None:
        if image_bytes is not None and audio_bytes is not None:
            observation_type = ObservationType.MULTIMODAL
        elif audio_bytes is not None:
            observation_type = ObservationType.AUDIO
        elif image_bytes is not None:
            observation_type = ObservationType.IMAGE
        else:
            observation_type = ObservationType.FIELD_NOTE

    payload = ObservationCreate(
        species_id=species_id,
        zone_id=zone_id,
        observation_type=observation_type,
        latitude=latitude,
        longitude=longitude,
        location_accuracy_m=location_accuracy_m,
        elevation_m=elevation_m,
        observed_at=observed_at,
        notes=notes,
        individual_count=individual_count,
    )
    observation = observation_service.create_observation(
        db, payload, recorder=recorder, media=stored, request=request
    )

    if run_ai and (image_bytes or audio_bytes):
        engine = AIEngine(db)
        image_prediction = engine.predict_image(image_bytes) if image_bytes else None
        audio_prediction = (
            engine.predict_audio(audio_bytes, filename=audio.filename if audio else None)
            if audio_bytes
            else None
        )
        for prediction in (image_prediction, audio_prediction):
            if prediction is not None:
                observation_service.record_prediction(
                    db, observation, prediction, commit=False, set_primary=False
                )
        if image_prediction is not None and audio_prediction is not None:
            prior = engine.context_prior_for_zone(observation.zone_id)
            fused = engine.fuse(image_prediction, audio_prediction, context_prior=prior)
            observation_service.record_prediction(
                db, observation, fused, commit=False, set_primary=True
            )
        else:
            # A single modality: promote the row already recorded above rather
            # than inserting the same inference twice.
            observation_service.apply_primary_prediction(
                observation, image_prediction or audio_prediction
            )
        db.commit()
        observation = observation_service.get_observation(db, observation.id)

    return observation_service.serialise_detail(observation, recorder)


@router.get(
    "/{observation_id}",
    response_model=ObservationDetail,
    summary="Read an observation with its media and predictions",
    responses={404: {"description": "Observation not found"}},
)
def get_observation(
    db: DbSession, viewer: OptionalUser, observation_id: int
) -> ObservationDetail:
    observation = observation_service.get_observation(db, observation_id)
    return observation_service.serialise_detail(observation, viewer)


@router.patch(
    "/{observation_id}",
    response_model=ObservationDetail,
    summary="Update your own observation",
    responses={403: {"description": "Only the recorder or an administrator may edit"}},
)
def update_observation(
    db: DbSession,
    request: Request,
    user: CurrentUser,
    observation_id: int,
    payload: ObservationUpdate = Body(...),
) -> ObservationDetail:
    """Changing the reported species returns the record to the review queue."""
    observation = observation_service.update_observation(
        db, observation_id, payload, actor=user, request=request
    )
    return observation_service.serialise_detail(observation, user)


@router.delete(
    "/{observation_id}",
    response_model=Message,
    summary="Delete your own observation",
)
def delete_observation(
    db: DbSession, request: Request, user: CurrentUser, observation_id: int
) -> Message:
    observation_service.delete_observation(db, observation_id, actor=user, request=request)
    return Message(detail="Observation deleted.")


@router.post(
    "/{observation_id}/media",
    response_model=MediaAssetRead,
    status_code=status.HTTP_201_CREATED,
    summary="Attach an image or recording to an existing observation",
)
async def add_media(
    db: DbSession,
    request: Request,
    user: CurrentUser,
    observation_id: int,
    kind: MediaKind = Form(...),
    file: UploadFile = File(...),
) -> MediaAssetRead:
    observation = observation_service.get_observation(db, observation_id)
    observation_service.assert_can_modify(observation, user)
    if kind == MediaKind.IMAGE:
        data = await storage.read_upload(file, settings.max_image_bytes)
        asset = storage.store_image(data, file.filename)
    elif kind == MediaKind.AUDIO:
        data = await storage.read_upload(file, settings.max_audio_bytes)
        asset = storage.store_audio(data, file.filename)
    else:
        raise ValidationError("Only IMAGE and AUDIO media can be uploaded directly.")
    record = observation_service.attach_media(db, observation, asset)
    return MediaAssetRead.model_validate(record)


@router.post(
    "/{observation_id}/identify",
    response_model=list[PredictionResult],
    summary="Re-run AI identification on an observation's stored media",
)
def reidentify(
    db: DbSession, user: CurrentUser, observation_id: int
) -> list[PredictionResult]:
    """Useful after a model upgrade or after new species were added.

    Earlier predictions are kept: re-running appends a new `AIPrediction` row so
    the history of what each model version said stays intact.
    """
    from app.api.v1.ai import to_prediction_result

    observation = observation_service.get_observation(db, observation_id)
    observation_service.assert_can_modify(observation, user)

    engine = AIEngine(db)
    results: list[PredictionResult] = []
    image_prediction = None
    audio_prediction = None

    store = storage.get_storage()
    for asset in observation.media:
        if not isinstance(store, storage.LocalStorage):  # pragma: no cover
            continue
        path = store._path_for(asset.storage_key)
        if not path.exists():
            continue
        if str(asset.kind) == "IMAGE" and image_prediction is None:
            image_prediction = engine.predict_image(path.read_bytes())
        elif str(asset.kind) == "AUDIO" and audio_prediction is None:
            audio_prediction = engine.predict_audio(
                path.read_bytes(), filename=asset.original_filename
            )

    if image_prediction is None and audio_prediction is None:
        raise ValidationError("This observation has no stored media to analyse.")

    for prediction in (image_prediction, audio_prediction):
        if prediction is not None:
            observation_service.record_prediction(
                db, observation, prediction, commit=False, set_primary=False
            )
            results.append(to_prediction_result(db, prediction))

    if image_prediction is not None and audio_prediction is not None:
        prior = engine.context_prior_for_zone(observation.zone_id)
        fused = engine.fuse(image_prediction, audio_prediction, context_prior=prior)
        observation_service.record_prediction(db, observation, fused, commit=False)
        results.append(to_prediction_result(db, fused))
    else:
        observation_service.apply_primary_prediction(
            observation, image_prediction or audio_prediction
        )
    db.commit()
    return results


@router.get(
    "/stats/summary",
    response_model=dict,
    summary="Queue and media health for the observation module",
)
def summary(db: DbSession, _user: CurrentUser) -> dict:
    return {
        "pending_review": observation_service.pending_review_count(db),
        "pending_over_14_days": observation_service.stale_pending(db, days=14),
        "media": observation_service.media_summary(db),
        "observation_types": observation_service.observation_types(),
        "ai_mode": ai_client.AIEngine(db).mode,
    }
