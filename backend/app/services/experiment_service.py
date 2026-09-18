"""The research experiment module.

Experiments are first-class records: a research question, a reproducible
configuration, and one run per variant with its metrics. Two dataset modes:

``synthetic``
    The seeded reference benchmark in :mod:`ai.datasets.synthetic`. Reproducible
    anywhere, and the only mode available before enough field data exists.

``verified``
    Expert-verified observations from this deployment. The honest mode, and the
    one whose numbers can be reported as platform performance — but it needs a
    reasonable number of verified records with usable media before it says
    anything, so it refuses rather than reporting a meaningless result.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from fastapi import Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.core.errors import ConflictError, NotFoundError, ValidationError
from app.models.enums import ExperimentStatus, VerificationStatus
from app.models.experiment import Experiment, ExperimentRun
from app.models.observation import Observation
from app.models.user import User
from app.schemas.experiment import (
    VARIANTS,
    ExperimentCreate,
    ExperimentExecuteRequest,
    ExperimentRead,
    ExperimentReport,
    VariantComparison,
)
from app.services import audit
from app.services.ai_client import AIEngine, _ensure_ai_importable

logger = logging.getLogger(__name__)

#: Below this many usable verified observations the ``verified`` dataset mode is
#: refused: a "comparison" on a handful of records is noise with a decimal point.
MIN_VERIFIED_SAMPLES = 40


def get_experiment(db: Session, experiment_id: int) -> Experiment:
    experiment = db.execute(
        select(Experiment)
        .options(selectinload(Experiment.runs))
        .where(Experiment.id == experiment_id)
    ).scalar_one_or_none()
    if experiment is None:
        raise NotFoundError(f"No experiment with id {experiment_id}.")
    return experiment


def list_experiments(db: Session) -> list[ExperimentRead]:
    rows = (
        db.execute(
            select(Experiment)
            .options(selectinload(Experiment.runs))
            .order_by(Experiment.created_at.desc())
        )
        .scalars()
        .all()
    )
    return [ExperimentRead.model_validate(row) for row in rows]


def create_experiment(
    db: Session, payload: ExperimentCreate, *, actor: User, request: Request | None = None
) -> Experiment:
    name = payload.name.strip()
    if db.execute(select(Experiment).where(Experiment.name == name)).scalar_one_or_none():
        raise ConflictError(f"An experiment named '{name}' already exists.")
    experiment = Experiment(
        name=name,
        research_question=payload.research_question.strip(),
        hypothesis=(payload.hypothesis or "").strip() or None,
        config=payload.config,
        status=ExperimentStatus.DRAFT,
        created_by_id=actor.id,
    )
    db.add(experiment)
    db.flush()
    audit.record(
        db,
        "experiment.create",
        user=actor,
        entity="experiment",
        entity_id=experiment.id,
        request=request,
        context={"name": name},
    )
    db.commit()
    return get_experiment(db, experiment.id)


def _synthetic_dataset(engine: AIEngine, sample_count: int, seed: int):
    _ensure_ai_importable()
    from ai.datasets.reference_species import REFERENCE_SPECIES
    from ai.datasets.synthetic import generate_dataset

    notes = {
        row["common_name"]: row.get("research_notes") or {} for row in REFERENCE_SPECIES
    }
    references = engine.vision.classes or engine.audio.classes
    return generate_dataset(
        references, sample_count=sample_count, seed=seed, notes_by_label=notes
    )


def _verified_dataset(db: Session, engine: AIEngine, sample_count: int, seed: int):
    """Build an evaluation set from expert-verified observations with media."""
    _ensure_ai_importable()
    import random

    import numpy as np

    from ai.datasets.synthetic import SyntheticSample
    from ai.preprocessing.image import load_image

    rows = (
        db.execute(
            select(Observation)
            .options(selectinload(Observation.verified_species), selectinload(Observation.media))
            .where(
                Observation.verification_status.in_(
                    [VerificationStatus.CONFIRMED, VerificationStatus.CORRECTED]
                ),
                Observation.verified_species_id.is_not(None),
            )
            .order_by(Observation.id)
        )
        .scalars()
        .all()
    )
    usable = [row for row in rows if row.image_url or row.audio_url]
    if len(usable) < MIN_VERIFIED_SAMPLES:
        raise ValidationError(
            f"Only {len(usable)} expert-verified observations carry media; at least "
            f"{MIN_VERIFIED_SAMPLES} are needed before a field comparison means "
            "anything. Use dataset='synthetic' until the verified set grows."
        )

    from app.services.storage import LocalStorage, get_storage

    storage = get_storage()
    rng = random.Random(seed)
    rng.shuffle(usable)
    samples: list[SyntheticSample] = []

    for observation in usable[:sample_count]:
        image = None
        audio_features = None
        for asset in observation.media:
            if not isinstance(storage, LocalStorage):  # pragma: no cover
                continue
            path = storage._path_for(asset.storage_key)
            if not path.exists():
                continue
            try:
                if str(asset.kind) == "IMAGE" and image is None:
                    image = load_image(str(path), size=160).astype(np.float32)
                elif str(asset.kind) == "AUDIO" and audio_features is None:
                    _, audio_features = engine.audio.analyse(path.read_bytes(),
                                                             filename=path.name)
            except Exception:  # pragma: no cover - a corrupt file must not stop the run
                logger.warning("skipping unreadable media %s", asset.storage_key, exc_info=True)
        if image is None and audio_features is None:
            continue
        samples.append(
            SyntheticSample(
                label=observation.verified_species.common_name,
                species_id=observation.verified_species_id,
                image=image,
                audio_features=audio_features,
                difficulty=0.0,
                context={
                    "hour": observation.observed_at.hour,
                    "category": str(observation.verified_species.category),
                    "confusable": False,
                    "observation_id": observation.id,
                },
            )
        )

    if len(samples) < MIN_VERIFIED_SAMPLES:
        raise ValidationError(
            f"Only {len(samples)} verified observations had readable media; at least "
            f"{MIN_VERIFIED_SAMPLES} are needed."
        )
    return samples


def execute_experiment(
    db: Session,
    experiment_id: int,
    payload: ExperimentExecuteRequest,
    *,
    engine: AIEngine,
    actor: User,
    request: Request | None = None,
) -> ExperimentReport:
    """Run the modality comparison and persist one run per variant."""
    _ensure_ai_importable()
    from ai.evaluation.experiment import compare_variants

    experiment = get_experiment(db, experiment_id)
    unknown = [v for v in payload.variants if v not in VARIANTS]
    if unknown:
        raise ValidationError(
            f"Unknown variant(s): {', '.join(unknown)}. Valid variants: "
            f"{', '.join(VARIANTS)}."
        )

    experiment.status = ExperimentStatus.RUNNING
    db.commit()

    started = datetime.now(UTC)
    try:
        if payload.dataset == "verified":
            samples = _verified_dataset(db, engine, payload.sample_count, payload.random_seed)
        else:
            samples = _synthetic_dataset(engine, payload.sample_count, payload.random_seed)
        report = compare_variants(
            samples,
            vision=engine.vision,
            audio=engine.audio,
            variants=payload.variants,
            random_seed=payload.random_seed,
        )
    except Exception:
        experiment.status = ExperimentStatus.FAILED
        db.commit()
        raise
    finished = datetime.now(UTC)

    # Replace previous runs for the same configuration so the stored history is
    # one row per variant per configuration rather than an append-only pile.
    for existing in list(experiment.runs):
        if existing.variant in payload.variants and existing.random_seed == payload.random_seed:
            db.delete(existing)

    comparisons: list[VariantComparison] = []
    for variant, result in report.results.items():
        metrics = result.metrics()
        db.add(
            ExperimentRun(
                experiment_id=experiment.id,
                variant=variant,
                metrics=metrics,
                per_class_metrics={
                    "average_precision": result.per_class_average_precision,
                    "f1": result.report.f1,
                    "support": result.report.support,
                },
                confusion_matrix={
                    "labels": result.confusion_labels,
                    "matrix": result.report.matrix,
                },
                sample_count=result.sample_count,
                random_seed=payload.random_seed,
                notes=f"dataset={payload.dataset}",
                started_at=started,
                finished_at=finished,
            )
        )
        comparisons.append(
            VariantComparison(
                variant=variant,
                accuracy=metrics["accuracy"],
                macro_precision=metrics["macro_precision"],
                macro_recall=metrics["macro_recall"],
                macro_f1=metrics["macro_f1"],
                mean_average_precision=metrics["mean_average_precision"],
                expected_calibration_error=metrics["expected_calibration_error"],
                uncertain_share=metrics["uncertain_share"],
                mean_latency_ms=metrics["mean_latency_ms"],
            )
        )

    experiment.status = ExperimentStatus.COMPLETED
    experiment.config = {
        **(experiment.config or {}),
        "dataset": payload.dataset,
        "sample_count": report.sample_count,
        "random_seed": payload.random_seed,
        "variants": list(payload.variants),
        "vision_model": engine.vision.info(),
        "audio_model": engine.audio.info(),
        "last_run_at": finished.isoformat(),
    }
    audit.record(
        db,
        "experiment.run",
        user=actor,
        entity="experiment",
        entity_id=experiment.id,
        request=request,
        context={
            "dataset": payload.dataset,
            "variants": list(payload.variants),
            "best_variant": report.best_variant,
        },
    )
    db.commit()

    return ExperimentReport(
        experiment_id=experiment.id,
        name=experiment.name,
        research_question=experiment.research_question,
        dataset=payload.dataset,
        sample_count=report.sample_count,
        random_seed=payload.random_seed,
        comparisons=comparisons,
        best_variant=report.best_variant,
        fusion_gain_f1=report.fusion_gain_f1,
        conclusion=report.conclusion,
    )


def delete_experiment(
    db: Session, experiment_id: int, *, actor: User, request: Request | None = None
) -> None:
    experiment = get_experiment(db, experiment_id)
    audit.record(
        db,
        "experiment.delete",
        user=actor,
        entity="experiment",
        entity_id=experiment_id,
        request=request,
        context={"name": experiment.name},
    )
    db.delete(experiment)
    db.commit()


def verified_dataset_size(db: Session) -> dict[str, int]:
    """How close the deployment is to supporting a field comparison."""
    verified = db.execute(
        select(func.count(Observation.id)).where(
            Observation.verification_status.in_(
                [VerificationStatus.CONFIRMED, VerificationStatus.CORRECTED]
            )
        )
    ).scalar_one()
    with_media = db.execute(
        select(func.count(Observation.id)).where(
            Observation.verification_status.in_(
                [VerificationStatus.CONFIRMED, VerificationStatus.CORRECTED]
            ),
            Observation.image_url.is_not(None) | Observation.audio_url.is_not(None),
        )
    ).scalar_one()
    return {
        "verified_observations": int(verified),
        "verified_with_media": int(with_media),
        "minimum_required": MIN_VERIFIED_SAMPLES,
    }
