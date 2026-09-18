"""Registration, login and token schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator

from app.core.security import validate_password_strength
from app.models.enums import PUBLIC_REGISTRATION_ROLES, UserRole
from app.schemas.user import UserPublic


class RegisterRequest(BaseModel):
    full_name: str = Field(min_length=2, max_length=120)
    email: EmailStr
    password: str = Field(min_length=1, max_length=256)
    password_confirm: str | None = None
    organization: str | None = Field(default=None, max_length=160)
    #: Only RESEARCHER and VIEWER may be self-selected. EXPERT, FOREST_OFFICER
    #: and ADMIN accounts are created or promoted by an administrator.
    role: UserRole = UserRole.VIEWER

    @field_validator("password")
    @classmethod
    def _strong_password(cls, value: str) -> str:
        problems = validate_password_strength(value)
        if problems:
            raise ValueError("password " + "; ".join(problems))
        return value

    @field_validator("role")
    @classmethod
    def _public_role_only(cls, value: UserRole) -> UserRole:
        if value not in PUBLIC_REGISTRATION_ROLES:
            allowed = ", ".join(sorted(r.value for r in PUBLIC_REGISTRATION_ROLES))
            raise ValueError(f"role must be one of: {allowed}")
        return value

    @model_validator(mode="after")
    def _passwords_match(self):
        if self.password_confirm is not None and self.password != self.password_confirm:
            raise ValueError("password_confirm does not match password")
        return self


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=256)


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = Field(description="Access-token lifetime in seconds")
    expires_at: datetime
    user: UserPublic


class RefreshRequest(BaseModel):
    refresh_token: str


class AccessToken(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    expires_at: datetime


class PasswordChangeRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=1, max_length=256)

    @field_validator("new_password")
    @classmethod
    def _strong_password(cls, value: str) -> str:
        problems = validate_password_strength(value)
        if problems:
            raise ValueError("new_password " + "; ".join(problems))
        return value
