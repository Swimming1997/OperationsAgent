from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from intelligence_engine.config import get_settings
from intelligence_engine.db.models import Employee, User
from intelligence_engine.db.session import get_db
from intelligence_engine.domain.auth_schemas import (
    AuthUserRead,
    BootstrapAdminRequest,
    BootstrapStatusResponse,
    ChangePasswordRequest,
    ChangePasswordResponse,
    LoginRequest,
    LoginResponse,
    LogoutResponse,
    RegisterRequest,
)
from intelligence_engine.domain.enums import UserRoleName
from intelligence_engine.security.auth import Principal, get_current_principal
from intelligence_engine.security.passwords import hash_password, verify_password
from intelligence_engine.security.tokens import create_access_token
from intelligence_engine.storage.repositories.product_repository import ProductRepository

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _auth_user_read(repo: ProductRepository, user: User) -> AuthUserRead:
    employee = repo.get_employee_for_user(user.id)
    return AuthUserRead(
        id=user.id,
        username=user.username,
        display_name=user.display_name,
        email=user.email,
        status=user.status,
        roles=repo.user_role_names(user.id),
        employee_id=employee.id if employee else None,
    )


def _issue_token(repo: ProductRepository, user: User) -> LoginResponse:
    settings = get_settings()
    roles = repo.user_role_names(user.id)
    token = create_access_token(
        user_id=user.id,
        roles=roles,
        secret=settings.auth_secret_key,
        ttl_seconds=settings.auth_token_ttl_hours * 3600,
    )
    return LoginResponse(access_token=token, user=_auth_user_read(repo, user))


@router.get("/bootstrap-status", response_model=BootstrapStatusResponse)
def bootstrap_status(db: Session = Depends(get_db)) -> BootstrapStatusResponse:
    users_count = db.scalar(select(func.count()).select_from(User)) or 0
    admin_exists = False
    if users_count:
        repo = ProductRepository(db)
        for user in repo.list_users():
            if UserRoleName.ADMIN.value in repo.user_role_names(user.id):
                admin_exists = True
                break
    return BootstrapStatusResponse(
        users_count=users_count,
        admin_exists=admin_exists,
        needs_bootstrap=users_count == 0,
    )


@router.post("/bootstrap-admin", response_model=LoginResponse)
def bootstrap_admin(request: BootstrapAdminRequest, db: Session = Depends(get_db)) -> LoginResponse:
    users_count = db.scalar(select(func.count()).select_from(User)) or 0
    if users_count > 0:
        raise HTTPException(status_code=409, detail="users already exist")
    repo = ProductRepository(db)
    user = repo.create_user(
        username=request.username,
        display_name=request.display_name,
        email=request.email,
        password_hash=hash_password(request.password),
        role_names=[UserRoleName.ADMIN.value],
        metadata={},
    )
    db.commit()
    db.refresh(user)
    return _issue_token(repo, user)


@router.post("/login", response_model=LoginResponse)
def login(request: LoginRequest, db: Session = Depends(get_db)) -> LoginResponse:
    repo = ProductRepository(db)
    user = repo.get_user_by_username(request.username)
    if not user or not verify_password(request.password, user.password_hash):
        raise HTTPException(status_code=401, detail="invalid username or password")
    if user.status != "active":
        raise HTTPException(status_code=403, detail="user is disabled")
    return _issue_token(repo, user)


@router.post("/register", response_model=LoginResponse)
def register(request: RegisterRequest, db: Session = Depends(get_db)) -> LoginResponse:
    users_count = db.scalar(select(func.count()).select_from(User)) or 0
    if users_count == 0:
        raise HTTPException(status_code=409, detail="system needs bootstrap admin")
    repo = ProductRepository(db)
    username = request.username.strip()
    display_name = request.display_name.strip()
    email = request.email.strip() if request.email else None
    if not username:
        raise HTTPException(status_code=422, detail="username is required")
    if not display_name:
        raise HTTPException(status_code=422, detail="display name is required")
    if repo.get_user_by_username(username):
        raise HTTPException(status_code=409, detail="username already exists")
    user = repo.create_user(
        username=username,
        display_name=display_name,
        email=email or None,
        password_hash=hash_password(request.password),
        role_names=[UserRoleName.OPERATOR.value],
        metadata={},
    )
    db.commit()
    db.refresh(user)
    return _issue_token(repo, user)


@router.post("/logout", response_model=LogoutResponse)
def logout() -> LogoutResponse:
    return LogoutResponse()


@router.post("/change-password", response_model=ChangePasswordResponse)
def change_password(
    request: ChangePasswordRequest,
    principal: Principal = Depends(get_current_principal),
    db: Session = Depends(get_db),
) -> ChangePasswordResponse:
    user = db.get(User, principal.user_id)
    if not user:
        raise HTTPException(status_code=401, detail="unknown user")
    if not verify_password(request.current_password, user.password_hash):
        raise HTTPException(status_code=401, detail="current password is incorrect")
    if request.current_password == request.new_password:
        raise HTTPException(status_code=400, detail="new password must be different")
    ProductRepository(db).set_password(user, hash_password(request.new_password))
    db.commit()
    return ChangePasswordResponse()


@router.get("/me", response_model=AuthUserRead)
def auth_me(principal: Principal = Depends(get_current_principal), db: Session = Depends(get_db)) -> AuthUserRead:
    user = db.get(User, principal.user_id)
    if not user:
        raise HTTPException(status_code=401, detail="unknown user")
    return _auth_user_read(ProductRepository(db), user)
