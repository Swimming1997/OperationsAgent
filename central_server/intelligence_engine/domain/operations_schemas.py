from __future__ import annotations

from datetime import datetime
from typing import Any

from intelligence_engine.domain.schemas import ApiModel


class JobQueueSummary(ApiModel):
    generated_at: datetime
    status_counts: dict[str, int]
    job_status_counts: dict[str, int]
    task_run_status_counts: dict[str, int]
    orphan_active_job_count: int = 0
    job_type_status_counts: dict[str, dict[str, int]]
    stale_running_count: int
    stale_claimed_count: int
    legacy_pending_count: int
    task_run_bucket_counts: dict[str, int] = {}
    stuck_task_run_count: int = 0
    by_agent: list[dict[str, Any]] = []


class JobListItem(ApiModel):
    id: str
    task_run_id: str | None
    task_template_name: str | None = None
    job_type: str
    status: str
    priority: int
    account_id: str | None = None
    local_agent_id: str | None = None
    claimed_by_agent_id: str | None = None
    claimed_by_agent_name: str | None = None
    retry_count: int
    last_error_code: str | None = None
    last_error_message: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    is_legacy: bool = False
    is_stale_running: bool = False
    is_stale_claimed: bool = False
    payload_json: dict[str, Any] = {}
    result_summary_json: dict[str, Any] = {}


class JobListResponse(ApiModel):
    items: list[JobListItem]
    total: int
    page: int
    page_size: int


class TaskRunListItem(ApiModel):
    id: str
    task_template_id: str | None = None
    task_template_name: str | None = None
    trigger_type: str
    status: str
    requested_by_user_id: str | None = None
    requested_by_display_name: str | None = None
    owner_employee_id: str | None = None
    owner_employee_name: str | None = None
    executor_account_id: str | None = None
    executor_account_name: str | None = None
    task_schedule_id: str | None = None
    jobs_total: int
    jobs_pending: int
    jobs_running: int
    jobs_success: int
    jobs_failed: int
    result_summary: dict[str, Any] = {}
    error_summary: dict[str, Any] = {}
    created_at: datetime
    updated_at: datetime
    finished_at: datetime | None = None
    has_active_jobs: bool = False
    has_stuck_jobs: bool = False


class TaskRunListOpsResponse(ApiModel):
    items: list[TaskRunListItem]
    total: int
    page: int
    page_size: int


class TaskRunDetailOps(TaskRunListItem):
    jobs: list[JobListItem] = []
    queue_context: dict[str, Any] | None = None


class JobDetailOps(JobListItem):
    events: list[dict[str, Any]] = []


class BulkOperationResult(ApiModel):
    affected_count: int
    job_ids: list[str] = []
    message: str


class BulkOperationRequest(ApiModel):
    reason: str = "operator_action"
    dry_run: bool = False


class LegacyCleanupRequest(BulkOperationRequest):
    agent_id: str | None = None
    created_before_hours: float | None = None
