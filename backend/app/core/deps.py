"""FastAPI dependencies: the current user and the role guards."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from typing import Annotated

import jwt
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.errors import AuthenticationError, InactiveAccountError, PermissionDeniedError
from app.core.security import decode_token
from app.db.session import get_db
from app.models.enums import PRECISE_LOCATION_ROLES, UserRole
from app.models.user import User
from app.schemas.user import UserCapabilities

#: ``auto_error=False`` so anonymous access reaches the endpoint and the public
#: read-only routes can serve generalised data instead of returning 403.
bearer_scheme = HTTPBearer(auto_error=False, scheme_name="JWT")

DbSession = Annotated[Session, Depends(get_db)]
Credentials = Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)]


def get_token_payload(credentials: Credentials) -> dict | None:
    if credentials is None or not credentials.credentials:
        return None
    try:
        return decode_token(credentials.credentials, expected_type="access")
    except jwt.ExpiredSignatureError as exc:
        raise AuthenticationError("Access token has expired.") from exc
    except jwt.PyJWTError as exc:
        raise AuthenticationError("Access token is invalid.") from exc


TokenPayload = Annotated[dict | None, Depends(get_token_payload)]


def get_current_user_optional(db: DbSession, payload: TokenPayload) -> User | None:
    """The signed-in user, or ``None`` for anonymous callers."""
    if payload is None:
        return None
    from app.services.auth_service import is_revoked

    if is_revoked(db, payload.get("jti", "")):
        raise AuthenticationError("This token has been revoked. Please sign in again.")
    user = db.get(User, int(payload["sub"]))
    if user is None:
        raise AuthenticationError("Access token is invalid.")
    if not user.is_active:
        raise InactiveAccountError()
    return user


OptionalUser = Annotated[User | None, Depends(get_current_user_optional)]


def get_current_user(user: OptionalUser) -> User:
    if user is None:
        raise AuthenticationError("Authentication is required for this endpoint.")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_roles(*roles: UserRole) -> Callable[..., User]:
    """Build a dependency that admits only the given roles.

    A closure rather than a callable class: FastAPI resolves a dependency's
    annotations through ``call.__globals__``, which a class *instance* does not
    have — so a callable-class guard combined with ``from __future__ import
    annotations`` leaves ``CurrentUser`` as an unresolved forward reference and
    breaks OpenAPI generation. A function carries its module globals, so the
    annotations resolve normally.
    """
    allowed = set(roles)

    def guard(user: CurrentUser, request: Request) -> User:
        if user.role not in allowed:
            names = ", ".join(sorted(role.value for role in allowed))
            raise PermissionDeniedError(
                f"This action requires one of: {names}. Your role is {user.role.value}.",
                required_roles=sorted(role.value for role in allowed),
                your_role=user.role.value,
                path=str(request.url.path),
            )
        return user

    return guard


require_admin = require_roles(UserRole.ADMIN)
require_recorder = require_roles(
    UserRole.ADMIN, UserRole.RESEARCHER, UserRole.FOREST_OFFICER
)
require_expert = require_roles(UserRole.ADMIN, UserRole.EXPERT)
require_officer = require_roles(UserRole.ADMIN, UserRole.FOREST_OFFICER)
require_curator = require_roles(UserRole.ADMIN, UserRole.EXPERT, UserRole.RESEARCHER)

AdminUser = Annotated[User, Depends(require_admin)]
RecorderUser = Annotated[User, Depends(require_recorder)]
ExpertUser = Annotated[User, Depends(require_expert)]
OfficerUser = Annotated[User, Depends(require_officer)]
CuratorUser = Annotated[User, Depends(require_curator)]


def capabilities_for(user: User) -> UserCapabilities:
    """What this user may do — the frontend renders its navigation from this."""
    return UserCapabilities(
        can_record_observations=user.role
        in {UserRole.ADMIN, UserRole.RESEARCHER, UserRole.FOREST_OFFICER},
        can_verify=user.role in {UserRole.ADMIN, UserRole.EXPERT},
        can_manage_species=user.role in {UserRole.ADMIN, UserRole.EXPERT, UserRole.RESEARCHER},
        can_manage_users=user.role == UserRole.ADMIN,
        can_manage_alerts=user.role in {UserRole.ADMIN, UserRole.FOREST_OFFICER},
        can_run_experiments=user.role in {UserRole.ADMIN, UserRole.RESEARCHER},
        can_see_precise_locations=user.role in PRECISE_LOCATION_ROLES,
    )


def get_ai_engine_dep(db: DbSession) -> Iterator:
    from app.services.ai_client import AIEngine

    yield AIEngine(db)
