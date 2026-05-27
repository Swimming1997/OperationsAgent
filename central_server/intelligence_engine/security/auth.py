from dataclasses import dataclass

from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from intelligence_engine.config import get_settings
from intelligence_engine.db.models import User
from intelligence_engine.db.session import get_db
from intelligence_engine.domain.enums import UserRoleName
from intelligence_engine.security.tokens import TokenError, decode_access_token
from intelligence_engine.storage.repositories.product_repository import ProductRepository


@dataclass(frozen=True)
class Principal:
    user_id: str | None
    role_names: frozenset[str]

    def has_role(self, *roles: UserRoleName | str) -> bool:
        expected = {getattr(role, "value", role) for role in roles}
        return bool(self.role_names.intersection(expected))


def _principal_from_bearer(authorization: str | None, db: Session) -> Principal | None:
    if not authorization or not authorization.lower().startswith("bearer "):
        return None
    token = authorization[7:].strip()
    if not token:
        raise HTTPException(status_code=401, detail="invalid authorization header")
    settings = get_settings()
    try:
        payload = decode_access_token(token, settings.auth_secret_key)
    except TokenError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    user = db.get(User, payload["sub"])
    if not user:
        raise HTTPException(status_code=401, detail="unknown user")
    if user.status != "active":
        raise HTTPException(status_code=403, detail="user is disabled")
    roles = payload.get("roles")
    if not isinstance(roles, list) or not roles:
        roles = ProductRepository(db).user_role_names(user.id)
    return Principal(user_id=user.id, role_names=frozenset(str(role) for role in roles))


def get_optional_principal(
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
    x_role: str | None = Header(default=None, alias="X-Role"),
    x_user_roles: str | None = Header(default=None, alias="X-User-Roles"),
    db: Session = Depends(get_db),
) -> Principal:
    bearer_principal = _principal_from_bearer(authorization, db)
    if bearer_principal is not None:
        return bearer_principal

    injected_roles = x_user_roles or x_role
    if injected_roles:
        if not get_settings().allow_header_auth:
            raise HTTPException(status_code=401, detail="header auth is disabled")
        return Principal(user_id=x_user_id, role_names=frozenset(role.strip() for role in injected_roles.split(",") if role.strip()))
    if not x_user_id:
        return Principal(user_id=None, role_names=frozenset())
    user = db.get(User, x_user_id)
    if not user:
        raise HTTPException(status_code=401, detail="unknown user")
    if user.status != "active":
        raise HTTPException(status_code=403, detail="user is disabled")
    roles = ProductRepository(db).user_role_names(user.id)
    return Principal(user_id=user.id, role_names=frozenset(roles))


def get_current_principal(principal: Principal = Depends(get_optional_principal)) -> Principal:
    if not principal.user_id:
        raise HTTPException(status_code=401, detail="authentication required")
    return principal


def require_any_role(*roles: UserRoleName):
    def dependency(principal: Principal = Depends(get_optional_principal)) -> Principal:
        if not principal.has_role(*roles):
            raise HTTPException(status_code=403, detail="insufficient role")
        return principal

    return dependency
