"""Expert verification — the workflow that turns model output into data.

The review queue is ordered so the observations that most need a human decision
come first, and every decision is stored with what the AI said at review time,
which is what makes AI-versus-expert agreement measurable afterwards.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import Request
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.core.errors import NotFoundError, ValidationError
from app.models.enums import (
    DECISION_TO_STATUS,
    VerificationDecision,
    VerificationStatus,
)
from app.models.observation import Observation
from app.models.species import Species
from app.models.user import User
from app.models.verification import ExpertVerification
from app.schemas.common import Page
from app.schemas.species import SpeciesSummary
from app.schemas.verification import (
    AgreementCell,
    ReviewQueueItem,
    VerificationCreate,
    VerificationRead,
    VerificationStats,
)
from app.services import audit, observation_service


def review_queue(
    db: Session,
    *,
    viewer: User,
    limit: int = 25,
    offset: int = 0,
    zone_id: int | None = None,
    category: str | None = None,
    only_with_media: bool = False,
) -> Page[ReviewQueueItem]:
    """Observations awaiting an expert decision, oldest first.

    Oldest-first is deliberate: a newest-first queue silently abandons the
    records nobody happened to review on the day they arrived.
    """
    statement = (
        select(Observation)
        .options(
            selectinload(Observation.species),
            selectinload(Observation.zone),
            selectinload(Observation.ai_predicted_species),
            selectinload(Observation.verified_species),
        )
        .where(Observation.verification_status == VerificationStatus.PENDING)
    )
    if zone_id is not None:
        statement = statement.where(Observation.zone_id == zone_id)
    if category:
        statement = statement.where(
            Observation.species_id.in_(
                select(Species.id).where(Species.category == category)
            )
        )
    if only_with_media:
        statement = statement.where(
            or_(Observation.image_url.is_not(None), Observation.audio_url.is_not(None))
        )

    total = db.execute(select(func.count()).select_from(statement.subquery())).scalar_one()
    rows = (
        db.execute(
            statement.order_by(Observation.created_at.asc()).limit(limit).offset(offset)
        )
        .scalars()
        .all()
    )
    now = datetime.now(UTC)
    items: list[ReviewQueueItem] = []
    for row in rows:
        created = row.created_at if row.created_at.tzinfo else row.created_at.replace(tzinfo=UTC)
        items.append(
            ReviewQueueItem(
                observation=observation_service.serialise_observation(row, viewer),
                ai_predicted_label=row.ai_prediction,
                ai_confidence=row.ai_confidence,
                reported_species=SpeciesSummary.model_validate(row.species)
                if row.species
                else None,
                waiting_days=round((now - created).total_seconds() / 86400.0, 2),
                has_image=bool(row.image_url),
                has_audio=bool(row.audio_url),
            )
        )
    return Page[ReviewQueueItem](
        items=items, total=int(total), limit=limit, offset=offset
    )


def submit_verification(
    db: Session,
    observation_id: int,
    payload: VerificationCreate,
    *,
    expert: User,
    request: Request | None = None,
) -> ExpertVerification:
    """Record an expert decision and update the observation's final species."""
    observation = observation_service.get_observation(db, observation_id)

    corrected: Species | None = None
    if payload.decision == VerificationDecision.CORRECT:
        corrected = db.get(Species, payload.corrected_species_id)
        if corrected is None:
            raise ValidationError(f"No species with id {payload.corrected_species_id}.")
        if corrected.id == observation.species_id:
            raise ValidationError(
                "The corrected species is the same as the reported species; "
                "use CONFIRM instead."
            )
    if payload.decision == VerificationDecision.CONFIRM and observation.species_id is None:
        raise ValidationError(
            "This observation has no reported species to confirm. Use CORRECT and "
            "supply the species."
        )

    verification = ExpertVerification(
        observation_id=observation.id,
        expert_id=expert.id,
        decision=payload.decision,
        corrected_species_id=corrected.id if corrected else None,
        previous_species_id=observation.species_id,
        # Snapshot the model's opinion so agreement can be measured later even
        # after the model is retrained and re-run.
        ai_predicted_label=observation.ai_prediction,
        ai_confidence=observation.ai_confidence,
        comments=payload.comments,
        verified_at=datetime.now(UTC),
    )
    db.add(verification)

    observation.verification_status = DECISION_TO_STATUS[payload.decision]
    observation.verified_at = verification.verified_at
    if payload.decision == VerificationDecision.CONFIRM:
        observation.verified_species_id = observation.species_id
    elif payload.decision == VerificationDecision.CORRECT:
        observation.verified_species_id = corrected.id if corrected else None
    else:
        # REJECT and UNCERTAIN leave no verified species behind.
        observation.verified_species_id = None

    audit.record(
        db,
        "verification.submit",
        user=expert,
        entity="observation",
        entity_id=observation.id,
        request=request,
        context={
            "decision": str(payload.decision),
            "previous_species_id": verification.previous_species_id,
            "corrected_species_id": verification.corrected_species_id,
            "ai_predicted_label": verification.ai_predicted_label,
        },
    )
    db.commit()
    db.refresh(verification)
    return verification


def list_verifications(
    db: Session,
    *,
    observation_id: int | None = None,
    expert_id: int | None = None,
    limit: int = 50,
    offset: int = 0,
) -> Page[VerificationRead]:
    statement = select(ExpertVerification).options(
        selectinload(ExpertVerification.expert),
        selectinload(ExpertVerification.corrected_species),
        selectinload(ExpertVerification.previous_species),
    )
    if observation_id is not None:
        statement = statement.where(ExpertVerification.observation_id == observation_id)
    if expert_id is not None:
        statement = statement.where(ExpertVerification.expert_id == expert_id)
    total = db.execute(select(func.count()).select_from(statement.subquery())).scalar_one()
    rows = (
        db.execute(
            statement.order_by(ExpertVerification.verified_at.desc()).limit(limit).offset(offset)
        )
        .scalars()
        .all()
    )
    return Page[VerificationRead](
        items=[VerificationRead.model_validate(row) for row in rows],
        total=int(total),
        limit=limit,
        offset=offset,
    )


def verification_history(db: Session, observation_id: int) -> list[VerificationRead]:
    observation_service.get_observation(db, observation_id)
    return list_verifications(db, observation_id=observation_id, limit=200).items


def agreement_stats(db: Session) -> VerificationStats:
    """AI-versus-expert agreement over reviewed observations.

    Only reviewed observations can contribute, which makes this a
    *review-conditional* measure: if experts review the model's confident cases
    first, the rate is optimistic. The schema's ``note`` says so in the response,
    and held-out performance is measured separately by the research module.
    """
    rows = (
        db.execute(
            select(ExpertVerification).options(
                selectinload(ExpertVerification.corrected_species),
                selectinload(ExpertVerification.previous_species),
            )
        )
        .scalars()
        .all()
    )
    if not rows:
        return VerificationStats(
            reviewed_count=0, confirmed=0, rejected=0, corrected=0, uncertain=0
        )

    counts = {decision: 0 for decision in VerificationDecision}
    agreed = 0
    comparable = 0
    agreed_confidence: list[float] = []
    disagreed_confidence: list[float] = []
    confusions: dict[tuple[str, str], int] = {}

    for row in rows:
        counts[row.decision] = counts.get(row.decision, 0) + 1
        if not row.ai_predicted_label or row.ai_predicted_label == "UNCERTAIN":
            continue
        expert_label: str | None
        if row.decision == VerificationDecision.CONFIRM:
            expert_label = row.previous_species.common_name if row.previous_species else None
        elif row.decision == VerificationDecision.CORRECT:
            expert_label = row.corrected_species.common_name if row.corrected_species else None
        elif row.decision == VerificationDecision.REJECT:
            expert_label = "REJECTED"
        else:
            expert_label = None
        if expert_label is None:
            continue

        comparable += 1
        if expert_label == row.ai_predicted_label:
            agreed += 1
            if row.ai_confidence is not None:
                agreed_confidence.append(row.ai_confidence)
        else:
            if row.ai_confidence is not None:
                disagreed_confidence.append(row.ai_confidence)
            key = (row.ai_predicted_label, expert_label)
            confusions[key] = confusions.get(key, 0) + 1

    top_confusions = [
        AgreementCell(ai_label=ai, expert_label=expert, count=count)
        for (ai, expert), count in sorted(
            confusions.items(), key=lambda kv: kv[1], reverse=True
        )[:8]
    ]
    return VerificationStats(
        reviewed_count=len(rows),
        confirmed=counts.get(VerificationDecision.CONFIRM, 0),
        rejected=counts.get(VerificationDecision.REJECT, 0),
        corrected=counts.get(VerificationDecision.CORRECT, 0),
        uncertain=counts.get(VerificationDecision.UNCERTAIN, 0),
        ai_agreement_rate=round(agreed / comparable, 4) if comparable else None,
        mean_confidence_when_agreed=(
            round(sum(agreed_confidence) / len(agreed_confidence), 4)
            if agreed_confidence
            else None
        ),
        mean_confidence_when_disagreed=(
            round(sum(disagreed_confidence) / len(disagreed_confidence), 4)
            if disagreed_confidence
            else None
        ),
        top_confusions=top_confusions,
    )


def expert_leaderboard(db: Session, *, limit: int = 10) -> list[dict]:
    """Review volume per expert — used for queue management, not ranking people."""
    rows = db.execute(
        select(
            User.id,
            User.full_name,
            User.expertise,
            func.count(ExpertVerification.id),
            func.max(ExpertVerification.verified_at),
        )
        .join(ExpertVerification, ExpertVerification.expert_id == User.id)
        .group_by(User.id, User.full_name, User.expertise)
        .order_by(func.count(ExpertVerification.id).desc())
        .limit(limit)
    ).all()
    return [
        {
            "expert_id": row[0],
            "full_name": row[1],
            "expertise": row[2],
            "reviews": int(row[3]),
            "last_review_at": row[4].isoformat() if row[4] else None,
        }
        for row in rows
    ]


def require_observation(db: Session, observation_id: int) -> Observation:
    observation = db.get(Observation, observation_id)
    if observation is None:
        raise NotFoundError(f"No observation with id {observation_id}.")
    return observation
