"""VANRAKSHA AI inference service.

A thin FastAPI wrapper around the pipelines, so the AI engine can be deployed,
scaled and GPU-scheduled independently of the platform API.  The backend calls
this service when ``AI_SERVICE_URL`` is set and otherwise imports the same
pipelines in-process — the request/response shapes are identical either way, so
switching between the two is a configuration change.

The service is stateless and holds no database connection.  The caller supplies
the reference species it wants matched against, which keeps the model server
free of the platform's schema and lets a study use a restricted species list.

Run with::

    uvicorn ai.service.main:app --port 8001
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import Body, FastAPI, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel, Field

from ai.anomaly.detector import BiodiversityAnomalyDetector, candidate_causes
from ai.audio.pipeline import build_audio_pipeline
from ai.config import get_config
from ai.datasets.reference_species import REFERENCE_SPECIES, species_references
from ai.multimodal.fusion import FusionWeights, fuse_predictions
from ai.preprocessing.audio import AudioValidationError
from ai.preprocessing.image import ImageValidationError
from ai.schema import Candidate, Prediction, SpeciesReference
from ai.vision.pipeline import build_vision_pipeline

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ai.service")

app = FastAPI(
    title="VANRAKSHA AI Engine",
    version="1.0.0",
    description=(
        "Species identification from images and audio, multimodal fusion, and "
        "unusual-pattern detection. Every identification is AI-assisted and "
        "requires expert verification."
    ),
)


# --------------------------------------------------------------------------- #
# request models
# --------------------------------------------------------------------------- #
class SpeciesReferenceIn(BaseModel):
    species_id: int | None = None
    label: str
    scientific_name: str | None = None
    category: str = "OTHER"
    visual_traits: dict[str, Any] = Field(default_factory=dict)
    acoustic_signature: dict[str, Any] = Field(default_factory=dict)

    def to_reference(self) -> SpeciesReference:
        return SpeciesReference(
            species_id=self.species_id,
            label=self.label,
            scientific_name=self.scientific_name,
            category=self.category,
            visual_traits=self.visual_traits,
            acoustic_signature=self.acoustic_signature,
        )


class CandidateIn(BaseModel):
    species_id: int | None = None
    label: str
    scientific_name: str | None = None
    confidence: float = Field(ge=0, le=1)


class PredictionIn(BaseModel):
    modality: str
    model_name: str = "external"
    model_version: str = "0"
    predicted_label: str
    confidence: float = Field(ge=0, le=1)
    is_uncertain: bool = False
    species_id: int | None = None
    top_k: list[CandidateIn] = Field(default_factory=list)

    def to_prediction(self) -> Prediction:
        return Prediction(
            modality=self.modality,
            model_name=self.model_name,
            model_version=self.model_version,
            label=self.predicted_label,
            confidence=self.confidence,
            is_uncertain=self.is_uncertain,
            species_id=self.species_id,
            top_k=tuple(
                Candidate(
                    species_id=c.species_id,
                    label=c.label,
                    scientific_name=c.scientific_name,
                    confidence=c.confidence,
                )
                for c in self.top_k
            ),
        )


class FuseRequest(BaseModel):
    image: PredictionIn | None = None
    audio: PredictionIn | None = None
    context_prior: dict[str, float] | None = None
    image_weight: float = Field(default=0.6, ge=0, le=1)
    audio_weight: float = Field(default=0.4, ge=0, le=1)


class AnomalyRequest(BaseModel):
    metric: str = "detections.total"
    #: ``{"2026-07-01": 12, "2026-07-02": 9, ...}``
    daily_counts: dict[str, float]
    window_days: int | None = Field(default=None, ge=1, le=90)
    baseline_days: int | None = Field(default=None, ge=14, le=1095)
    z_threshold: float | None = Field(default=None, ge=1.0, le=10.0)
    device_gap: bool = False


# --------------------------------------------------------------------------- #
# pipeline construction
# --------------------------------------------------------------------------- #
def _references(payload: list[SpeciesReferenceIn] | None) -> list[SpeciesReference]:
    """Use the caller's species list, or fall back to the shipped catalogue."""
    if payload:
        return [item.to_reference() for item in payload]
    return species_references()


def _pipelines(references: list[SpeciesReference]):
    config = get_config()
    return build_vision_pipeline(references, config), build_audio_pipeline(references, config)


# --------------------------------------------------------------------------- #
# routes
# --------------------------------------------------------------------------- #
@app.get("/", tags=["meta"])
def root() -> dict[str, str]:
    return {"status": "ok", "service": "VANRAKSHA AI Engine", "version": app.version}


@app.get("/health", tags=["meta"])
def health() -> dict[str, Any]:
    vision, audio = _pipelines(species_references())
    return {
        "status": "ok",
        "service": "VANRAKSHA AI Engine",
        "version": app.version,
        "vision_backend": vision.backend_name,
        "audio_backend": audio.backend_name,
        "reference_species": len(REFERENCE_SPECIES),
    }


@app.get("/models", tags=["meta"])
def models() -> dict[str, Any]:
    vision, audio = _pipelines(species_references())
    return {
        "vision": vision.info(),
        "audio": audio.info(),
        "anomaly_methods": ["ROBUST_Z", "ISOLATION_FOREST", "ENSEMBLE"],
        "fusion_available": True,
    }


@app.post("/predict/image", tags=["inference"])
async def predict_image(
    file: UploadFile = File(..., description="JPEG/PNG/WebP photograph"),
    references: str | None = Form(
        default=None, description="Optional JSON array of species references"
    ),
) -> dict[str, Any]:
    payload = _parse_references(references)
    vision, _ = _pipelines(_references(payload))
    data = await file.read()
    try:
        prediction = vision.predict(data)
    except ImageValidationError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    return prediction.as_dict()


@app.post("/predict/audio", tags=["inference"])
async def predict_audio(
    file: UploadFile = File(..., description="WAV recording (FLAC/OGG/MP3 need soundfile)"),
    references: str | None = Form(default=None),
) -> dict[str, Any]:
    payload = _parse_references(references)
    _, audio = _pipelines(_references(payload))
    data = await file.read()
    try:
        prediction = audio.predict(data, filename=file.filename)
    except AudioValidationError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    return prediction.as_dict()


@app.post("/analyse/audio", tags=["inference"])
async def analyse_audio(file: UploadFile = File(...)) -> dict[str, Any]:
    """Acoustic measurements only — no species claim. Used for spectrogram views."""
    _, audio = _pipelines(species_references())
    data = await file.read()
    try:
        decoded, features = audio.analyse(data, filename=file.filename)
    except AudioValidationError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    return {
        "sample_rate": decoded.sample_rate,
        "duration_seconds": round(decoded.duration_seconds, 3),
        "channels_original": decoded.channels_original,
        "source_format": decoded.source_format,
        "features": features.as_dict(),
    }


@app.post("/fuse", tags=["inference"])
def fuse(request: FuseRequest = Body(...)) -> dict[str, Any]:
    if request.image is None and request.audio is None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "provide at least one of 'image' or 'audio'",
        )
    prediction = fuse_predictions(
        request.image.to_prediction() if request.image else None,
        request.audio.to_prediction() if request.audio else None,
        context_prior=request.context_prior,
        weights=FusionWeights(request.image_weight, request.audio_weight),
    )
    return prediction.as_dict()


@app.post("/anomaly/score", tags=["analysis"])
def anomaly_score(request: AnomalyRequest = Body(...)) -> dict[str, Any]:
    from datetime import date

    try:
        counts = {date.fromisoformat(k): float(v) for k, v in request.daily_counts.items()}
    except ValueError as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"daily_counts keys must be ISO dates: {exc}",
        ) from exc

    findings = BiodiversityAnomalyDetector().detect(
        request.metric,
        counts,
        window_days=request.window_days,
        baseline_days=request.baseline_days,
        z_threshold=request.z_threshold,
    )
    return {
        "metric": request.metric,
        "evaluated_windows": len(findings),
        "findings": [
            {
                **finding.as_dict(),
                "candidate_causes": candidate_causes(
                    finding, device_gap=request.device_gap
                ),
            }
            for finding in findings
        ],
        "note": (
            "Flagged windows indicate a deviation from the recent baseline and require "
            "human investigation; the detector does not infer a cause."
        ),
    }


def _parse_references(raw: str | None) -> list[SpeciesReferenceIn] | None:
    if not raw:
        return None
    import json

    try:
        decoded = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, f"'references' is not valid JSON: {exc}"
        ) from exc
    if not isinstance(decoded, list):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, "'references' must be a JSON array"
        )
    try:
        return [SpeciesReferenceIn.model_validate(item) for item in decoded]
    except Exception as exc:  # pydantic validation error
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, f"invalid species reference: {exc}"
        ) from exc
