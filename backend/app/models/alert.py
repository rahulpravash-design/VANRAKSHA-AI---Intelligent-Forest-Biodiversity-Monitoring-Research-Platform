"""Anomaly scores and the alerts raised from them.

Alerts describe *patterns that need human investigation*.  They never assert a
cause: :attr:`Alert.candidate_causes` lists possibilities (weather, sensor
failure, seasonal migration, habitat change, human activity, data gaps) and a
forest officer records the outcome in :attr:`Alert.resolution_notes`.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, utcnow
from app.models.enums import AlertKind, AlertSeverity, AlertStatus, AnomalyMethod, sa_enum

if TYPE_CHECKING:  # pragma: no cover
    from app.models.user import User
    from app.models.zone import ForestZone


class AnomalyScore(Base):
    """One scored time window for one metric in one zone."""

    __tablename__ = "anomaly_scores"
    __table_args__ = (Index("ix_anomaly_scores_zone_window", "zone_id", "window_end"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    zone_id: Mapped[int | None] = mapped_column(
        ForeignKey("forest_zones.id", ondelete="CASCADE"), index=True
    )
    #: e.g. ``detections.BIRD``, ``detections.total``, ``sensor.sound_level_db``
    metric: Mapped[str] = mapped_column(String(80), nullable=False)
    method: Mapped[AnomalyMethod] = mapped_column(
        sa_enum(AnomalyMethod, 24), nullable=False
    )
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    window_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    observed_value: Mapped[float] = mapped_column(Float, nullable=False)
    baseline_value: Mapped[float | None] = mapped_column(Float)
    baseline_spread: Mapped[float | None] = mapped_column(Float)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    is_anomaly: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    details: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )

    zone: Mapped[ForestZone | None] = relationship()


class Alert(Base, TimestampMixin):
    __tablename__ = "alerts"
    __table_args__ = (Index("ix_alerts_status_detected", "status", "detected_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[AlertKind] = mapped_column(
        sa_enum(AlertKind, 32), nullable=False
    )
    severity: Mapped[AlertSeverity] = mapped_column(
        sa_enum(AlertSeverity, 12),
        default=AlertSeverity.MEDIUM,
        nullable=False,
    )
    status: Mapped[AlertStatus] = mapped_column(
        sa_enum(AlertStatus, 16),
        default=AlertStatus.OPEN,
        nullable=False,
        index=True,
    )
    zone_id: Mapped[int | None] = mapped_column(
        ForeignKey("forest_zones.id", ondelete="SET NULL"), index=True
    )
    device_id: Mapped[int | None] = mapped_column(ForeignKey("devices.id", ondelete="SET NULL"))
    anomaly_score_id: Mapped[int | None] = mapped_column(
        ForeignKey("anomaly_scores.id", ondelete="SET NULL")
    )

    title: Mapped[str] = mapped_column(String(200), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    #: Supporting numbers: observed vs baseline, window, contributing metrics.
    evidence: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    #: Possible explanations, ordered by plausibility. Never a conclusion.
    candidate_causes: Mapped[list[str] | None] = mapped_column(JSON)

    detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    acknowledged_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    #: The human conclusion after investigation — the only place a cause is stated.
    resolution_notes: Mapped[str | None] = mapped_column(Text)
    confirmed_cause: Mapped[str | None] = mapped_column(String(120))

    zone: Mapped[ForestZone | None] = relationship()
    acknowledged_by: Mapped[User | None] = relationship()
    anomaly_score: Mapped[AnomalyScore | None] = relationship()
