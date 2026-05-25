from __future__ import annotations

from datetime import datetime

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
