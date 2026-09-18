"""The backend's gateway to the AI engine.

Two deployment shapes, one interface:

* **in-process** (default) — the :mod:`ai` package is imported and the pipelines
  run inside the API worker.  Simple to develop against and to test.
* **microservice** — when ``AI_SERVICE_URL`` is set, inference is delegated over
  HTTP to ``ai.service.main``, so the model server can be scaled or
  GPU-scheduled independently.

The reference species passed to the engine always come from the live ``species``
table, so adding a species through the admin UI immediately widens what the
baselines can match — there is no separate model-side species list to keep in
sync.
"""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import BACKEND_ROOT, settings
from app.core.errors import AIEngineError, ValidationError
from app.models.species import Species

logger = logging.getLogger(__name__)

REPO_ROOT = BACKEND_ROOT.parent


def _ensure_ai_importable() -> None:
    """Put the repository root on ``sys.path`` so ``import ai`` resolves.

    The AI engine is a sibling package rather than an installed distribution, so
    that a checkout runs without a packaging step. Installing it (``pip install
    -e .`` from the repo root) also works and makes this a no-op.
    """
    root = str(REPO_ROOT)
    if root not in sys.path and (Path(root) / "ai" / "__init__.py").exists():
        sys.path.insert(0, root)


_ensure_ai_importable()


@dataclass(frozen=True)
class EngineInfo:
    vision: dict
    audio: dict
    anomaly_methods: list[str]
    fusion_available: bool
    mode: str


def species_references(db: Session) -> list:
    """Build AI reference objects from every species in the database."""
    _ensure_ai_importable()
    from ai.schema import SpeciesReference

    rows = db.execute(select(Species).order_by(Species.id)).scalars().all()
    return [
        SpeciesReference(
            species_id=row.id,
            label=row.common_name,
            scientific_name=row.scientific_name,
            category=str(row.category),
            visual_traits=row.visual_traits or {},
            acoustic_signature=row.acoustic_signature or {},
        )
        for row in rows
    ]


@lru_cache(maxsize=8)
def _ai_config():
    _ensure_ai_importable()
    from ai.config import AIConfig

    return AIConfig(
        vision_backend=settings.ai_vision_backend,
        audio_backend=settings.ai_audio_backend,
        vision_weights=settings.ai_vision_weights,
        audio_weights=settings.ai_audio_weights,
        min_confidence=settings.ai_min_confidence,
        uncertain_margin=settings.ai_uncertain_margin,
        baseline_days=settings.anomaly_baseline_days,
        window_days=settings.anomaly_window_days,
        z_threshold=settings.anomaly_z_threshold,
        contamination=settings.anomaly_contamination,
    )


class AIEngine:
    """Facade over the AI pipelines for one request."""

    def __init__(self, db: Session) -> None:
        self._db = db
        self._references = species_references(db)
        self._remote = bool(settings.ai_service_url)
        self._vision = None
        self._audio = None

    # ------------------------------------------------------------ properties
    @property
    def mode(self) -> str:
        return "microservice" if self._remote else "in-process"

    @property
    def vision(self):
        if self._vision is None:
            _ensure_ai_importable()
            from ai.vision.pipeline import build_vision_pipeline

            self._vision = build_vision_pipeline(self._references, _ai_config())
        return self._vision

    @property
    def audio(self):
        if self._audio is None:
            _ensure_ai_importable()
            from ai.audio.pipeline import build_audio_pipeline

            self._audio = build_audio_pipeline(self._references, _ai_config())
        return self._audio

    def info(self) -> EngineInfo:
        return EngineInfo(
            vision=self.vision.info(),
            audio=self.audio.info(),
            anomaly_methods=["ROBUST_Z", "ISOLATION_FOREST", "ENSEMBLE"],
            fusion_available=True,
            mode=self.mode,
        )

    # ------------------------------------------------------------- inference
    def predict_image(self, data: bytes):
        _ensure_ai_importable()
        from ai.preprocessing.image import ImageValidationError

        if self._remote:
            return self._remote_predict("image", data, "upload.jpg")
        try:
            return self.vision.predict(data)
        except ImageValidationError as exc:
            raise ValidationError(str(exc)) from exc

    def predict_audio(self, data: bytes, filename: str | None = None):
        _ensure_ai_importable()
        from ai.preprocessing.audio import AudioValidationError

        if self._remote:
            return self._remote_predict("audio", data, filename or "upload.wav")
        try:
            return self.audio.predict(data, filename=filename)
        except AudioValidationError as exc:
            raise ValidationError(str(exc)) from exc

    def analyse_audio(self, data: bytes, filename: str | None = None):
        """Acoustic measurements without any species claim."""
        _ensure_ai_importable()
        from ai.preprocessing.audio import AudioValidationError

        try:
            return self.audio.analyse(data, filename=filename)
        except AudioValidationError as exc:
            raise ValidationError(str(exc)) from exc

    def fuse(self, image_prediction, audio_prediction, *, context_prior=None):
        _ensure_ai_importable()
        from ai.multimodal.fusion import FusionWeights, fuse_predictions

        config = _ai_config()
        return fuse_predictions(
            image_prediction,
            audio_prediction,
            context_prior=context_prior,
            weights=FusionWeights(config.image_weight, config.audio_weight),
            config=config,
        )

    def context_prior_for_zone(self, zone_id: int | None, hour: int | None = None):
        """Empirical prior from what this zone has actually recorded before.

        Only *expert-verified* observations contribute, so the prior cannot be
        bootstrapped from the model's own unverified guesses — otherwise a single
        early misidentification would keep reinforcing itself.
        """
        if zone_id is None:
            return None
        _ensure_ai_importable()
        from sqlalchemy import func

        from ai.multimodal.fusion import context_prior_from_history
        from app.models.enums import VerificationStatus
        from app.models.observation import Observation

        statement = (
            select(Species.common_name, func.count(Observation.id))
            .join(
                Observation,
                (Observation.verified_species_id == Species.id)
                | (
                    (Observation.species_id == Species.id)
                    & (Observation.verification_status == VerificationStatus.CONFIRMED)
                ),
            )
            .where(
                Observation.zone_id == zone_id,
                Observation.verification_status.in_(
                    [VerificationStatus.CONFIRMED, VerificationStatus.CORRECTED]
                ),
            )
            .group_by(Species.common_name)
        )
        history = {name: float(count) for name, count in db_rows(self._db, statement)}
        if not history:
            return None
        config = _ai_config()
        return context_prior_from_history(history, strength=config.context_strength)

    # -------------------------------------------------------------- remote
    def _remote_predict(self, modality: str, data: bytes, filename: str):
        import httpx

        _ensure_ai_importable()
        from ai.schema import Candidate, Detection, Prediction

        url = f"{settings.ai_service_url.rstrip('/')}/predict/{modality}"
        references = [
            {
                "species_id": r.species_id,
                "label": r.label,
                "scientific_name": r.scientific_name,
                "category": r.category,
                "visual_traits": r.visual_traits,
                "acoustic_signature": r.acoustic_signature,
            }
            for r in self._references
        ]
        try:
            import json

            response = httpx.post(
                url,
                files={"file": (filename, data)},
                data={"references": json.dumps(references)},
                timeout=settings.ai_service_timeout_seconds,
            )
            if response.status_code == 422:
                raise ValidationError(response.json().get("detail", "invalid media"))
            response.raise_for_status()
            payload = response.json()
        except ValidationError:
            raise
        except Exception as exc:
            logger.exception("AI microservice call failed: %s", url)
            raise AIEngineError(
                "The AI engine did not respond. The observation was not analysed."
            ) from exc

        return Prediction(
            modality=payload["modality"],
            model_name=payload["model_name"],
            model_version=payload["model_version"],
            label=payload["predicted_label"],
            confidence=float(payload["confidence"]),
            is_uncertain=bool(payload["is_uncertain"]),
            species_id=payload.get("species_id"),
            scientific_name=payload.get("scientific_name"),
            top_k=tuple(
                Candidate(
                    species_id=c.get("species_id"),
                    label=c["label"],
                    scientific_name=c.get("scientific_name"),
                    confidence=float(c["confidence"]),
                )
                for c in payload.get("top_k") or []
            ),
            detections=tuple(
                Detection(
                    bbox=tuple(d["bbox"]),  # type: ignore[arg-type]
                    score=float(d["score"]),
                    label=d.get("label"),
                )
                for d in payload.get("detections") or []
            ),
            diagnostics=payload.get("diagnostics") or {},
            latency_ms=payload.get("latency_ms"),
        )


def db_rows(db: Session, statement):
    return db.execute(statement).all()


def get_ai_engine(db: Session) -> AIEngine:
    return AIEngine(db)
