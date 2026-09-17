"""User schemas. Password hashes are never part of any response model."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

from app.models.enums import UserRole
from app.schemas.common import ORMModel


class UserPublic(ORMModel):
    id: int
    full_name: str
    email: EmailStr
    role: UserRole
    organization: str | None = None
    expertise: str | None = None
    is_active: bool
    created_at: datetime
    last_login_at: datetime | None = None


class UserCreateAdmin(BaseModel):
    """Administrator-side creation — any role, including EXPERT and ADMIN."""

    full_name: str = Field(min_length=2, max_length=120)
    email: EmailStr
    password: str = Field(min_length=1, max_length=256)
    role: UserRole
    organization: str | None = Field(default=None, max_length=160)
    expertise: str | None = Field(default=None, max_length=255)
    is_active: bool = True


class UserUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=2, max_length=120)
    organization: str | None = Field(default=None, max_length=160)
    expertise: str | None = Field(default=None, max_length=255)


class UserAdminUpdate(UserUpdate):
    role: UserRole | None = None
    is_active: bool | None = None


class UserCapabilities(BaseModel):
    """What the signed-in user may do — drives the frontend navigation."""

    can_record_observations: bool
    can_verify: bool
    can_manage_species: bool
    can_manage_users: bool
    can_manage_alerts: bool
    can_run_experiments: bool
    can_see_precise_locations: bool


class MeResponse(BaseModel):
    user: UserPublic
    capabilities: UserCapabilities
