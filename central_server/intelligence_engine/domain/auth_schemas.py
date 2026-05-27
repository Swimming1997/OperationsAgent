from __future__ import annotations

from datetime import datetime

from pydantic import Field

from intelligence_engine.domain.enums import UserRoleName
from intelligence_engine.domain.schemas import ApiModel


class BootstrapStatusResponse(ApiModel):
    users_count: int
    admin_exists: bool
    needs_bootstrap: bool


class BootstrapAdminRequest(ApiModel):
    username: str
    display_name: str
    email: str | None = None
    password: str


class LoginRequest(ApiModel):
    username: str
    password: str


class RegisterRequest(ApiModel):
    username: str = Field(min_length=3, max_length=128)
    display_name: str = Field(min_length=1, max_length=128)
    email: str | None = None
    password: str = Field(min_length=8)


class ChangePasswordRequest(ApiModel):
    current_password: str
    new_password: str = Field(min_length=8)


class AuthUserRead(ApiModel):
    id: str
    username: str
    display_name: str
    email: str | None = None
    status: str
    roles: list[str] = []
    employee_id: str | None = None


class LoginResponse(ApiModel):
    access_token: str
    token_type: str = "bearer"
    user: AuthUserRead


class LogoutResponse(ApiModel):
    message: str = "logged out"


class ChangePasswordResponse(ApiModel):
    message: str = "password updated"
