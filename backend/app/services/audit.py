"""Audit logging.

Recorded for authentication events, permission denials, data changes and — most
importantly for a biodiversity platform — every access to precise coordinates of
a sensitive species, so it is possible to answer "who looked up where the tigers
are?" after the fact.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import Request
from sqlalchemy.orm import Session

from app.models.audit import AuditLog
from app.models.user import User

logger = logging.getLogger(__name__)


def client_ip(request: Request | None) -> str | None:
    if request is None:
        return None
    # Honour a reverse proxy's forwarding header, taking the left-most entry.
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()[:64]
    return request.client.host[:64] if request.client else None


def record(
    db: Session,
    action: str,
    *,
    user: User | None = None,
    entity: str | None = None,
    entity_id: int | None = None,
    request: Request | None = None,
    context: dict[str, Any] | None = None,
    commit: bool = False,
) -> AuditLog:
    """Append an audit entry.

    The caller normally lets the surrounding transaction commit this along with
    the change it describes, so an audit row can never claim an action that was
    rolled back.
    """
    entry = AuditLog(
        user_id=user.id if user else None,
        actor_email=user.email if user else None,
        action=action,
        entity=entity,
        entity_id=entity_id,
        ip_address=client_ip(request),
        user_agent=(request.headers.get("user-agent", "")[:255] or None) if request else None,
        context=context,
    )
    db.add(entry)
    if commit:
        db.commit()
    logger.info(
        "audit action=%s entity=%s id=%s actor=%s",
        action,
        entity,
        entity_id,
        entry.actor_email or "anonymous",
    )
    return entry
