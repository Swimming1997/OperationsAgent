from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from intelligence_engine.db.models import Employee, LocalAgent, PlatformAccount
from intelligence_engine.domain.enums import UserRoleName
from intelligence_engine.security.auth import Principal
from intelligence_engine.storage.repositories.product_repository import ProductRepository


def get_principal_employee_id(db: Session, principal: Principal) -> str | None:
    if principal.has_role(UserRoleName.ADMIN, UserRoleName.SUPERVISOR):
        return None
    employee = ProductRepository(db).get_employee_for_user(principal.user_id or "")
    return employee.id if employee else None


def ensure_account_readable(db: Session, principal: Principal, account: PlatformAccount) -> None:
    if principal.has_role(UserRoleName.ADMIN, UserRoleName.SUPERVISOR):
        return
    employee_id = get_principal_employee_id(db, principal)
    if not employee_id or account.employee_id != employee_id:
        raise HTTPException(status_code=403, detail="insufficient permission for this account")


def ensure_account_writable(db: Session, principal: Principal, account: PlatformAccount) -> None:
    ensure_account_readable(db, principal, account)
    if principal.has_role(UserRoleName.OPERATOR):
        return
    if not principal.has_role(UserRoleName.ADMIN, UserRoleName.SUPERVISOR):
        raise HTTPException(status_code=403, detail="insufficient role")


def ensure_agent_readable(db: Session, principal: Principal, agent: LocalAgent) -> None:
    if principal.has_role(UserRoleName.ADMIN, UserRoleName.SUPERVISOR):
        return
    employee_id = get_principal_employee_id(db, principal)
    if not employee_id:
        raise HTTPException(status_code=403, detail="operator has no employee profile")
    if agent.employee_id == employee_id:
        return
    bound = db.scalar(
        select(PlatformAccount.id)
        .where(
            PlatformAccount.employee_id == employee_id,
            PlatformAccount.default_agent_id == agent.id,
        )
        .limit(1)
    )
    if bound:
        return
    raise HTTPException(status_code=403, detail="insufficient permission for this agent")


def attach_agent_to_employee(db: Session, *, agent_id: str | None, employee_id: str | None) -> None:
    if not agent_id or not employee_id:
        return
    agent = db.get(LocalAgent, agent_id)
    if not agent:
        return
    if agent.employee_id is None or agent.employee_id == employee_id:
        agent.employee_id = employee_id


def set_agent_employee(db: Session, *, agent_id: str, employee_id: str | None) -> LocalAgent:
    agent = db.get(LocalAgent, agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="agent not found")
    if employee_id:
        employee = db.get(Employee, employee_id)
        if not employee:
            raise HTTPException(status_code=404, detail="employee not found")
    agent.employee_id = employee_id
    return agent
