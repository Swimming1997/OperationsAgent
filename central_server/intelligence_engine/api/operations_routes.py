from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from intelligence_engine.db.session import get_db
from intelligence_engine.domain.enums import UserRoleName
from intelligence_engine.domain.operations_schemas import (
    BulkOperationRequest,
    BulkOperationResult,
    JobDetailOps,
    JobListResponse,
    JobQueueSummary,
    LegacyCleanupRequest,
    TaskRunDetailOps,
    TaskRunListOpsResponse,
)
from intelligence_engine.security.auth import Principal, get_optional_principal, require_any_role
from intelligence_engine.services.job_operations_service import JobOperationsService

router = APIRouter(prefix="/api/operations", tags=["operations"])


def _service(db: Session) -> JobOperationsService:
    return JobOperationsService(db)


def _read_roles(principal: Principal):
    return require_any_role(UserRoleName.ADMIN, UserRoleName.SUPERVISOR, UserRoleName.OPERATOR)(principal)


def _write_roles(principal: Principal):
    return require_any_role(UserRoleName.ADMIN, UserRoleName.SUPERVISOR)(principal)


@router.get("/queue-summary", response_model=JobQueueSummary)
def get_queue_summary(
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_optional_principal),
):
    _read_roles(principal)
    summary = _service(db).queue_summary()
    db.commit()
    return summary


@router.get("/task-runs", response_model=TaskRunListOpsResponse)
def list_task_runs_ops(
    template_id: str | None = None,
    trigger_type: str | None = None,
    status: str | None = None,
    has_active_jobs: bool | None = None,
    created_after: datetime | None = None,
    created_before: datetime | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_optional_principal),
):
    _read_roles(principal)
    body = _service(db).list_task_runs(
        template_id=template_id,
        trigger_type=trigger_type,
        status=status,
        has_active_jobs=has_active_jobs,
        created_after=created_after,
        created_before=created_before,
        page=page,
        page_size=page_size,
    )
    db.commit()
    return body


@router.get("/task-runs/{task_run_id}", response_model=TaskRunDetailOps)
def get_task_run_ops(
    task_run_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_optional_principal),
):
    _read_roles(principal)
    try:
        body = _service(db).get_task_run_detail(task_run_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="task run not found") from None
    db.commit()
    return body


@router.get("/jobs", response_model=JobListResponse)
def list_jobs_ops(
    job_type: str | None = None,
    status: str | None = None,
    agent_id: str | None = None,
    task_run_id: str | None = None,
    priority_max: int | None = None,
    legacy_only: bool | None = None,
    stale_running_only: bool | None = None,
    created_after: datetime | None = None,
    created_before: datetime | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_optional_principal),
):
    _read_roles(principal)
    body = _service(db).list_jobs(
        job_type=job_type,
        status=status,
        agent_id=agent_id,
        task_run_id=task_run_id,
        priority_max=priority_max,
        legacy_only=legacy_only,
        stale_running_only=stale_running_only,
        created_after=created_after,
        created_before=created_before,
        page=page,
        page_size=page_size,
    )
    db.commit()
    return body


@router.get("/jobs/{job_id}", response_model=JobDetailOps)
def get_job_ops(
    job_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_optional_principal),
):
    _read_roles(principal)
    try:
        body = _service(db).get_job_detail(job_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="job not found") from None
    db.commit()
    return body


@router.post("/jobs/{job_id}/cancel", response_model=BulkOperationResult)
def cancel_job_ops(
    job_id: str,
    request: BulkOperationRequest,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_optional_principal),
):
    _write_roles(principal)
    try:
        result = _service(db).cancel_job(job_id, reason=request.reason, actor_user_id=principal.user_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="job not found") from None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.commit()
    return result


@router.post("/jobs/{job_id}/retry", response_model=BulkOperationResult)
def retry_job_ops(
    job_id: str,
    request: BulkOperationRequest,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_optional_principal),
):
    _write_roles(principal)
    try:
        result = _service(db).retry_job(job_id, reason=request.reason, actor_user_id=principal.user_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="job not found") from None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.commit()
    return result


@router.post("/task-runs/{task_run_id}/cancel-pending", response_model=BulkOperationResult)
def cancel_task_run_pending_ops(
    task_run_id: str,
    request: BulkOperationRequest,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_optional_principal),
):
    _write_roles(principal)
    result = _service(db).cancel_task_run_pending(task_run_id, reason=request.reason, actor_user_id=principal.user_id)
    db.commit()
    return result


@router.post("/task-runs/{task_run_id}/retry", response_model=BulkOperationResult)
def retry_task_run_ops(
    task_run_id: str,
    request: BulkOperationRequest,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_optional_principal),
):
    _write_roles(principal)
    result = _service(db).retry_task_run(task_run_id, reason=request.reason, actor_user_id=principal.user_id)
    db.commit()
    return result


@router.post("/jobs/fail-stale-running", response_model=BulkOperationResult)
def fail_stale_running_ops(
    request: BulkOperationRequest,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_optional_principal),
):
    _write_roles(principal)
    result = _service(db).fail_stale_running(reason=request.reason, actor_user_id=principal.user_id)
    db.commit()
    return result


@router.post("/jobs/cleanup-legacy-pending", response_model=BulkOperationResult)
def cleanup_legacy_pending_ops(
    request: LegacyCleanupRequest,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_optional_principal),
):
    _write_roles(principal)
    result = _service(db).cleanup_legacy_pending(
        reason=request.reason,
        agent_id=request.agent_id,
        created_before_hours=request.created_before_hours,
        dry_run=request.dry_run,
    )
    if not request.dry_run:
        db.commit()
    else:
        db.rollback()
    return result
