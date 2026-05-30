from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from intelligence_engine.api.account_access import get_principal_employee_id
from intelligence_engine.db.models import Job, PlatformAccount, TaskRun
from intelligence_engine.domain.enums import UserRoleName
from intelligence_engine.security.auth import Principal


def is_operator_only(principal: Principal) -> bool:
    return principal.has_role(UserRoleName.OPERATOR) and not principal.has_role(
        UserRoleName.ADMIN,
        UserRoleName.SUPERVISOR,
    )


def operator_scope_employee_id(db: Session, principal: Principal) -> str | None:
    if not is_operator_only(principal):
        return None
    employee_id = get_principal_employee_id(db, principal)
    if not employee_id:
        raise HTTPException(status_code=403, detail="operator has no employee profile")
    return employee_id


def task_run_belongs_to_employee(db: Session, task_run_id: str, employee_id: str) -> bool:
    run = db.get(TaskRun, task_run_id)
    if not run or not run.executor_account_id:
        return False
    account = db.get(PlatformAccount, run.executor_account_id)
    return bool(account and account.employee_id == employee_id)


def ensure_task_run_operator_access(db: Session, principal: Principal, task_run_id: str) -> None:
    if not is_operator_only(principal):
        return
    employee_id = operator_scope_employee_id(db, principal)
    if not db.get(TaskRun, task_run_id):
        raise HTTPException(status_code=404, detail="task run not found")
    if not task_run_belongs_to_employee(db, task_run_id, employee_id):
        raise HTTPException(status_code=404, detail="task run not found")


def ensure_job_operator_access(db: Session, principal: Principal, job_id: str) -> None:
    if not is_operator_only(principal):
        return
    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    if not job.task_run_id:
        raise HTTPException(status_code=404, detail="job not found")
    ensure_task_run_operator_access(db, principal, job.task_run_id)
