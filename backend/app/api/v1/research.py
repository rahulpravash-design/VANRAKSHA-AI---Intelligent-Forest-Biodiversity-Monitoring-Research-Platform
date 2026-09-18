"""The research experiment module.

This is where the platform's headline research question is answered — does
multimodal AI identify species better than a single modality? — with a
comparison rather than an assertion.
"""

from __future__ import annotations

from fastapi import APIRouter, Body, Request, status

from app.core.deps import CurrentUser, DbSession, RecorderUser
from app.schemas.common import Message
from app.schemas.experiment import (
    VARIANTS,
    ExperimentCreate,
    ExperimentExecuteRequest,
    ExperimentRead,
    ExperimentReport,
)
from app.services import experiment_service
from app.services.ai_client import AIEngine

router = APIRouter(prefix="/research", tags=["research"])


@router.get(
    "/variants",
    response_model=dict,
    summary="The comparison variants and the dataset modes available",
)
def variants(db: DbSession, _user: CurrentUser) -> dict:
    """Also reports how close this deployment is to supporting a *field*
    comparison, rather than only the reproducible synthetic benchmark."""
    return {
        "variants": {
            "image_only": "Photograph alone",
            "audio_only": "Recording alone",
            "image_audio": "Both, reliability-weighted late fusion",
            "image_audio_context": "Both, plus a time-of-day and zone prior",
        },
        "datasets": {
            "synthetic": (
                "Seeded reference benchmark. Reproducible anywhere; establishes the "
                "relative ordering of the variants, not field accuracy."
            ),
            "verified": (
                "Expert-verified observations from this deployment. The only mode whose "
                "numbers describe real performance."
            ),
        },
        "verified_dataset": experiment_service.verified_dataset_size(db),
        "valid_variant_names": list(VARIANTS),
    }


@router.get("", response_model=list[ExperimentRead], summary="List experiments")
def list_experiments(db: DbSession, _user: CurrentUser) -> list[ExperimentRead]:
    return experiment_service.list_experiments(db)


@router.post(
    "",
    response_model=ExperimentRead,
    status_code=status.HTTP_201_CREATED,
    summary="Define an experiment",
    responses={409: {"description": "An experiment with this name already exists"}},
)
def create_experiment(
    db: DbSession, request: Request, actor: RecorderUser, payload: ExperimentCreate = Body(...)
) -> ExperimentRead:
    experiment = experiment_service.create_experiment(
        db, payload, actor=actor, request=request
    )
    return ExperimentRead.model_validate(experiment)


@router.get(
    "/{experiment_id}",
    response_model=ExperimentRead,
    summary="Read an experiment and its runs",
)
def get_experiment(db: DbSession, _user: CurrentUser, experiment_id: int) -> ExperimentRead:
    return ExperimentRead.model_validate(experiment_service.get_experiment(db, experiment_id))


@router.post(
    "/{experiment_id}/run",
    response_model=ExperimentReport,
    summary="Run the modality comparison",
    responses={
        422: {"description": "Unknown variant, or not enough verified data for that mode"}
    },
)
def run_experiment(
    db: DbSession,
    request: Request,
    actor: RecorderUser,
    experiment_id: int,
    payload: ExperimentExecuteRequest = Body(default=ExperimentExecuteRequest()),
) -> ExperimentReport:
    """Scores each variant on one identical split with one seed.

    The contextual prior for `image_audio_context` is fitted on a disjoint slice
    of the data, and abstentions are reported as coverage alongside selective
    accuracy — a variant that answers less often does not get to look better for
    it.
    """
    return experiment_service.execute_experiment(
        db, experiment_id, payload, engine=AIEngine(db), actor=actor, request=request
    )


@router.delete("/{experiment_id}", response_model=Message, summary="Delete an experiment")
def delete_experiment(
    db: DbSession, request: Request, actor: RecorderUser, experiment_id: int
) -> Message:
    experiment_service.delete_experiment(db, experiment_id, actor=actor, request=request)
    return Message(detail="Experiment and its runs deleted.")
