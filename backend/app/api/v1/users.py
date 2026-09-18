"""User administration."""

from __future__ import annotations

from fastapi import APIRouter, Body, Query, Request, status
from sqlalchemy import func, or_, select

from app.core.deps import AdminUser, CurrentUser, DbSession
from app.core.errors import NotFoundError, ValidationError
from app.models.enums import UserRole
from app.models.user import User
from app.schemas.common import Message, Page
from app.schemas.user import (
    UserAdminUpdate,
    UserCreateAdmin,
    UserPublic,
    UserUpdate,
)
from app.services import audit, auth_service

router = APIRouter(prefix="/users", tags=["users"])


@router.get("", response_model=Page[UserPublic], summary="List accounts (administrators only)")
def list_users(
    db: DbSession,
    _admin: AdminUser,
    role: UserRole | None = Query(default=None),
    is_active: bool | None = Query(default=None),
    search: str | None = Query(default=None, max_length=120),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> Page[UserPublic]:
    statement = select(User)
    if role is not None:
        statement = statement.where(User.role == role)
    if is_active is not None:
        statement = statement.where(User.is_active.is_(is_active))
    if search:
        pattern = f"%{search.strip().lower()}%"
        statement = statement.where(
            or_(
                func.lower(User.full_name).like(pattern),
                func.lower(User.email).like(pattern),
                func.lower(func.coalesce(User.organization, "")).like(pattern),
            )
        )
    total = db.execute(select(func.count()).select_from(statement.subquery())).scalar_one()
    rows = (
        db.execute(statement.order_by(User.full_name).limit(limit).offset(offset))
        .scalars()
        .all()
    )
    return Page[UserPublic](
        items=[UserPublic.model_validate(row) for row in rows],
        total=int(total),
        limit=limit,
        offset=offset,
    )


@router.post(
    "",
    response_model=UserPublic,
    status_code=status.HTTP_201_CREATED,
    summary="Create an account with any role (administrators only)",
)
def create_user(
    db: DbSession, request: Request, admin: AdminUser, payload: UserCreateAdmin = Body(...)
) -> UserPublic:
    """How expert, forest officer and additional administrator accounts are made."""
    from app.core.security import validate_password_strength

    problems = validate_password_strength(payload.password)
    if problems:
        raise ValidationError("password " + "; ".join(problems))
    user = auth_service.create_user_as_admin(db, payload, actor=admin, request=request)
    return UserPublic.model_validate(user)


@router.patch("/me", response_model=UserPublic, summary="Update your own profile")
def update_me(
    db: DbSession, request: Request, user: CurrentUser, payload: UserUpdate = Body(...)
) -> UserPublic:
    changes = payload.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(user, field, value)
    audit.record(
        db,
        "user.update_self",
        user=user,
        entity="user",
        entity_id=user.id,
        request=request,
        context={"fields": sorted(changes)},
    )
    db.commit()
    db.refresh(user)
    return UserPublic.model_validate(user)


@router.get("/{user_id}", response_model=UserPublic, summary="Read an account")
def get_user(db: DbSession, _admin: AdminUser, user_id: int) -> UserPublic:
    user = db.get(User, user_id)
    if user is None:
        raise NotFoundError(f"No user with id {user_id}.")
    return UserPublic.model_validate(user)


@router.patch(
    "/{user_id}",
    response_model=UserPublic,
    summary="Change an account's role or active state (administrators only)",
)
def update_user(
    db: DbSession,
    request: Request,
    admin: AdminUser,
    user_id: int,
    payload: UserAdminUpdate = Body(...),
) -> UserPublic:
    user = db.get(User, user_id)
    if user is None:
        raise NotFoundError(f"No user with id {user_id}.")
    changes = payload.model_dump(exclude_unset=True)

    # Guard against an administrator locking everyone out of administration.
    if user.id == admin.id and (
        changes.get("is_active") is False or changes.get("role") not in (None, UserRole.ADMIN)
    ):
        raise ValidationError(
            "You cannot remove your own administrator access. Ask another "
            "administrator to make this change."
        )
    if changes.get("role") is not None and user.role == UserRole.ADMIN:
        remaining = db.execute(
            select(func.count(User.id)).where(
                User.role == UserRole.ADMIN, User.is_active.is_(True), User.id != user.id
            )
        ).scalar_one()
        if not remaining and changes["role"] != UserRole.ADMIN:
            raise ValidationError(
                "This is the last active administrator; promote another account first."
            )

    for field, value in changes.items():
        setattr(user, field, value)
    audit.record(
        db,
        "user.admin_update",
        user=admin,
        entity="user",
        entity_id=user.id,
        request=request,
        context={"fields": sorted(changes), "target_email": user.email},
    )
    db.commit()
    db.refresh(user)
    return UserPublic.model_validate(user)


@router.delete(
    "/{user_id}",
    response_model=Message,
    summary="Deactivate an account (administrators only)",
)
def deactivate_user(
    db: DbSession, request: Request, admin: AdminUser, user_id: int
) -> Message:
    """Deactivation rather than deletion.

    Field observations reference their recorder, and the research record must
    stay attributable, so accounts are disabled instead of removed.
    """
    user = db.get(User, user_id)
    if user is None:
        raise NotFoundError(f"No user with id {user_id}.")
    if user.id == admin.id:
        raise ValidationError("You cannot deactivate your own account.")
    user.is_active = False
    audit.record(
        db,
        "user.deactivate",
        user=admin,
        entity="user",
        entity_id=user.id,
        request=request,
        context={"target_email": user.email},
    )
    db.commit()
    return Message(detail=f"{user.email} has been deactivated.")
