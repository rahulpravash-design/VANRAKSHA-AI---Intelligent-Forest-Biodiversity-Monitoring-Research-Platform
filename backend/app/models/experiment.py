"""The research experiment framework.

An :class:`Experiment` records a research question and its configuration; each
:class:`ExperimentRun` records one variant (image-only, audio-only, fused…) with
its metrics, so single-modality baselines and multimodal fusion can be compared
rather than assumed.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin
from app.models.enums import ExperimentStatus, sa_enum

if TYPE_CHECKING:  # pragma: no cover
    from app.models.user import User


class Experiment(Base, TimestampMixin):
    __tablename__ = "experiments"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    research_question: Mapped[str] = mapped_column(Text, nullable=False)
    hypothesis: Mapped[str | None] = mapped_column(Text)
    status: Mapped[ExperimentStatus] = mapped_column(
        sa_enum(ExperimentStatus, 16),
        default=ExperimentStatus.DRAFT,
        nullable=False,
    )
    #: Dataset spec, seed, thresholds, model versions — everything needed to
    #: reproduce the run.
    config: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))

    created_by: Mapped[User | None] = relationship()
    runs: Mapped[list[ExperimentRun]] = relationship(
        back_populates="experiment", cascade="all, delete-orphan"
    )


class ExperimentRun(Base):
    __tablename__ = "experiment_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    experiment_id: Mapped[int] = mapped_column(
        ForeignKey("experiments.id", ondelete="CASCADE"), index=True, nullable=False
    )
    #: ``image_only`` | ``audio_only`` | ``image_audio`` | ``image_audio_context``
    variant: Mapped[str] = mapped_column(String(60), nullable=False)
    #: precision / recall / f1 / mAP / accuracy / ece / latency_ms …
    metrics: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    per_class_metrics: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    confusion_matrix: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    sample_count: Mapped[int | None] = mapped_column(Integer)
    random_seed: Mapped[int | None] = mapped_column(Integer)
    notes: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    experiment: Mapped[Experiment] = relationship(back_populates="runs")
