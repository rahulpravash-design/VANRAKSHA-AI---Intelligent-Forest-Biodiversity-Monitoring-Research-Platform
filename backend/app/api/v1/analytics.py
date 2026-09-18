"""Biodiversity analytics endpoints.

Everything here counts *detections*. The response models say so, because a
dashboard number labelled only "Indian Gaur: 47" invites the reader to hear
"there are 47 gaur", which this sampling design cannot support.
"""

from __future__ import annotations

import csv
import io
from datetime import UTC, date, datetime

from fastapi import APIRouter, Query, Response
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.deps import CurrentUser, DbSession, OptionalUser
from app.models.observation import Observation
from app.schemas.analytics import (
    AIPerformanceReport,
    DetectionTrend,
    DiversityIndices,
    GeographicDistribution,
    OverviewCounts,
    SeasonalPattern,
    SpeciesFrequency,
    ZoneComparison,
)
from app.services import analytics_service, sensor_service
from app.services.geo import may_see_precise_locations

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/overview", response_model=OverviewCounts, summary="Dashboard headline counts")
def overview(db: DbSession) -> OverviewCounts:
    return analytics_service.overview(db)


@router.get(
    "/trends",
    response_model=DetectionTrend,
    summary="Detection counts per day or month",
)
def trends(
    db: DbSession,
    granularity: str = Query(default="month", pattern="^(day|month)$"),
    start: date | None = Query(default=None),
    end: date | None = Query(default=None),
    zone_id: int | None = Query(default=None),
    species_id: int | None = Query(default=None),
) -> DetectionTrend:
    return analytics_service.detection_trend(
        db,
        granularity=granularity,
        start=start,
        end=end,
        zone_id=zone_id,
        species_id=species_id,
    )


@router.get(
    "/species-frequency",
    response_model=list[SpeciesFrequency],
    summary="Most frequently detected species",
)
def species_frequency(
    db: DbSession,
    limit: int = Query(default=20, ge=1, le=100),
    start: date | None = Query(default=None),
    end: date | None = Query(default=None),
    zone_id: int | None = Query(default=None),
    category: str | None = Query(default=None),
) -> list[SpeciesFrequency]:
    return analytics_service.species_frequency(
        db, limit=limit, start=start, end=end, zone_id=zone_id, category=category
    )


@router.get(
    "/diversity",
    response_model=DiversityIndices,
    summary="Shannon, Simpson and Chao1 over detection frequencies",
)
def diversity(
    db: DbSession,
    start: date | None = Query(default=None),
    end: date | None = Query(default=None),
    zone_id: int | None = Query(default=None),
) -> DiversityIndices:
    """`comparable: false` means the window has too few active sampling days for
    the indices to be compared against another window."""
    return analytics_service.diversity_indices(db, start=start, end=end, zone_id=zone_id)


@router.get(
    "/zones",
    response_model=list[ZoneComparison],
    summary="Per-zone comparison, normalised by sampling effort",
)
def zones(
    db: DbSession,
    start: date | None = Query(default=None),
    end: date | None = Query(default=None),
) -> list[ZoneComparison]:
    return analytics_service.zone_comparison(db, start=start, end=end)


@router.get(
    "/seasonal",
    response_model=SeasonalPattern,
    summary="Detections per calendar month across all years",
)
def seasonal(
    db: DbSession,
    zone_id: int | None = Query(default=None),
    species_id: int | None = Query(default=None),
) -> SeasonalPattern:
    return analytics_service.seasonal_pattern(db, zone_id=zone_id, species_id=species_id)


@router.get(
    "/ai-performance",
    response_model=AIPerformanceReport,
    summary="Model confidence distribution and expert agreement",
)
def ai_performance(db: DbSession, _user: CurrentUser) -> AIPerformanceReport:
    return analytics_service.ai_performance(db)


@router.get(
    "/geographic",
    response_model=GeographicDistribution,
    summary="Gridded detection density",
)
def geographic(
    db: DbSession,
    viewer: OptionalUser,
    precision_deg: float | None = Query(default=None, gt=0, le=5),
    zone_id: int | None = Query(default=None),
) -> GeographicDistribution:
    """The grid is never finer than the caller is entitled to see, so a
    sensitive record cannot be isolated by differencing two grid sizes."""
    return analytics_service.geographic_distribution(
        db, viewer=viewer, precision_deg=precision_deg, zone_id=zone_id
    )


@router.get(
    "/environment",
    response_model=dict,
    summary="Recent environmental conditions from the sensor network",
)
def environment(
    db: DbSession,
    _user: CurrentUser,
    zone_id: int | None = Query(default=None),
    hours: int = Query(default=24, ge=1, le=720),
) -> dict:
    """Context for interpreting a detection drop: a week of heavy rain is a
    likelier explanation than a change in the fauna."""
    return sensor_service.environmental_summary(db, zone_id=zone_id, hours=hours)


@router.get(
    "/export.csv",
    summary="Export the observation dataset as CSV",
    response_class=Response,
    responses={200: {"content": {"text/csv": {}}}},
)
def export_csv(
    db: DbSession,
    user: CurrentUser,
    start: date | None = Query(default=None),
    end: date | None = Query(default=None),
    verified_only: bool = Query(
        default=True, description="Restrict to expert-verified records"
    ),
    limit: int = Query(default=20000, ge=1, le=100000),
) -> Response:
    """A research export with provenance in the header comments.

    Defaults to verified records only: an export of unverified model guesses is
    not a dataset. Coordinates follow the same privacy rules as the API, and the
    `location_generalised` column marks every row whose position was coarsened.
    """
    from app.models.enums import VerificationStatus
    from app.services.observation_service import serialise_observation

    statement = (
        select(Observation)
        .options(
            selectinload(Observation.species),
            selectinload(Observation.verified_species),
            selectinload(Observation.zone),
            selectinload(Observation.researcher),
        )
        .order_by(Observation.observed_at)
        .limit(limit)
    )
    if verified_only:
        statement = statement.where(
            Observation.verification_status.in_(
                [VerificationStatus.CONFIRMED, VerificationStatus.CORRECTED]
            )
        )
    if start is not None:
        statement = statement.where(
            Observation.observed_at >= datetime.combine(start, datetime.min.time(), tzinfo=UTC)
        )
    if end is not None:
        statement = statement.where(
            Observation.observed_at <= datetime.combine(end, datetime.max.time(), tzinfo=UTC)
        )
    rows = db.execute(statement).scalars().all()

    columns = [
        "observation_id",
        "observed_at",
        "final_scientific_name",
        "final_common_name",
        "category",
        "conservation_status",
        "latitude",
        "longitude",
        "location_accuracy_m",
        "location_generalised",
        "zone_code",
        "observation_type",
        "individual_count",
        "verification_status",
        "ai_prediction",
        "ai_confidence",
        "ai_model_version",
        "recorded_by",
        "notes",
    ]
    buffer = io.StringIO()
    buffer.write(f"# VANRAKSHA AI observation export generated {datetime.now(UTC).isoformat()}\n")
    buffer.write(f"# rows={len(rows)} verified_only={verified_only}\n")
    buffer.write(
        "# Values are observation/detection records, not population estimates.\n"
    )
    buffer.write(
        "# Coordinates of sensitive taxa are generalised unless "
        f"location_generalised=false (requester role={user.role.value}, "
        f"precise_access={may_see_precise_locations(user)}).\n"
    )
    writer = csv.DictWriter(buffer, fieldnames=columns, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        view = serialise_observation(row, user)
        species = row.verified_species or row.species
        writer.writerow(
            {
                "observation_id": row.id,
                "observed_at": view.observed_at.isoformat(),
                "final_scientific_name": species.scientific_name if species else "",
                "final_common_name": species.common_name if species else "",
                "category": str(species.category) if species else "",
                "conservation_status": str(species.conservation_status) if species else "",
                "latitude": view.latitude if view.latitude is not None else "",
                "longitude": view.longitude if view.longitude is not None else "",
                "location_accuracy_m": view.location_accuracy_m or "",
                "location_generalised": str(view.location_generalised).lower(),
                "zone_code": row.zone.code if row.zone else "",
                "observation_type": str(view.observation_type),
                "individual_count": view.individual_count if view.individual_count else "",
                "verification_status": str(view.verification_status),
                "ai_prediction": view.ai_prediction or "",
                "ai_confidence": view.ai_confidence if view.ai_confidence is not None else "",
                "ai_model_version": view.ai_model_version or "",
                "recorded_by": row.researcher.full_name if row.researcher else "",
                "notes": (view.notes or "").replace("\n", " "),
            }
        )
    filename = f"vanraksha-observations-{date.today().isoformat()}.csv"
    return Response(
        content=buffer.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
