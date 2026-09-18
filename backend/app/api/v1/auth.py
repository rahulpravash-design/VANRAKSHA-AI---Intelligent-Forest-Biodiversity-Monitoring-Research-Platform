"""Authentication endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Body, Request, status

from app.core.deps import CurrentUser, DbSession, OptionalUser, TokenPayload, capabilities_for
from app.schemas.auth import (
    LoginRequest,
    PasswordChangeRequest,
    RefreshRequest,
    RegisterRequest,
    TokenPair,
)
from app.schemas.common import Message
from app.schemas.user import MeResponse, UserPublic
from app.services import auth_service

router = APIRouter(prefix="/auth", tags=["authentication"])


@router.post(
    "/register",
    response_model=UserPublic,
    status_code=status.HTTP_201_CREATED,
    summary="Create a researcher or viewer account",
    responses={
        409: {"description": "Email address already registered"},
        422: {"description": "Weak password, invalid email, or a non-public role"},
    },
)
def register(
    db: DbSession, request: Request, payload: RegisterRequest = Body(...)
) -> UserPublic:
    """Self-registration.

    Only `RESEARCHER` and `VIEWER` accounts can be created here. Expert, forest
    officer and administrator accounts are created by an administrator through
    `POST /users`.
    """
    user = auth_service.register(db, payload, request)
    return UserPublic.model_validate(user)


@router.post(
    "/login",
    response_model=TokenPair,
    summary="Exchange credentials for an access and refresh token",
    responses={
        401: {"description": "Incorrect email address or password"},
        403: {"description": "Account deactivated"},
        429: {"description": "Too many attempts"},
    },
)
def login(db: DbSession, request: Request, payload: LoginRequest = Body(...)) -> TokenPair:
    return auth_service.login(db, payload, request)


@router.post(
    "/refresh",
    response_model=TokenPair,
    summary="Rotate a refresh token for a new token pair",
    responses={401: {"description": "Refresh token invalid, expired or revoked"}},
)
def refresh(db: DbSession, payload: RefreshRequest = Body(...)) -> TokenPair:
    """The presented refresh token is revoked as part of this call, so a stolen
    refresh token is usable at most once before the legitimate client's next
    refresh invalidates it."""
    return auth_service.refresh_access_token(db, payload.refresh_token)


@router.post("/logout", response_model=Message, summary="Revoke the current tokens")
def logout(
    db: DbSession,
    request: Request,
    user: OptionalUser,
    payload: TokenPayload,
    body: RefreshRequest | None = Body(default=None),
) -> Message:
    auth_service.logout(
        db,
        access_payload=payload,
        refresh_token=body.refresh_token if body else None,
        user=user,
        request=request,
    )
    return Message(detail="Signed out. The presented tokens have been revoked.")


@router.get("/me", response_model=MeResponse, summary="The signed-in user and their permissions")
def me(user: CurrentUser) -> MeResponse:
    return MeResponse(
        user=UserPublic.model_validate(user), capabilities=capabilities_for(user)
    )


@router.post(
    "/change-password",
    response_model=Message,
    summary="Change your own password",
    responses={401: {"description": "Current password incorrect"}},
)
def change_password(
    db: DbSession,
    request: Request,
    user: CurrentUser,
    payload: PasswordChangeRequest = Body(...),
) -> Message:
    auth_service.change_password(
        db, user, payload.current_password, payload.new_password, request
    )
    return Message(detail="Password updated.")
