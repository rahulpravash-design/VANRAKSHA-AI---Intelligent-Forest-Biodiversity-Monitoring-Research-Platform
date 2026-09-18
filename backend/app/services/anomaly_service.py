"""Anomaly detection over the platform's own data, and the alerts it raises.

The detector's job is to notice that a window of detections no longer resembles
the recent baseline. It does not diagnose. Every alert therefore carries:

* the numbers (observed, baseline, spread, score, window),
* a ranked list of candidate causes for a human to check, and
* an empty ``confirmed_cause`` until a forest officer records one.

The wording is deliberate throughout: "unusual biodiversity observation pattern
detected in Zone C", never "poaching detected". A detection-count drop has many
ordinary explanations — a sensor failing, a week of rain, a survey team on
leave, a species migrating — and the platform is not in a position to
distinguish them from the data alone.
"""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime, timedelta

from fastapi import Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.core.config import settings
from app.core.errors import NotFoundError, ValidationError
from app.models.alert import Alert, AnomalyScore
from app.models.enums import (
    AlertKind,
    AlertSeverity,
    AlertStatus,
    AnomalyMethod,
    VerificationStatus,
)
from app.models.iot import Device, SensorReading
from app.models.observation import Observation
from app.models.species import Species
from app.models.user import User
from app.models.zone import ForestZone
from app.schemas.alert import (
    AlertRead,
    AlertStatusUpdate,
    AnomalyRunRequest,
    AnomalyRunResult,
    AnomalyScoreRead,
)
from app.schemas.common import Page
from app.services import audit
from app.services.ai_client import _ensure_ai_importable

logger = logging.getLogger(__name__)

SEVERITY_BY_SCORE = (
    (0.85, AlertSeverity.HIGH),
    (0.65, AlertSeverity.MEDIUM),
    (0.45, AlertSeverity.LOW),
)


def _severity_for(score: float) -> AlertSeverity:
    for threshold, severity in SEVERITY_BY_SCORE:
        if score >= threshold:
            return severity
    return AlertSeverity.INFO


def daily_detection_counts(
    db: Session,
    *,
    zone_id: int | None = None,
    category: str | None = None,
    since: date | None = None,
) -> dict[date, float]:
    """Detections per calendar day.

    Days with no row are *absent* from the result rather than zero, so the
    detector can tell "we surveyed and saw nothing" apart from "we did not
    survey" — a distinction that decides whether a drop is ecological or a data
    gap.
    """
    day = func.date(Observation.observed_at)
    statement = select(day, func.count(Observation.id))
    if zone_id is not None:
        statement = statement.where(Observation.zone_id == zone_id)
    if category:
        statement = statement.where(
            func.coalesce(Observation.verified_species_id, Observation.species_id).in_(
                select(Species.id).where(Species.category == category)
            )
        )
    if since is not None:
        statement = statement.where(
            Observation.observed_at >= datetime.combine(since, datetime.min.time(), tzinfo=UTC)
        )
    rows = db.execute(statement.group_by(day).order_by(day)).all()

    counts: dict[date, float] = {}
    for bucket, count in rows:
        parsed = bucket if isinstance(bucket, date) else date.fromisoformat(str(bucket)[:10])
        counts[parsed] = float(count)
    return counts


def _device_gap(db: Session, zone_id: int | None, window_end: date) -> bool:
    """True when a device in this zone stopped reporting during the window."""
    statement = select(Device).where(Device.is_active.is_(True))
    if zone_id is not None:
        statement = statement.where(Device.zone_id == zone_id)
    devices = db.execute(statement).scalars().all()
    if not devices:
        return False
    boundary = datetime.combine(window_end, datetime.max.time(), tzinfo=UTC)
    for device in devices:
        latest = db.execute(
            select(func.max(SensorReading.recorded_at)).where(
                SensorReading.device_id == device.id
            )
        ).scalar()
        expected_gap = timedelta(minutes=device.report_interval_minutes * 4)
        if latest is None:
            return True
        latest = latest if latest.tzinfo else latest.replace(tzinfo=UTC)
        if boundary - latest > expected_gap:
            return True
    return False


def _already_raised(
    db: Session, zone_id: int | None, window_start: date, lookback_days: int
) -> bool:
    """True when this zone already has an open alert for this exact window.

    The window is stored inside the JSON ``evidence`` blob, and JSON path syntax
    differs between SQLite and PostgreSQL, so the comparison is done in Python
    over the small set of recent alerts rather than in a dialect-specific
    predicate.
    """
    recent = (
        db.execute(
            select(Alert)
            .where(
                Alert.zone_id == zone_id,
                Alert.kind.in_(
                    [AlertKind.BIODIVERSITY_ANOMALY, AlertKind.SENSOR_MALFUNCTION]
                ),
                Alert.detected_at >= datetime.now(UTC) - timedelta(days=lookback_days),
            )
            .limit(500)
        )
        .scalars()
        .all()
    )
    target = window_start.isoformat()
    return any((alert.evidence or {}).get("window_start") == target for alert in recent)


def run_detection(
    db: Session,
    payload: AnomalyRunRequest,
    *,
    actor: User | None = None,
    request: Request | None = None,
) -> AnomalyRunResult:
    """Score recent windows and, optionally, raise alerts for the flagged ones."""
    _ensure_ai_importable()
    from ai.anomaly.detector import BiodiversityAnomalyDetector, candidate_causes
    from ai.config import AIConfig

    config = AIConfig(
        baseline_days=payload.baseline_days or settings.anomaly_baseline_days,
        window_days=payload.window_days or settings.anomaly_window_days,
        z_threshold=payload.z_threshold
        if payload.z_threshold is not None
        else settings.anomaly_z_threshold,
        contamination=settings.anomaly_contamination,
    )
    detector = BiodiversityAnomalyDetector(config)

    zones: list[ForestZone | None]
    if payload.zone_id is not None:
        zone = db.get(ForestZone, payload.zone_id)
        if zone is None:
            raise ValidationError(f"No forest zone with id {payload.zone_id}.")
        zones = [zone]
    else:
        zones = list(db.execute(select(ForestZone).order_by(ForestZone.id)).scalars().all())
    if not zones:
        zones = [None]  # whole-dataset analysis when no zones are configured

    metrics = ["detections.total", "detections.BIRD", "detections.MAMMAL", "detections.PLANT"]
    lookback = date.today() - timedelta(days=config.baseline_days + config.window_days * 4)

    scores: list[AnomalyScore] = []
    alerts: list[Alert] = []
    evaluated = 0
    anomalies = 0

    for zone in zones:
        zone_id = zone.id if zone else None
        # Findings per metric for this zone, so a single alert can say whether
        # every taxon moved together (a recording problem) or just one (an
        # ecological question).
        zone_findings: dict[str, list] = {}
        for metric in metrics:
            category = metric.split(".", 1)[1]
            counts = daily_detection_counts(
                db,
                zone_id=zone_id,
                category=None if category == "total" else category,
                since=lookback,
            )
            if not counts:
                continue
            findings = detector.detect(
                metric,
                counts,
                window_days=config.window_days,
                baseline_days=config.baseline_days,
                z_threshold=config.z_threshold,
                evaluate_last_n=3,
                # Anchor the windows to today, not to the last day that carries
                # data, so a zone that stopped reporting is still evaluated.
                end_date=date.today(),
            )
            zone_findings[metric] = findings
            evaluated += len(findings)

        if not zone_findings:
            continue

        flagged_windows: dict[tuple[date, date], list] = {}
        for findings in zone_findings.values():
            for finding in findings:
                row = AnomalyScore(
                    zone_id=zone_id,
                    metric=finding.metric,
                    method=AnomalyMethod(finding.method),
                    window_start=datetime.combine(
                        finding.window_start, datetime.min.time(), tzinfo=UTC
                    ),
                    window_end=datetime.combine(
                        finding.window_end, datetime.max.time(), tzinfo=UTC
                    ),
                    observed_value=finding.observed,
                    baseline_value=finding.baseline,
                    baseline_spread=finding.spread,
                    score=finding.score,
                    is_anomaly=finding.is_anomaly,
                    details=finding.details,
                )
                db.add(row)
                scores.append(row)
                if finding.is_anomaly:
                    anomalies += 1
                    key = (finding.window_start, finding.window_end)
                    flagged_windows.setdefault(key, []).append(finding)

        if not payload.create_alerts:
            continue

        for (window_start, window_end), window_findings in flagged_windows.items():
            total_metrics = len(zone_findings)
            correlated = len(window_findings)
            primary = max(window_findings, key=lambda f: f.score)
            device_gap = _device_gap(db, zone_id, window_end)
            causes = candidate_causes(
                primary,
                device_gap=device_gap,
                correlated_metrics=correlated,
                total_metrics=total_metrics,
                config=config,
            )
            zone_label = f"Zone {zone.code}" if zone else "the monitored area"
            direction = (
                "lower than" if primary.direction == "drop" else "higher than"
            ) if primary.direction != "stable" else "differently distributed from"
            title = f"Unusual biodiversity observation pattern in {zone_label}"
            message = (
                f"Between {window_start.isoformat()} and {window_end.isoformat()}, "
                f"{primary.metric} was {direction} the recent baseline "
                f"({primary.observed:.0f} against a baseline of {primary.baseline:.1f}, "
                f"robust z = {primary.robust_z:+.2f}). "
                f"{correlated} of {total_metrics} monitored metrics moved in this window. "
                "This requires human investigation; the system does not infer a cause."
            )
            alert = Alert(
                kind=(
                    AlertKind.SENSOR_MALFUNCTION
                    if device_gap
                    else AlertKind.BIODIVERSITY_ANOMALY
                ),
                severity=_severity_for(primary.score),
                status=AlertStatus.OPEN,
                zone_id=zone_id,
                title=title,
                message=message,
                evidence={
                    "window_start": window_start.isoformat(),
                    "window_end": window_end.isoformat(),
                    "metrics": [finding.as_dict() for finding in window_findings],
                    "correlated_metrics": correlated,
                    "total_metrics": total_metrics,
                    "device_reporting_gap": device_gap,
                },
                candidate_causes=causes,
                detected_at=datetime.now(UTC),
            )
            if _already_raised(db, zone_id, window_start, config.baseline_days):
                continue
            db.add(alert)
            alerts.append(alert)

    if actor is not None:
        audit.record(
            db,
            "anomaly.run",
            user=actor,
            entity="zone",
            entity_id=payload.zone_id,
            request=request,
            context={
                "evaluated_windows": evaluated,
                "anomalies": anomalies,
                "alerts_created": len(alerts),
            },
        )
    db.commit()
    for row in scores:
        db.refresh(row)
    for row in alerts:
        db.refresh(row)

    return AnomalyRunResult(
        evaluated_windows=evaluated,
        anomalies_found=anomalies,
        alerts_created=len(alerts),
        scores=[AnomalyScoreRead.model_validate(row) for row in scores if row.is_anomaly],
        alerts=[_serialise_alert(row) for row in alerts],
    )


# --------------------------------------------------------------------------- #
# alerts
# --------------------------------------------------------------------------- #
def _serialise_alert(alert: Alert) -> AlertRead:
    payload = AlertRead.model_validate(alert).model_dump()
    payload["zone_name"] = alert.zone.name if alert.zone else None
    return AlertRead(**payload)


def list_alerts(
    db: Session,
    *,
    status: AlertStatus | None = None,
    zone_id: int | None = None,
    kind: AlertKind | None = None,
    severity: AlertSeverity | None = None,
    limit: int = 50,
    offset: int = 0,
) -> Page[AlertRead]:
    statement = select(Alert).options(selectinload(Alert.zone))
    if status is not None:
        statement = statement.where(Alert.status == status)
    if zone_id is not None:
        statement = statement.where(Alert.zone_id == zone_id)
    if kind is not None:
        statement = statement.where(Alert.kind == kind)
    if severity is not None:
        statement = statement.where(Alert.severity == severity)
    total = db.execute(select(func.count()).select_from(statement.subquery())).scalar_one()
    rows = (
        db.execute(statement.order_by(Alert.detected_at.desc()).limit(limit).offset(offset))
        .scalars()
        .all()
    )
    return Page[AlertRead](
        items=[_serialise_alert(row) for row in rows],
        total=int(total),
        limit=limit,
        offset=offset,
    )


def get_alert(db: Session, alert_id: int) -> Alert:
    alert = db.execute(
        select(Alert).options(selectinload(Alert.zone)).where(Alert.id == alert_id)
    ).scalar_one_or_none()
    if alert is None:
        raise NotFoundError(f"No alert with id {alert_id}.")
    return alert


def update_alert_status(
    db: Session,
    alert_id: int,
    payload: AlertStatusUpdate,
    *,
    actor: User,
    request: Request | None = None,
) -> AlertRead:
    """Move an alert through investigation and record the human conclusion."""
    alert = get_alert(db, alert_id)
    now = datetime.now(UTC)

    if payload.status in {AlertStatus.RESOLVED, AlertStatus.DISMISSED} and not (
        payload.resolution_notes or "").strip():
        raise ValidationError(
            "Closing an alert requires resolution notes describing what was found."
        )

    alert.status = payload.status
    if payload.status == AlertStatus.INVESTIGATING and alert.acknowledged_at is None:
        alert.acknowledged_at = now
        alert.acknowledged_by_id = actor.id
    if payload.status in {AlertStatus.RESOLVED, AlertStatus.DISMISSED}:
        alert.resolved_at = now
        if alert.acknowledged_by_id is None:
            alert.acknowledged_by_id = actor.id
            alert.acknowledged_at = alert.acknowledged_at or now
    if payload.resolution_notes is not None:
        alert.resolution_notes = payload.resolution_notes
    # The confirmed cause is a human finding. The detector never sets it.
    if payload.confirmed_cause is not None:
        alert.confirmed_cause = payload.confirmed_cause

    audit.record(
        db,
        "alert.status_change",
        user=actor,
        entity="alert",
        entity_id=alert.id,
        request=request,
        context={"status": str(payload.status), "confirmed_cause": payload.confirmed_cause},
    )
    db.commit()
    db.refresh(alert)
    return _serialise_alert(alert)


def list_scores(
    db: Session,
    *,
    zone_id: int | None = None,
    metric: str | None = None,
    anomalies_only: bool = False,
    limit: int = 100,
    offset: int = 0,
) -> Page[AnomalyScoreRead]:
    statement = select(AnomalyScore)
    if zone_id is not None:
        statement = statement.where(AnomalyScore.zone_id == zone_id)
    if metric:
        statement = statement.where(AnomalyScore.metric == metric)
    if anomalies_only:
        statement = statement.where(AnomalyScore.is_anomaly.is_(True))
    total = db.execute(select(func.count()).select_from(statement.subquery())).scalar_one()
    rows = (
        db.execute(
            statement.order_by(AnomalyScore.window_end.desc()).limit(limit).offset(offset)
        )
        .scalars()
        .all()
    )
    return Page[AnomalyScoreRead](
        items=[AnomalyScoreRead.model_validate(row) for row in rows],
        total=int(total),
        limit=limit,
        offset=offset,
    )


def raise_device_alerts(
    db: Session, *, actor: User | None = None, request: Request | None = None
) -> list[AlertRead]:
    """Flag active devices that have stopped reporting on schedule."""
    now = datetime.now(UTC)
    created: list[Alert] = []
    devices = db.execute(select(Device).where(Device.is_active.is_(True))).scalars().all()
    for device in devices:
        threshold = timedelta(minutes=device.report_interval_minutes * 4)
        last_seen = device.last_seen_at
        if last_seen is not None and last_seen.tzinfo is None:
            last_seen = last_seen.replace(tzinfo=UTC)
        if last_seen is not None and now - last_seen <= threshold:
            continue
        already_open = db.execute(
            select(Alert.id).where(
                Alert.device_id == device.id,
                Alert.kind == AlertKind.DEVICE_OFFLINE,
                Alert.status.in_([AlertStatus.OPEN, AlertStatus.INVESTIGATING]),
            )
        ).first()
        if already_open is not None:
            continue
        silent_for = (
            f"{(now - last_seen).total_seconds() / 3600:.1f} hours"
            if last_seen
            else "its whole lifetime"
        )
        alert = Alert(
            kind=AlertKind.DEVICE_OFFLINE,
            severity=AlertSeverity.MEDIUM,
            status=AlertStatus.OPEN,
            zone_id=device.zone_id,
            device_id=device.id,
            title=f"Monitoring node {device.device_code} has stopped reporting",
            message=(
                f"{device.name} last reported {silent_for} ago; it is configured to report "
                f"every {device.report_interval_minutes} minutes. Detection counts from this "
                "zone may be incomplete for the affected period."
            ),
            evidence={
                "device_code": device.device_code,
                "last_seen_at": last_seen.isoformat() if last_seen else None,
                "report_interval_minutes": device.report_interval_minutes,
            },
            candidate_causes=[
                "Battery depleted or power failure",
                "Connectivity loss at the node or gateway",
                "Hardware or firmware fault",
                "Node removed, stolen or damaged",
            ],
            detected_at=now,
        )
        db.add(alert)
        created.append(alert)

    if created and actor is not None:
        audit.record(
            db,
            "alert.device_sweep",
            user=actor,
            request=request,
            context={"alerts_created": len(created)},
        )
    db.commit()
    for alert in created:
        db.refresh(alert)
    return [_serialise_alert(alert) for alert in created]


def threatened_species_notice(
    db: Session, observation: Observation, *, commit: bool = True
) -> Alert | None:
    """Notify officers when a threatened taxon is recorded in a zone.

    Informational by design: it tells the people responsible for a zone that a
    CR/EN/VU taxon has been reported there, and it is raised only once the
    identification has been confirmed by an expert — an unverified model guess is
    not a basis for dispatching a patrol.
    """
    from app.models.enums import THREATENED_STATUSES

    species = observation.verified_species
    if species is None or species.conservation_status not in THREATENED_STATUSES:
        return None
    if observation.verification_status not in {
        VerificationStatus.CONFIRMED,
        VerificationStatus.CORRECTED,
    }:
        return None

    alert = Alert(
        kind=AlertKind.THREATENED_SPECIES_DETECTION,
        severity=AlertSeverity.INFO,
        status=AlertStatus.OPEN,
        zone_id=observation.zone_id,
        title=f"Expert-confirmed record of {species.common_name}",
        message=(
            f"{species.common_name} ({species.scientific_name}, IUCN "
            f"{species.conservation_status.value}) was confirmed by an expert in "
            f"observation #{observation.id}. Precise coordinates are restricted to "
            "authorised roles."
        ),
        evidence={
            "observation_id": observation.id,
            "species_id": species.id,
            "conservation_status": species.conservation_status.value,
            "location_restricted": True,
        },
        candidate_causes=[],
        detected_at=datetime.now(UTC),
    )
    db.add(alert)
    if commit:
        db.commit()
        db.refresh(alert)
    return alert
