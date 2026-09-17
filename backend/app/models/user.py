"""User accounts and role-based access."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin
from app.models.enums import UserRole, sa_enum

if TYPE_CHECKING:  # pragma: no cover
    from app.models.observation import Observation
    from app.models.verification import ExpertVerification


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    full_name: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        sa_enum(UserRole, 20), default=UserRole.VIEWER, nullable=False
    )
    organization: Mapped[str | None] = mapped_column(String(160))
    #: Free-text taxonomic expertise, used to route verification work to experts.
    expertise: Mapped[str | None] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    observations: Mapped[list[Observation]] = relationship(
        back_populates="researcher",
        foreign_keys="Observation.researcher_id",
        cascade="all, delete-orphan",
    )
    verifications: Mapped[list[ExpertVerification]] = relationship(
        back_populates="expert", cascade="all, delete-orphan"
    )

    # ------------------------------------------------------------- helpers
    @property
    def can_record_observations(self) -> bool:
        return self.role in {UserRole.ADMIN, UserRole.RESEARCHER, UserRole.FOREST_OFFICER}

    @property
    def can_verify(self) -> bool:
        return self.role in {UserRole.ADMIN, UserRole.EXPERT}

    @property
    def is_admin(self) -> bool:
        return self.role == UserRole.ADMIN

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<User {self.id} {self.email} {self.role}>"
