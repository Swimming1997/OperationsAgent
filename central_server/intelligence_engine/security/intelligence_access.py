from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from intelligence_engine.db.models import PlatformAccount, ReferenceLibraryItem, utcnow
from intelligence_engine.domain.enums import UserRoleName
from intelligence_engine.security.auth import Principal
from intelligence_engine.storage.repositories.product_repository import ProductRepository

INTELLIGENCE_READ_ROLES = (
    UserRoleName.ADMIN,
    UserRoleName.SUPERVISOR,
    UserRoleName.OPERATOR,
    UserRoleName.SALES,
)

INTELLIGENCE_WRITE_ROLES = (
    UserRoleName.ADMIN,
    UserRoleName.SUPERVISOR,
    UserRoleName.OPERATOR,
)

OPERATOR_REFERENCE_REVOKE_WINDOW = timedelta(hours=24)


@dataclass(frozen=True)
class OperatorIntelligenceListScope:
    assigned_to_user_id: str | None = None
    discovered_by_account_ids: tuple[str, ...] = ()


def is_operator_pool_scope(principal: Principal) -> bool:
    return principal.has_role(UserRoleName.OPERATOR) and not principal.has_role(
        UserRoleName.ADMIN,
        UserRoleName.SUPERVISOR,
    )


def resolve_operator_intelligence_list_scope(
    db: Session,
    principal: Principal,
    assigned_to_user_id: str | None,
) -> OperatorIntelligenceListScope | None:
    """Operator lists: assigned to self OR discovered via owned platform accounts."""
    if not is_operator_pool_scope(principal):
        return None
    if assigned_to_user_id:
        return OperatorIntelligenceListScope(assigned_to_user_id=assigned_to_user_id)
    user_id = principal.user_id
    if not user_id:
        return OperatorIntelligenceListScope()
    employee = ProductRepository(db).get_employee_for_user(user_id)
    account_ids: tuple[str, ...] = ()
    if employee:
        account_ids = tuple(
            db.scalars(select(PlatformAccount.id).where(PlatformAccount.employee_id == employee.id)).all()
        )
    return OperatorIntelligenceListScope(assigned_to_user_id=user_id, discovered_by_account_ids=account_ids)


def ensure_can_revoke_reference_library_item(principal: Principal, item: ReferenceLibraryItem) -> None:
    if principal.has_role(UserRoleName.ADMIN, UserRoleName.SUPERVISOR):
        return
    if not principal.has_role(UserRoleName.OPERATOR):
        raise HTTPException(status_code=403, detail="insufficient role to archive reference library item")
    if not principal.user_id:
        raise HTTPException(status_code=403, detail="authentication required")
    if item.created_by_user_id != principal.user_id:
        raise HTTPException(status_code=403, detail="operator can only revoke own reference library items")
    created_at = item.created_at
    if created_at is None:
        raise HTTPException(status_code=403, detail="reference library item has no created_at")
    now = utcnow()
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    if now - created_at > OPERATOR_REFERENCE_REVOKE_WINDOW:
        raise HTTPException(status_code=403, detail="operator revoke window expired")
