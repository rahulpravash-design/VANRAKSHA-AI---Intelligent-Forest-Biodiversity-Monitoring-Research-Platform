"""Biodiversity analytics.

Every number produced here is a *detection* or *observation* count. The sampling
design — opportunistic field records plus fixed camera and acoustic nodes with
uneven effort — does not support abundance estimation, so nothing in this module
returns a population figure, and the response schemas carry that caveat into the
API documentation.

Diversity indices are reported on detection frequencies. That is defensible for
comparing windows of similar effort and misleading otherwise, so
:func:`diversity_indices` reports ``comparable=False`` when the window it was
given has too few active sampling days to stand against another.
"""

from __future__ import annotations

import calendar
import math
from datetime import UTC, date, datetime, timedelta
from itertools import pairwise

from sqlalchemy import Select, case, func, or_, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.ai import AIPrediction
from app.models.alert import Alert
from app.models.enums import AlertStatus, VerificationStatus
from app.models.iot import Device
from app.models.observation import Observation
from app.models.species import Species
from app.models.user import User
from app.models.zone import ForestZone
from app.schemas.analytics import (
    AIPerformanceReport,
    ConfidenceBin,
    DetectionTrend,
    DiversityIndices,
    GeographicCell,
    GeographicDistribution,
    OverviewCounts,
    SeasonalBucket,
    SeasonalPattern,
    SpeciesFrequency,
    TrendPoint,
    ZoneComparison,
)
from app.services.geo import may_see_precise_locations

VERIFIED_STATUSES = (VerificationStatus.CONFIRMED, VerificationStatus.CORRECTED)
#: Below this many distinct sampling days, index comparisons are not meaningful.
MIN_ACTIVE_DAYS_FOR_COMPARISON = 14


def _effective_species_id():
    """The species to attribute a detection to: expert-verified first."""
    return func.coalesce(Observation.verified_species_id, Observation.species_id)


def _window(statement: Select, start: datetime | None, end: datetime | None) -> Select:
    if start is not None:
        statement = statement.where(Observation.observed_at >= start)
    if end is not None:
        statement = statement.where(Observation.observed_at <= end)
    return statement


def _as_datetime(value: date | datetime | None, *, end_of_day: bool = False) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    time = datetime.max.time() if end_of_day else datetime.min.time()
    return datetime.combine(value, time, tzinfo=UTC)


# --------------------------------------------------------------------------- #
# overview
# --------------------------------------------------------------------------- #
def overview(db: Session) -> OverviewCounts:
    now = datetime.now(UTC)
    thirty_days_ago = now - timedelta(days=30)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    species_total = db.execute(select(func.count(Species.id))).scalar_one()
    species_by_category = {
        str(category): int(count)
        for category, count in db.execute(
            select(Species.category, func.count(Species.id)).group_by(Species.category)
        ).all()
    }
    species_observed = db.execute(
        select(func.count(func.distinct(_effective_species_id()))).where(
            _effective_species_id().is_not(None)
        )
    ).scalar_one()

    observations_total = db.execute(select(func.count(Observation.id))).scalar_one()
    observations_recent = db.execute(
        select(func.count(Observation.id)).where(Observation.observed_at >= thirty_days_ago)
    ).scalar_one()
    verified = db.execute(
        select(func.count(Observation.id)).where(
            Observation.verification_status.in_(VERIFIED_STATUSES)
        )
    ).scalar_one()
    pending = db.execute(
        select(func.count(Observation.id)).where(
            Observation.verification_status == VerificationStatus.PENDING
        )
    ).scalar_one()

    predictions_total = db.execute(select(func.count(AIPrediction.id))).scalar_one()
    uncertain_total = db.execute(
        select(func.count(AIPrediction.id)).where(AIPrediction.is_uncertain.is_(True))
    ).scalar_one()

    zones_total = db.execute(select(func.count(ForestZone.id))).scalar_one()
    devices_active = db.execute(
        select(func.count(Device.id)).where(Device.is_active.is_(True))
    ).scalar_one()
    open_alerts = db.execute(
        select(func.count(Alert.id)).where(
            Alert.status.in_([AlertStatus.OPEN, AlertStatus.INVESTIGATING])
        )
    ).scalar_one()

    # "New this month" means first recorded this month anywhere in the dataset —
    # not merely detected again this month.
    first_seen = (
        select(
            _effective_species_id().label("species_id"),
            func.min(Observation.observed_at).label("first_seen"),
        )
        .where(_effective_species_id().is_not(None))
        .group_by(_effective_species_id())
        .subquery()
    )
    new_species = db.execute(
        select(func.count()).select_from(first_seen).where(first_seen.c.first_seen >= month_start)
    ).scalar_one()

    return OverviewCounts(
        species_total=int(species_total),
        species_observed=int(species_observed or 0),
        species_by_category=species_by_category,
        observations_total=int(observations_total),
        observations_last_30_days=int(observations_recent),
        observations_verified=int(verified),
        observations_pending=int(pending),
        ai_predictions_total=int(predictions_total),
        ai_uncertain_share=(
            round(uncertain_total / predictions_total, 4) if predictions_total else None
        ),
        zones_total=int(zones_total),
        devices_active=int(devices_active),
        open_alerts=int(open_alerts),
        new_species_this_month=int(new_species or 0),
    )


# --------------------------------------------------------------------------- #
# trends
# --------------------------------------------------------------------------- #
def detection_trend(
    db: Session,
    *,
    granularity: str = "month",
    start: date | None = None,
    end: date | None = None,
    zone_id: int | None = None,
    species_id: int | None = None,
) -> DetectionTrend:
    """Observation counts per period. Detections, not population estimates."""
    if granularity not in {"day", "month"}:
        granularity = "month"
    fmt = "%Y-%m-%d" if granularity == "day" else "%Y-%m"
    bucket = func.strftime(fmt, Observation.observed_at)
    if db.bind is not None and db.bind.dialect.name.startswith("postgres"):
        pattern = "YYYY-MM-DD" if granularity == "day" else "YYYY-MM"
        bucket = func.to_char(Observation.observed_at, pattern)

    statement = select(
        bucket.label("period"),
        func.count(Observation.id),
        func.count(func.distinct(_effective_species_id())),
        func.sum(
            case((Observation.verification_status.in_(VERIFIED_STATUSES), 1), else_=0)
        ),
    )
    statement = _window(statement, _as_datetime(start), _as_datetime(end, end_of_day=True))
    if zone_id is not None:
        statement = statement.where(Observation.zone_id == zone_id)
    if species_id is not None:
        statement = statement.where(
            or_(
                Observation.species_id == species_id,
                Observation.verified_species_id == species_id,
            )
        )
    rows = db.execute(statement.group_by("period").order_by("period")).all()
    return DetectionTrend(
        granularity=granularity,
        points=[
            TrendPoint(
                period=str(period),
                observations=int(count),
                distinct_species=int(species or 0),
                verified=int(verified or 0),
            )
            for period, count, species, verified in rows
        ],
    )


def species_frequency(
    db: Session,
    *,
    limit: int = 20,
    start: date | None = None,
    end: date | None = None,
    zone_id: int | None = None,
    category: str | None = None,
) -> list[SpeciesFrequency]:
    statement = (
        select(
            Species.id,
            Species.common_name,
            Species.scientific_name,
            Species.category,
            func.count(Observation.id),
            func.sum(
                case((Observation.verification_status.in_(VERIFIED_STATUSES), 1), else_=0)
            ),
            func.max(Observation.observed_at),
        )
        .join(Observation, _effective_species_id() == Species.id)
        .group_by(Species.id, Species.common_name, Species.scientific_name, Species.category)
    )
    statement = _window(statement, _as_datetime(start), _as_datetime(end, end_of_day=True))
    if zone_id is not None:
        statement = statement.where(Observation.zone_id == zone_id)
    if category:
        statement = statement.where(Species.category == category)

    rows = db.execute(
        statement.order_by(func.count(Observation.id).desc()).limit(limit)
    ).all()
    total = sum(int(row[4]) for row in rows) or 1
    return [
        SpeciesFrequency(
            species_id=row[0],
            common_name=row[1],
            scientific_name=row[2],
            category=str(row[3]),
            detections=int(row[4]),
            share=round(int(row[4]) / total, 4),
            verified_detections=int(row[5] or 0),
            last_detected_at=row[6],
        )
        for row in rows
    ]


# --------------------------------------------------------------------------- #
# diversity
# --------------------------------------------------------------------------- #
def _detection_counts(
    db: Session,
    *,
    start: datetime | None,
    end: datetime | None,
    zone_id: int | None = None,
) -> tuple[list[int], int]:
    statement = select(_effective_species_id(), func.count(Observation.id)).where(
        _effective_species_id().is_not(None)
    )
    statement = _window(statement, start, end)
    if zone_id is not None:
        statement = statement.where(Observation.zone_id == zone_id)
    rows = db.execute(statement.group_by(_effective_species_id())).all()

    day_statement = select(func.count(func.distinct(func.date(Observation.observed_at))))
    day_statement = _window(day_statement, start, end)
    if zone_id is not None:
        day_statement = day_statement.where(Observation.zone_id == zone_id)
    active_days = int(db.execute(day_statement).scalar_one() or 0)
    return [int(count) for _, count in rows], active_days


def diversity_indices(
    db: Session,
    *,
    start: date | None = None,
    end: date | None = None,
    zone_id: int | None = None,
) -> DiversityIndices:
    """Shannon, Simpson and Chao1 over detection frequencies."""
    counts, active_days = _detection_counts(
        db,
        start=_as_datetime(start),
        end=_as_datetime(end, end_of_day=True),
        zone_id=zone_id,
    )
    total = sum(counts)
    richness = len(counts)
    if total == 0 or richness == 0:
        return DiversityIndices(
            sample_count=0, species_richness=0, comparable=False, singletons=0, doubletons=0
        )

    proportions = [count / total for count in counts]
    shannon = -sum(p * math.log(p) for p in proportions if p > 0)
    evenness = shannon / math.log(richness) if richness > 1 else 1.0
    # Simpson's index of diversity (1 - D): probability two detections differ.
    simpson = 1.0 - sum(p * p for p in proportions)
    inverse_simpson = 1.0 / sum(p * p for p in proportions)

    singletons = sum(1 for count in counts if count == 1)
    doubletons = sum(1 for count in counts if count == 2)
    # Chao1 with the bias-corrected form when there are no doubletons.
    if doubletons > 0:
        chao1 = richness + (singletons**2) / (2 * doubletons)
    elif singletons > 0:
        chao1 = richness + singletons * (singletons - 1) / 2
    else:
        chao1 = float(richness)

    return DiversityIndices(
        sample_count=total,
        species_richness=richness,
        shannon_index=round(shannon, 4),
        shannon_evenness=round(evenness, 4),
        simpson_index=round(simpson, 4),
        inverse_simpson=round(inverse_simpson, 4),
        chao1_estimate=round(chao1, 2),
        singletons=singletons,
        doubletons=doubletons,
        comparable=active_days >= MIN_ACTIVE_DAYS_FOR_COMPARISON,
    )


def zone_comparison(
    db: Session, *, start: date | None = None, end: date | None = None
) -> list[ZoneComparison]:
    """Per-zone effort-aware comparison."""
    zones = db.execute(select(ForestZone).order_by(ForestZone.code)).scalars().all()
    window_start = _as_datetime(start)
    window_end = _as_datetime(end, end_of_day=True)
    results: list[ZoneComparison] = []
    for zone in zones:
        counts, active_days = _detection_counts(
            db, start=window_start, end=window_end, zone_id=zone.id
        )
        total = sum(counts)
        richness = len(counts)
        shannon = None
        if total > 0 and richness > 0:
            proportions = [count / total for count in counts]
            shannon = round(-sum(p * math.log(p) for p in proportions if p > 0), 4)
        open_alerts = db.execute(
            select(func.count(Alert.id)).where(
                Alert.zone_id == zone.id,
                Alert.status.in_([AlertStatus.OPEN, AlertStatus.INVESTIGATING]),
            )
        ).scalar_one()
        results.append(
            ZoneComparison(
                zone_id=zone.id,
                zone_code=zone.code,
                zone_name=zone.name,
                observations=total,
                species_richness=richness,
                shannon_index=shannon,
                # Normalising by active sampling days is what makes two zones
                # with different survey effort comparable at all.
                detections_per_active_day=(
                    round(total / active_days, 3) if active_days else None
                ),
                open_alerts=int(open_alerts),
            )
        )
    return results


def _month_expression(db: Session):
    """Two-digit month of ``observed_at``, in the current dialect's syntax."""
    if db.bind is not None and db.bind.dialect.name.startswith("postgres"):
        return func.to_char(Observation.observed_at, "MM")
    return func.strftime("%m", Observation.observed_at)


def seasonal_pattern(
    db: Session, *, zone_id: int | None = None, species_id: int | None = None
) -> SeasonalPattern:
    """Detections per calendar month, aggregated across all years in the data."""
    month_expression = _month_expression(db)

    def scoped(statement: Select) -> Select:
        if zone_id is not None:
            statement = statement.where(Observation.zone_id == zone_id)
        if species_id is not None:
            statement = statement.where(
                or_(
                    Observation.species_id == species_id,
                    Observation.verified_species_id == species_id,
                )
            )
        return statement

    rows = db.execute(
        scoped(
            select(
                month_expression.label("month"),
                func.count(Observation.id),
                func.count(func.distinct(_effective_species_id())),
            )
        )
        .group_by("month")
        .order_by("month")
    ).all()
    by_month = {int(month): (int(count), int(species or 0)) for month, count, species in rows}

    category_rows = db.execute(
        scoped(
            select(
                month_expression.label("month"), Species.category, func.count(Observation.id)
            ).join(Species, _effective_species_id() == Species.id)
        ).group_by("month", Species.category)
    ).all()
    best: dict[int, tuple[int, str]] = {}
    for month, category, count in category_rows:
        month_number = int(month)
        if month_number not in best or int(count) > best[month_number][0]:
            best[month_number] = (int(count), str(category))
    dominant = {month: value[1] for month, value in best.items()}

    earliest, latest = db.execute(
        scoped(select(func.min(Observation.observed_at), func.max(Observation.observed_at)))
    ).one()
    years = list(range(earliest.year, latest.year + 1)) if earliest and latest else []

    return SeasonalPattern(
        buckets=[
            SeasonalBucket(
                month=month,
                month_name=calendar.month_abbr[month],
                observations=by_month.get(month, (0, 0))[0],
                distinct_species=by_month.get(month, (0, 0))[1],
                dominant_category=dominant.get(month),
            )
            for month in range(1, 13)
        ],
        years_covered=years,
    )


# --------------------------------------------------------------------------- #
# AI performance
# --------------------------------------------------------------------------- #
def ai_performance(db: Session, *, bins: int = 10) -> AIPerformanceReport:
    """Model behaviour measured against expert decisions."""
    from app.models.verification import ExpertVerification

    total = db.execute(select(func.count(AIPrediction.id))).scalar_one()
    uncertain = db.execute(
        select(func.count(AIPrediction.id)).where(AIPrediction.is_uncertain.is_(True))
    ).scalar_one()
    mean_confidence = db.execute(select(func.avg(AIPrediction.confidence))).scalar()

    confidences = (
        db.execute(
            select(AIPrediction.confidence).where(AIPrediction.is_uncertain.is_(False))
        )
        .scalars()
        .all()
    )
    edges = [i / bins for i in range(bins + 1)]
    confidence_bins: list[ConfidenceBin] = []
    for lower, upper in pairwise(edges):
        in_bin = [c for c in confidences if (lower < c <= upper) or (lower == 0.0 and c == 0.0)]
        confirmed = db.execute(
            select(func.count(ExpertVerification.id)).where(
                ExpertVerification.ai_confidence > lower,
                ExpertVerification.ai_confidence <= upper,
                ExpertVerification.decision == "CONFIRM",
            )
        ).scalar_one()
        rejected = db.execute(
            select(func.count(ExpertVerification.id)).where(
                ExpertVerification.ai_confidence > lower,
                ExpertVerification.ai_confidence <= upper,
                ExpertVerification.decision.in_(["REJECT", "CORRECT"]),
            )
        ).scalar_one()
        confidence_bins.append(
            ConfidenceBin(
                lower=round(lower, 2),
                upper=round(upper, 2),
                count=len(in_bin),
                expert_confirmed=int(confirmed),
                expert_rejected=int(rejected),
            )
        )

    reviewed = db.execute(select(func.count(ExpertVerification.id))).scalar_one()
    stats = None
    if reviewed:
        from app.services.verification_service import agreement_stats

        stats = agreement_stats(db)

    # A high-confidence prediction an expert then rejected or corrected is the
    # case that matters most for trust in the queue.
    false_positive_candidates = db.execute(
        select(func.count(ExpertVerification.id)).where(
            ExpertVerification.ai_confidence >= 0.8,
            ExpertVerification.decision.in_(["REJECT", "CORRECT"]),
        )
    ).scalar_one()

    return AIPerformanceReport(
        predictions_total=int(total),
        uncertain_total=int(uncertain),
        mean_confidence=round(float(mean_confidence), 4) if mean_confidence is not None else None,
        confidence_bins=confidence_bins,
        reviewed_total=int(reviewed),
        agreement_rate=stats.ai_agreement_rate if stats else None,
        false_positive_candidates=int(false_positive_candidates),
    )


# --------------------------------------------------------------------------- #
# geography
# --------------------------------------------------------------------------- #
def geographic_distribution(
    db: Session,
    *,
    viewer: User | None,
    precision_deg: float | None = None,
    zone_id: int | None = None,
) -> GeographicDistribution:
    """Gridded detection density.

    The grid is never finer than the viewer is entitled to see: an anonymous or
    viewer-role caller gets the sensitive-species precision applied to *every*
    cell, so a sensitive record cannot be isolated by differencing a fine grid
    against a coarse one.
    """
    precise = may_see_precise_locations(viewer)
    grid = precision_deg or (0.02 if precise else settings.sensitive_location_precision_deg)
    grid = max(float(grid), 0.002 if precise else settings.sensitive_location_precision_deg)

    statement = select(Observation.latitude, Observation.longitude, _effective_species_id()).where(
        Observation.latitude.is_not(None), Observation.longitude.is_not(None)
    )
    if zone_id is not None:
        statement = statement.where(Observation.zone_id == zone_id)
    rows = db.execute(statement).all()

    cells: dict[tuple[int, int], dict] = {}
    for latitude, longitude, species_id in rows:
        key = (math.floor(latitude / grid), math.floor(longitude / grid))
        cell = cells.setdefault(key, {"count": 0, "species": set()})
        cell["count"] += 1
        if species_id is not None:
            cell["species"].add(species_id)

    return GeographicDistribution(
        cells=[
            GeographicCell(
                latitude=round((key[0] + 0.5) * grid, 6),
                longitude=round((key[1] + 0.5) * grid, 6),
                observations=value["count"],
                distinct_species=len(value["species"]),
                precision_deg=grid,
            )
            for key, value in sorted(cells.items())
        ],
        precision_deg=grid,
        location_generalised=not precise,
    )
