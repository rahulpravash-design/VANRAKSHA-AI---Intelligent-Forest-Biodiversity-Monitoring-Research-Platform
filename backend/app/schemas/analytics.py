"""Biodiversity analytics schemas.

Counts here are *detection/observation* counts. They are not population
estimates: the sampling design (opportunistic field records plus fixed camera
and acoustic nodes) does not support abundance estimation, and the response
models say so explicitly so a reader of the API cannot mistake one for the
other.
"""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field

DETECTION_DISCLAIMER = (
    "Values are observation/detection counts from opportunistic and fixed-sensor "
    "sampling. They are not population estimates."
)


class OverviewCounts(BaseModel):
    species_total: int
    species_observed: int
    species_by_category: dict[str, int]
    observations_total: int
    observations_last_30_days: int
    observations_verified: int
    observations_pending: int
    ai_predictions_total: int
    ai_uncertain_share: float | None = None
    zones_total: int
    devices_active: int
    open_alerts: int
    new_species_this_month: int
    disclaimer: str = DETECTION_DISCLAIMER


class TrendPoint(BaseModel):
    period: str = Field(description="ISO date (daily) or YYYY-MM (monthly) bucket")
    observations: int
    distinct_species: int
    verified: int


class DetectionTrend(BaseModel):
    granularity: str
    points: list[TrendPoint]
    disclaimer: str = DETECTION_DISCLAIMER


class SpeciesFrequency(BaseModel):
    species_id: int
    common_name: str
    scientific_name: str
    category: str
    detections: int
    share: float
    verified_detections: int
    last_detected_at: datetime | None = None


class DiversityIndices(BaseModel):
    """Diversity computed from detection frequencies.

    Shannon and Simpson are reported on detection counts, which is defensible
    for comparing effort-matched windows; ``comparable`` is false when sampling
    effort differs enough that a direct comparison would mislead.
    """

    sample_count: int
    species_richness: int
    shannon_index: float | None = None
    shannon_evenness: float | None = None
    simpson_index: float | None = None
    inverse_simpson: float | None = None
    chao1_estimate: float | None = None
    singletons: int = 0
    doubletons: int = 0
    comparable: bool = True
    caveat: str = (
        "Indices are computed on detection counts, not on individuals, and are only "
        "comparable between windows with similar sampling effort."
    )


class ZoneComparison(BaseModel):
    zone_id: int
    zone_code: str
    zone_name: str
    observations: int
    species_richness: int
    shannon_index: float | None = None
    detections_per_active_day: float | None = None
    open_alerts: int = 0


class SeasonalBucket(BaseModel):
    month: int
    month_name: str
    observations: int
    distinct_species: int
    dominant_category: str | None = None


class SeasonalPattern(BaseModel):
    buckets: list[SeasonalBucket]
    years_covered: list[int]
    disclaimer: str = DETECTION_DISCLAIMER


class ConfidenceBin(BaseModel):
    lower: float
    upper: float
    count: int
    expert_confirmed: int = 0
    expert_rejected: int = 0


class AIPerformanceReport(BaseModel):
    """Model behaviour measured against expert decisions.

    Because only reviewed observations contribute, this is review-conditional
    performance, not held-out test accuracy — for that, see the experiment
    framework under ``/research``.
    """

    predictions_total: int
    uncertain_total: int
    mean_confidence: float | None = None
    confidence_bins: list[ConfidenceBin]
    reviewed_total: int
    agreement_rate: float | None = None
    false_positive_candidates: int = Field(
        default=0,
        description="High-confidence predictions an expert rejected or corrected",
    )
    caveat: str = (
        "Computed over expert-reviewed observations only; it is review-conditional "
        "performance rather than held-out test accuracy."
    )


class GeographicCell(BaseModel):
    latitude: float
    longitude: float
    observations: int
    distinct_species: int
    precision_deg: float


class GeographicDistribution(BaseModel):
    cells: list[GeographicCell]
    precision_deg: float
    location_generalised: bool
    disclaimer: str = DETECTION_DISCLAIMER


class ResearchExport(BaseModel):
    generated_at: datetime
    window_start: date | None = None
    window_end: date | None = None
    row_count: int
    columns: list[str]
    #: Free-form provenance block: filters, model versions, verification policy.
    provenance: dict[str, str | int | float | None]
