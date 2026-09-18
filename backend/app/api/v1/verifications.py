"""Expert verification endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Body, Query, Request, status

from app.core.deps import CurrentUser, DbSession, ExpertUser
from app.schemas.common import Page
from app.schemas.verification import (
    ReviewQueueItem,
    VerificationCreate,
    VerificationRead,
    VerificationStats,
)
from app.services import anomaly_service, observation_service, verification_service

router = APIRouter(prefix="/verifications", tags=["verification"])


@router.get(
    "/queue",
    response_model=Page[ReviewQueueItem],
    summary="Observations awaiting an expert decision",
)
def review_queue(
    db: DbSession,
    expert: ExpertUser,
    zone_id: int | None = Query(default=None),
    category: str | None = Query(default=None),
    only_with_media: bool = Query(default=False),
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> Page[ReviewQueueItem]:
    """Oldest first, so records are not abandoned by a newest-first queue."""
    return verification_service.review_queue(
        db,
        viewer=expert,
        limit=limit,
        offset=offset,
        zone_id=zone_id,
        category=category,
        only_with_media=only_with_media,
    )


@router.get("/stats", response_model=VerificationStats, summary="AI-versus-expert agreement")
def stats(db: DbSession, _user: CurrentUser) -> VerificationStats:
    """Agreement over reviewed observations only — review-conditional, as the
    response's `note` states. Held-out performance lives under `/research`."""
    return verification_service.agreement_stats(db)


@router.get("/experts", response_model=list[dict], summary="Review volume per expert")
def experts(db: DbSession, _expert: ExpertUser) -> list[dict]:
    return verification_service.expert_leaderboard(db)


@router.get(
    "/observation/{observation_id}",
    response_model=list[VerificationRead],
    summary="Verification history for one observation",
)
def history(db: DbSession, _user: CurrentUser, observation_id: int) -> list[VerificationRead]:
    return verification_service.verification_history(db, observation_id)


@router.get("", response_model=Page[VerificationRead], summary="List verification decisions")
def list_verifications(
    db: DbSession,
    _user: CurrentUser,
    expert_id: int | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> Page[VerificationRead]:
    return verification_service.list_verifications(
        db, expert_id=expert_id, limit=limit, offset=offset
    )


@router.post(
    "/observation/{observation_id}",
    response_model=VerificationRead,
    status_code=status.HTTP_201_CREATED,
    summary="Confirm, reject or correct an identification",
    responses={
        403: {"description": "Expert or administrator role required"},
        422: {"description": "A correction needs a species, and must differ from the report"},
    },
)
def submit(
    db: DbSession,
    request: Request,
    expert: ExpertUser,
    observation_id: int,
    payload: VerificationCreate = Body(...),
) -> VerificationRead:
    """Record an expert decision.

    The decision sets the observation's final species and stores what the model
    predicted at review time, which is what makes AI-versus-expert agreement
    measurable later. A confirmed threatened-species record also raises an
    informational notice for the officers responsible for that zone.
    """
    verification = verification_service.submit_verification(
        db, observation_id, payload, expert=expert, request=request
    )
    observation = observation_service.get_observation(db, observation_id)
    anomaly_service.threatened_species_notice(db, observation)
    return VerificationRead.model_validate(verification)
