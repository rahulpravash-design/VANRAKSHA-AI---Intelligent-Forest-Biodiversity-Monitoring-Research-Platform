"""Server-side token revocation (logout / forced sign-out)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, utcnow


class RevokedToken(Base):
    """A token id (``jti``) that must no longer be accepted.

    Rows can safely be pruned once ``expires_at`` has passed — see
    :func:`app.services.auth_service.prune_revoked_tokens`.
    """

    __tablename__ = "revoked_tokens"
    __table_args__ = (Index("ix_revoked_tokens_expires_at", "expires_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    jti: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    token_type: Mapped[str] = mapped_column(String(16), default="access", nullable=False)
    reason: Mapped[str | None] = mapped_column(String(120))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
