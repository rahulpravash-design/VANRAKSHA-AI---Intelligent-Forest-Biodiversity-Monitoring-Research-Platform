"""AI inference endpoints.

Every response here is labelled an *AI-assisted identification*. The schema
carries `requires_expert_verification: true` and an `identification_basis`
string that the UI shows beside the result, because a confidence number next to
a species name reads as a determination unless the interface says otherwise.
"""

from __future__ import annotations

from fastapi import APIRouter, Body, File, UploadFile, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.deps import CurrentUser, DbSession, RecorderUser
from app.core.errors import ValidationError
from app.models.enums import Modality
from app.models.species import Species
from app.schemas.ai import (
    AIEngineStatus,
    Detection,
    FusionRequest,
    ModelInfo,
    PredictionCandidate,
    PredictionResult,
)
from app.schemas.species import SpeciesSummary
from app.services import storage
from app.services.ai_client import AIEngine

router = APIRouter(prefix="/ai", tags=["ai"])


def to_prediction_result(db: Session, prediction) -> PredictionResult:  # noqa: ANN001
    """Convert an engine :class:`ai.schema.Prediction` into the API model."""
    species = None
    if prediction.species_id is not None:
        row = db.get(Species, prediction.species_id)
        species = SpeciesSummary.model_validate(row) if row is not None else None
    modality = (
        Modality(prediction.modality)
        if prediction.modality in {m.value for m in Modality}
        else Modality.IMAGE
    )
    return PredictionResult(
        modality=modality,
        model_name=prediction.model_name,
        model_version=prediction.model_version,
        predicted_label=prediction.label,
        predicted_species=species,
        confidence=float(prediction.confidence),
        is_uncertain=bool(prediction.is_uncertain),
        top_k=[
            PredictionCandidate(
                species_id=candidate.species_id,
                label=candidate.label,
                scientific_name=candidate.scientific_name,
                confidence=float(candidate.confidence),
            )
            for candidate in prediction.top_k
        ],
        detections=[
            Detection(bbox=list(detection.bbox), score=detection.score, label=detection.label)
            for detection in prediction.detections
        ],
        diagnostics=prediction.diagnostics or None,
        latency_ms=prediction.latency_ms,
    )


@router.get("/status", response_model=AIEngineStatus, summary="Which models are loaded")
def engine_status(db: DbSession) -> AIEngineStatus:
    """Reports the active backend for each modality.

    `backend: "baseline"` means the dependency-free descriptor/template matcher
    is in use because no trained weights are configured — informative rather
    than broken, and the `notes` field says how to change it.
    """
    info = AIEngine(db).info()
    return AIEngineStatus(
        vision=ModelInfo(**info.vision),
        audio=ModelInfo(**info.audio),
        anomaly_methods=info.anomaly_methods,
        fusion_available=info.fusion_available,
    )


@router.post(
    "/identify/image",
    response_model=PredictionResult,
    summary="AI-assisted identification from a photograph",
    responses={422: {"description": "File is not a usable image"}},
)
async def identify_image(
    db: DbSession, _user: RecorderUser, file: UploadFile = File(...)
) -> PredictionResult:
    """A preview call: nothing is stored. Use `POST /observations/capture` to
    record an observation together with its identification."""
    data = await storage.read_upload(file, settings.max_image_bytes)
    prediction = AIEngine(db).predict_image(data)
    return to_prediction_result(db, prediction)


@router.post(
    "/identify/audio",
    response_model=PredictionResult,
    summary="AI-assisted identification from a recording",
    responses={422: {"description": "File is not usable audio"}},
)
async def identify_audio(
    db: DbSession, _user: RecorderUser, file: UploadFile = File(...)
) -> PredictionResult:
    data = await storage.read_upload(file, settings.max_audio_bytes)
    prediction = AIEngine(db).predict_audio(data, filename=file.filename)
    return to_prediction_result(db, prediction)


@router.post(
    "/analyse/audio",
    response_model=dict,
    summary="Acoustic measurements for a recording, with no species claim",
)
async def analyse_audio(
    db: DbSession, _user: CurrentUser, file: UploadFile = File(...)
) -> dict:
    """Returns the measured call parameters and a mel spectrogram summary.

    Used by the recording view to draw the spectrogram and to show *why* a
    template matched, independently of any identification.
    """
    data = await storage.read_upload(file, settings.max_audio_bytes)
    engine = AIEngine(db)
    decoded, features = engine.analyse_audio(data, filename=file.filename)
    return {
        "sample_rate": decoded.sample_rate,
        "duration_seconds": round(decoded.duration_seconds, 3),
        "channels_original": decoded.channels_original,
        "source_format": decoded.source_format,
        "features": features.as_dict(),
        "note": (
            "Acoustic measurements only. No species identification is implied by "
            "this response."
        ),
    }


@router.post(
    "/fuse",
    response_model=PredictionResult,
    summary="Combine an image and an audio prediction",
    status_code=status.HTTP_200_OK,
)
def fuse(
    db: DbSession, _user: RecorderUser, payload: FusionRequest = Body(...)
) -> PredictionResult:
    """Log-linear late fusion, weighted by each modality's reliability.

    A modality whose distribution is close to uniform — it does not know —
    contributes proportionately little, so a confident single modality is not
    diluted by an uninformative partner.
    """
    if payload.image is None and payload.audio is None:
        raise ValidationError("Provide at least one of 'image' or 'audio'.")

    from ai.schema import Candidate, Prediction

    def rebuild(result):  # noqa: ANN001
        if result is None:
            return None
        return Prediction(
            modality=str(result.modality),
            model_name=result.model_name,
            model_version=result.model_version,
            label=result.predicted_label,
            confidence=result.confidence,
            is_uncertain=result.is_uncertain,
            species_id=(
                result.predicted_species.id if result.predicted_species else None
            ),
            top_k=tuple(
                Candidate(
                    species_id=candidate.species_id,
                    label=candidate.label,
                    scientific_name=candidate.scientific_name,
                    confidence=candidate.confidence,
                )
                for candidate in result.top_k
            ),
        )

    engine = AIEngine(db)
    fused = engine.fuse(
        rebuild(payload.image), rebuild(payload.audio), context_prior=payload.context
    )
    return to_prediction_result(db, fused)
