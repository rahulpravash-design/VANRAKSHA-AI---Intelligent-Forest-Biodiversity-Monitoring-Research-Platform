"""Anomaly and alert schemas.

Language matters here: an alert reports an *unusual observation pattern* and
lists candidate explanations. It never asserts a cause such as poaching — that
conclusion can only be recorded by a human after investigation.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.models.enums import (
    AlertKind,
    AlertSeverity,
    AlertStatus,
    AnomalyMethod,
)
from app.schemas.common import ORMModel


class AnomalyScoreRead(ORMModel):
    id: int
    zone_id: int | None = None
    metric: str
    method: AnomalyMethod
    window_start: datetime
    window_end: datetime
    observed_value: float
    baseline_value: float | None = None
    baseline_spread: float | None = None
    score: float
    is_anomaly: bool
    details: dict[str, Any] | None = None
    created_at: datetime


class AlertRead(ORMModel):
    id: int
    kind: AlertKind
    severity: AlertSeverity
    status: AlertStatus
    zone_id: int | None = None
    zone_name: str | None = None
    device_id: int | None = None
    title: str
    message: str
    evidence: dict[str, Any] | None = None
    candidate_causes: list[str] | None = None
    detected_at: datetime
    acknowledged_at: datetime | None = None
    acknowledged_by_id: int | None = None
    resolved_at: datetime | None = None
    resolution_notes: str | None = None
    confirmed_cause: str | None = None
    created_at: datetime


class AlertStatusUpdate(BaseModel):
    status: AlertStatus
    resolution_notes: str | None = Field(default=None, max_length=4000)
    #: Only set by the investigating human, never by the detector.
    confirmed_cause: str | None = Field(default=None, max_length=120)


class AnomalyRunRequest(BaseModel):
    zone_id: int | None = None
    baseline_days: int | None = Field(default=None, ge=14, le=1095)
    window_days: int | None = Field(default=None, ge=1, le=90)
    z_threshold: float | None = Field(default=None, ge=1.0, le=10.0)
    method: AnomalyMethod = AnomalyMethod.ENSEMBLE
    #: When false the detector reports findings without creating alert rows.
    create_alerts: bool = True


class AnomalyRunResult(BaseModel):
    evaluated_windows: int
    anomalies_found: int
    alerts_created: int
    scores: list[AnomalyScoreRead] = Field(default_factory=list)
    alerts: list[AlertRead] = Field(default_factory=list)
    note: str = (
        "Flagged windows indicate a deviation from the recent baseline and require "
        "human investigation; the detector does not infer a cause."
    )
