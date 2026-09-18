"""Anomaly detection and alert management.

The wording of these endpoints is deliberate. An alert reports an *unusual
observation pattern* and lists candidate causes; it does not claim poaching,
felling or ecological damage. Only a human investigating in the field can set
`confirmed_cause`, and the API enforces that a closing note accompanies it.
"""

from __future__ import annotations

from fastapi import APIRouter, Body, Query, Request

from app.core.deps import CurrentUser, DbSession, OfficerUser
from app.models.enums import AlertKind, AlertSeverity, AlertStatus
from app.schemas.alert import (
    AlertRead,
    AlertStatusUpdate,
    AnomalyRunRequest,
    AnomalyRunResult,
    AnomalyScoreRead,
)
from app.schemas.common import Page
from app.services import anomaly_service

router = APIRouter(prefix="/alerts", tags=["alerts"])


@router.get("", response_model=Page[AlertRead], summary="List alerts")
def list_alerts(
    db: DbSession,
    _user: CurrentUser,
    status: AlertStatus | None = Query(default=None),
    zone_id: int | None = Query(default=None),
    kind: AlertKind | None = Query(default=None),
    severity: AlertSeverity | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> Page[AlertRead]:
    return anomaly_service.list_alerts(
        db,
        status=status,
        zone_id=zone_id,
        kind=kind,
        severity=severity,
        limit=limit,
        offset=offset,
    )


@router.get("/{alert_id}", response_model=AlertRead, summary="Read an alert")
def get_alert(db: DbSession, _user: CurrentUser, alert_id: int) -> AlertRead:
    return anomaly_service._serialise_alert(  # noqa: SLF001
        anomaly_service.get_alert(db, alert_id)
    )


@router.patch(
    "/{alert_id}",
    response_model=AlertRead,
    summary="Acknowledge, resolve or dismiss an alert",
    responses={422: {"description": "Closing an alert requires resolution notes"}},
)
def update_alert(
    db: DbSession,
    request: Request,
    officer: OfficerUser,
    alert_id: int,
    payload: AlertStatusUpdate = Body(...),
) -> AlertRead:
    """Recording the outcome is what turns a flagged window into knowledge:
    `confirmed_cause` is the one place a cause is ever asserted, and only a
    human sets it."""
    return anomaly_service.update_alert_status(
        db, alert_id, payload, actor=officer, request=request
    )


@router.post(
    "/detect",
    response_model=AnomalyRunResult,
    summary="Score recent windows for unusual observation patterns",
)
def run_detection(
    db: DbSession,
    request: Request,
    officer: OfficerUser,
    payload: AnomalyRunRequest = Body(default=AnomalyRunRequest()),
) -> AnomalyRunResult:
    """Runs the robust-baseline and Isolation-Forest ensemble over recent windows.

    Set `create_alerts: false` to score without raising anything — useful for
    tuning the threshold against historical data before enabling alerting.
    """
    return anomaly_service.run_detection(db, payload, actor=officer, request=request)


@router.post(
    "/device-sweep",
    response_model=list[AlertRead],
    summary="Raise alerts for nodes that have stopped reporting",
)
def device_sweep(db: DbSession, request: Request, officer: OfficerUser) -> list[AlertRead]:
    """A silent node makes detection counts drop for a reason that has nothing to
    do with wildlife, so this runs before interpreting an anomaly."""
    return anomaly_service.raise_device_alerts(db, actor=officer, request=request)


@router.get(
    "/anomaly/scores",
    response_model=Page[AnomalyScoreRead],
    summary="Scored windows, including the ones not flagged",
)
def scores(
    db: DbSession,
    _user: CurrentUser,
    zone_id: int | None = Query(default=None),
    metric: str | None = Query(default=None),
    anomalies_only: bool = Query(default=False),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> Page[AnomalyScoreRead]:
    """The unflagged windows matter too: they are the baseline a reviewer needs
    to judge whether a threshold is set sensibly."""
    return anomaly_service.list_scores(
        db,
        zone_id=zone_id,
        metric=metric,
        anomalies_only=anomalies_only,
        limit=limit,
        offset=offset,
    )
