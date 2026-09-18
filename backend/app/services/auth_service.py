"""Registration, login, refresh, logout and password change."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

import jwt
from fastapi import Request
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import (
    AuthenticationError,
    ConflictError,
    InactiveAccountError,
    ValidationError,
)
from app.core.rate_limit import auth_limiter
from app.core.security import (
    create_token,
    decode_token,
    hash_password,
    needs_rehash,
    verify_password,
)
from app.models.auth import RevokedToken
from app.models.enums import UserRole
from app.models.user import User
from app.schemas.auth import LoginRequest, RegisterRequest, TokenPair
from app.schemas.user import UserCreateAdmin, UserPublic
from app.services import audit

logger = logging.getLogger(__name__)


def normalise_email(email: str) -> str:
    return email.strip().lower()


def get_user_by_email(db: Session, email: str) -> User | None:
    return db.execute(
        select(User).where(User.email == normalise_email(email))
    ).scalar_one_or_none()


# --------------------------------------------------------------------------- #
# registration
# --------------------------------------------------------------------------- #
def register(db: Session, payload: RegisterRequest, request: Request | None = None) -> User:
    """Create a self-registered account.

    The schema already restricts ``role`` to RESEARCHER or VIEWER; this is the
    second, server-side check, so a future caller that bypasses the schema still
    cannot mint an administrator.
    """
    email = normalise_email(payload.email)
    if get_user_by_email(db, email) is not None:
        raise ConflictError("An account with this email address already exists.")
    if payload.role not in {UserRole.RESEARCHER, UserRole.VIEWER}:
        raise ValidationError("Only researcher and viewer accounts can self-register.")

    user = User(
        full_name=payload.full_name.strip(),
        email=email,
        password_hash=hash_password(payload.password),
        role=payload.role,
        organization=(payload.organization or "").strip() or None,
        is_active=True,
    )
    db.add(user)
    db.flush()
    audit.record(
        db,
        "auth.register",
        user=user,
        entity="user",
        entity_id=user.id,
        request=request,
        context={"role": str(user.role)},
    )
    db.commit()
    db.refresh(user)
    return user


def create_user_as_admin(
    db: Session, payload: UserCreateAdmin, *, actor: User, request: Request | None = None
) -> User:
    """Administrator-side creation — any role, including EXPERT and ADMIN."""
    email = normalise_email(payload.email)
    if get_user_by_email(db, email) is not None:
        raise ConflictError("An account with this email address already exists.")
    user = User(
        full_name=payload.full_name.strip(),
        email=email,
        password_hash=hash_password(payload.password),
        role=payload.role,
        organization=(payload.organization or "").strip() or None,
        expertise=(payload.expertise or "").strip() or None,
        is_active=payload.is_active,
    )
    db.add(user)
    db.flush()
    audit.record(
        db,
        "user.create",
        user=actor,
        entity="user",
        entity_id=user.id,
        request=request,
        context={"role": str(user.role), "email": user.email},
    )
    db.commit()
    db.refresh(user)
    return user


# --------------------------------------------------------------------------- #
# login
# --------------------------------------------------------------------------- #
def _issue_tokens(db: Session, user: User) -> TokenPair:
    access_token, _, expires_at = create_token(user.id, "access", role=str(user.role))
    refresh_token, _, _ = create_token(user.id, "refresh", role=str(user.role))
    return TokenPair(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.access_token_expire_minutes * 60,
        expires_at=expires_at,
        user=UserPublic.model_validate(user),
    )


def login(db: Session, payload: LoginRequest, request: Request | None = None) -> TokenPair:
    """Authenticate and issue an access/refresh pair.

    Wrong password and unknown email return the same error, so the endpoint
    cannot be used to enumerate registered addresses. Rate limiting is keyed on
    the client address *and* the submitted email, which slows both spraying one
    password across many accounts and many passwords against one account.
    """
    email = normalise_email(payload.email)
    auth_limiter.check(f"login:{audit.client_ip(request) or 'unknown'}")
    auth_limiter.check(f"login:{email}")

    user = get_user_by_email(db, email)
    if user is None or not verify_password(payload.password, user.password_hash):
        audit.record(
            db,
            "auth.login_failed",
            entity="user",
            entity_id=user.id if user else None,
            request=request,
            context={"email": email},
            commit=True,
        )
        raise AuthenticationError("Incorrect email address or password.")
    if not user.is_active:
        audit.record(
            db,
            "auth.login_inactive",
            user=user,
            entity="user",
            entity_id=user.id,
            request=request,
            commit=True,
        )
        raise InactiveAccountError()

    # Upgrade the stored hash if a stronger scheme became available.
    if needs_rehash(user.password_hash):
        user.password_hash = hash_password(payload.password)
    user.last_login_at = datetime.now(UTC)
    audit.record(db, "auth.login", user=user, entity="user", entity_id=user.id, request=request)
    db.commit()
    db.refresh(user)
    return _issue_tokens(db, user)


# --------------------------------------------------------------------------- #
# refresh / logout
# --------------------------------------------------------------------------- #
def is_revoked(db: Session, jti: str) -> bool:
    return (
        db.execute(select(RevokedToken.id).where(RevokedToken.jti == jti)).first() is not None
    )


def refresh_access_token(db: Session, refresh_token: str) -> TokenPair:
    try:
        payload = decode_token(refresh_token, expected_type="refresh")
    except jwt.PyJWTError as exc:
        raise AuthenticationError("Refresh token is invalid or has expired.") from exc

    jti = payload.get("jti", "")
    if jti and is_revoked(db, jti):
        raise AuthenticationError("Refresh token has been revoked.")
    user = db.get(User, int(payload["sub"]))
    if user is None:
        raise AuthenticationError("Refresh token is invalid or has expired.")
    if not user.is_active:
        raise InactiveAccountError()

    # Rotate: the presented refresh token cannot be replayed after this call.
    revoke(db, payload, reason="rotated", user=user)
    tokens = _issue_tokens(db, user)
    db.commit()
    return tokens


def revoke(
    db: Session, payload: dict, *, reason: str, user: User | None = None
) -> RevokedToken | None:
    jti = payload.get("jti")
    if not jti:
        return None
    if is_revoked(db, jti):
        return None
    expires_at = datetime.fromtimestamp(int(payload["exp"]), tz=UTC)
    entry = RevokedToken(
        jti=jti,
        user_id=user.id if user else None,
        token_type=payload.get("type", "access"),
        reason=reason,
        expires_at=expires_at,
    )
    db.add(entry)
    return entry


def logout(
    db: Session,
    *,
    access_payload: dict | None,
    refresh_token: str | None,
    user: User | None,
    request: Request | None = None,
) -> None:
    """Revoke the presented tokens server-side."""
    if access_payload:
        revoke(db, access_payload, reason="logout", user=user)
    if refresh_token:
        try:
            refresh_payload = decode_token(refresh_token, expected_type="refresh")
        except jwt.PyJWTError:
            logger.debug("ignoring an unparseable refresh token on logout")
        else:
            revoke(db, refresh_payload, reason="logout", user=user)
    audit.record(
        db,
        "auth.logout",
        user=user,
        entity="user",
        entity_id=user.id if user else None,
        request=request,
    )
    db.commit()


def prune_revoked_tokens(db: Session) -> int:
    """Delete revocation rows whose tokens have expired anyway."""
    result = db.execute(
        delete(RevokedToken).where(RevokedToken.expires_at < datetime.now(UTC))
    )
    db.commit()
    return int(result.rowcount or 0)


def change_password(
    db: Session,
    user: User,
    current_password: str,
    new_password: str,
    request: Request | None = None,
) -> None:
    if not verify_password(current_password, user.password_hash):
        raise AuthenticationError("Current password is incorrect.")
    if verify_password(new_password, user.password_hash):
        raise ValidationError("The new password must differ from the current one.")
    user.password_hash = hash_password(new_password)
    audit.record(
        db, "auth.password_change", user=user, entity="user", entity_id=user.id, request=request
    )
    db.commit()
