from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from intelligence_engine.config import get_settings
from intelligence_engine.db.models import Employee, Job, JobEvent, LocalAgent, PlatformAccount, TaskRun, TaskTemplate, User
from intelligence_engine.domain.enums import JobStatus, JobType
from intelligence_engine.domain.job_priority import is_legacy_test_job_payload
from intelligence_engine.domain.operations_status_groups import (
    JOB_FINISHED_STATUSES,
    JOB_WAITING_STATUSES,
    TASK_RUN_ACTIVE_STATUSES,
    TASK_RUN_NEEDS_ACTION_STATUSES,
    TASK_RUN_DONE_STATUSES,
    build_stuck_task_run_ids,
    build_task_run_bucket_counts,
    is_job_stale_claimed,
    is_job_stale_running,
)
from intelligence_engine.domain.operations_schemas import (
    BulkOperationResult,
    JobDetailOps,
    JobListItem,
    JobListResponse,
    JobQueueSummary,
    TaskRunDetailOps,
    TaskRunListItem,
    TaskRunListOpsResponse,
)
from intelligence_engine.services.job_queue_diagnostics import build_task_run_queue_context, collect_job_queue_report
from intelligence_engine.services.task_materialization import TaskMaterializationService
from intelligence_engine.storage.repositories.job_repository import JobRepository


class JobOperationsService:
    def __init__(self, db: Session):
        self.db = db
        self.job_repo = JobRepository(db)

    def queue_summary(self) -> JobQueueSummary:
        TaskMaterializationService(self.db).refresh_active_task_runs()
        report = collect_job_queue_report(self.db)
        task_run_status_counts = Counter(run.status for run in self.db.scalars(select(TaskRun)))
        orphan_active_job_count = self.db.scalar(
            select(func.count(Job.id)).where(
                Job.task_run_id.is_(None),
                Job.status.in_(
                    [
                        JobStatus.PENDING.value,
                        JobStatus.CLAIMED.value,
                        JobStatus.RUNNING.value,
                    ]
                ),
            )
        ) or 0
        by_agent_rows = list(
            self.db.execute(
                select(
                    Job.claimed_by_agent_id,
                    Job.status,
                    func.count(Job.id),
                )
                .where(Job.status.in_([JobStatus.PENDING.value, JobStatus.CLAIMED.value, JobStatus.RUNNING.value]))
                .where(Job.claimed_by_agent_id.is_not(None))
                .group_by(Job.claimed_by_agent_id, Job.status)
            )
        )
        agent_map: dict[str, dict[str, int]] = {}
        for agent_id, status, count in by_agent_rows:
            agent_map.setdefault(agent_id, {})[status] = count
        by_agent = []
        for agent_id, statuses in agent_map.items():
            agent = self.db.get(LocalAgent, agent_id)
            by_agent.append({"agent_id": agent_id, "device_name": agent.device_name if agent else None, "status_counts": statuses})
        job_status_counts = dict(report["status_counts"])
        settings = get_settings()
        stuck_run_ids = build_stuck_task_run_ids(self.db, settings)
        all_runs = list(self.db.scalars(select(TaskRun)))
        bucket_counts = build_task_run_bucket_counts(all_runs, stuck_run_ids)
        return JobQueueSummary(
            generated_at=datetime.fromisoformat(report["generated_at"]),
            status_counts=job_status_counts,
            job_status_counts=job_status_counts,
            task_run_status_counts=dict(task_run_status_counts),
            orphan_active_job_count=orphan_active_job_count,
            job_type_status_counts=report["job_type_status_counts"],
            stale_running_count=len(report["stale_running_jobs"]),
            stale_claimed_count=len(report["stale_claimed_jobs"]),
            legacy_pending_count=report["legacy_pending_estimate"],
            task_run_bucket_counts=bucket_counts,
            stuck_task_run_count=len(stuck_run_ids),
            by_agent=by_agent,
        )

    def _apply_task_run_employee_scope(
        self,
        stmt,
        *,
        owner_employee_id: str | None,
        executor_account_id: str | None,
    ):
        if owner_employee_id:
            stmt = (
                stmt.join(PlatformAccount, TaskRun.executor_account_id == PlatformAccount.id)
                .where(PlatformAccount.employee_id == owner_employee_id)
            )
        if executor_account_id:
            stmt = stmt.where(TaskRun.executor_account_id == executor_account_id)
        return stmt

    def list_task_runs(
        self,
        *,
        template_id: str | None = None,
        trigger_type: str | None = None,
        status: str | None = None,
        status_group: str | None = None,
        stuck_only: bool | None = None,
        has_active_jobs: bool | None = None,
        owner_employee_id: str | None = None,
        executor_account_id: str | None = None,
        created_after: datetime | None = None,
        created_before: datetime | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> TaskRunListOpsResponse:
        TaskMaterializationService(self.db).refresh_active_task_runs()
        settings = get_settings()
        stuck_run_ids = build_stuck_task_run_ids(self.db, settings)
        stmt = select(TaskRun)
        stmt = self._apply_task_run_employee_scope(
            stmt,
            owner_employee_id=owner_employee_id,
            executor_account_id=executor_account_id,
        )
        if template_id:
            stmt = stmt.where(TaskRun.task_template_id == template_id)
        if trigger_type:
            stmt = stmt.where(TaskRun.trigger_type == trigger_type)
        if status_group:
            if status_group == "active":
                stmt = stmt.where(TaskRun.status.in_(TASK_RUN_ACTIVE_STATUSES))
                if stuck_run_ids:
                    stmt = stmt.where(TaskRun.id.not_in(stuck_run_ids))
            elif status_group == "needs_action":
                conditions = [TaskRun.status.in_(TASK_RUN_NEEDS_ACTION_STATUSES)]
                if stuck_run_ids:
                    conditions.append(TaskRun.id.in_(stuck_run_ids))
                stmt = stmt.where(or_(*conditions))
            elif status_group == "done":
                stmt = stmt.where(TaskRun.status.in_(TASK_RUN_DONE_STATUSES))
        elif status:
            stmt = stmt.where(TaskRun.status == status)
        if stuck_only is True:
            if stuck_run_ids:
                stmt = stmt.where(TaskRun.id.in_(stuck_run_ids))
            else:
                stmt = stmt.where(TaskRun.id.in_([]))
        if created_after:
            stmt = stmt.where(TaskRun.created_at >= created_after)
        if created_before:
            stmt = stmt.where(TaskRun.created_at <= created_before)
        total = self.db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        runs = list(
            self.db.scalars(
                stmt.order_by(TaskRun.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
            )
        )
        items = [self._task_run_item(run, stuck_run_ids=stuck_run_ids) for run in runs]
        if has_active_jobs is not None:
            items = [item for item in items if item.has_active_jobs == has_active_jobs]
        return TaskRunListOpsResponse(items=items, total=total, page=page, page_size=page_size)

    def get_task_run_detail(self, task_run_id: str) -> TaskRunDetailOps:
        run = self.db.get(TaskRun, task_run_id)
        if not run:
            raise KeyError(task_run_id)
        TaskMaterializationService(self.db).refresh_task_run(run)
        item = self._task_run_item(run, stuck_run_ids=build_stuck_task_run_ids(self.db, get_settings()))
        jobs = list(self.db.scalars(select(Job).where(Job.task_run_id == run.id).order_by(Job.created_at.asc())))
        queue = build_task_run_queue_context(self.db, run)
        return TaskRunDetailOps(**item.model_dump(), jobs=[self._job_item(job) for job in jobs], queue_context=queue)

    def list_jobs(
        self,
        *,
        job_type: str | None = None,
        status: str | None = None,
        status_group: str | None = None,
        agent_id: str | None = None,
        task_run_id: str | None = None,
        priority_max: int | None = None,
        legacy_only: bool | None = None,
        stale_running_only: bool | None = None,
        owner_employee_id: str | None = None,
        created_after: datetime | None = None,
        created_before: datetime | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> JobListResponse:
        stmt = select(Job)
        if owner_employee_id:
            stmt = (
                stmt.join(TaskRun, Job.task_run_id == TaskRun.id)
                .join(PlatformAccount, TaskRun.executor_account_id == PlatformAccount.id)
                .where(Job.task_run_id.is_not(None), PlatformAccount.employee_id == owner_employee_id)
            )
        if job_type:
            stmt = stmt.where(Job.job_type == job_type)
        if status_group == "waiting":
            stmt = stmt.where(Job.status.in_(JOB_WAITING_STATUSES))
        elif status_group == "running":
            stmt = stmt.where(Job.status == JobStatus.RUNNING.value)
        elif status_group == "finished":
            stmt = stmt.where(Job.status.in_(JOB_FINISHED_STATUSES))
        elif status:
            stmt = stmt.where(Job.status == status)
        if agent_id:
            stmt = stmt.where((Job.claimed_by_agent_id == agent_id) | (Job.local_agent_id == agent_id))
        if task_run_id:
            stmt = stmt.where(Job.task_run_id == task_run_id)
        if priority_max is not None:
            stmt = stmt.where(Job.priority <= priority_max)
        if created_after:
            stmt = stmt.where(Job.created_at >= created_after)
        if created_before:
            stmt = stmt.where(Job.created_at <= created_before)
        jobs = list(self.db.scalars(stmt.order_by(Job.created_at.desc())))
        items = [self._job_item(job) for job in jobs]
        if legacy_only is True:
            items = [item for item in items if item.is_legacy]
        if stale_running_only is True:
            items = [item for item in items if item.is_stale_running or item.is_stale_claimed]
        total = len(items)
        start = (page - 1) * page_size
        page_items = items[start : start + page_size]
        return JobListResponse(items=page_items, total=total, page=page, page_size=page_size)

    def get_job_detail(self, job_id: str) -> JobDetailOps:
        job = self.db.get(Job, job_id)
        if not job:
            raise KeyError(job_id)
        events = list(
            self.db.scalars(select(JobEvent).where(JobEvent.job_id == job.id).order_by(JobEvent.created_at.asc()))
        )
        return JobDetailOps(
            **self._job_item(job).model_dump(),
            events=[
                {"event_type": event.event_type, "payload": event.event_payload_json, "created_at": event.created_at.isoformat()}
                for event in events
            ],
        )

    def cancel_job(self, job_id: str, *, reason: str, actor_user_id: str | None = None) -> BulkOperationResult:
        job = self.db.get(Job, job_id)
        if not job:
            raise KeyError(job_id)
        self.job_repo.cancel_job(job, reason=reason)
        self._audit(job.id, "job_cancelled", {"reason": reason, "actor_user_id": actor_user_id})
        self.db.flush()
        return BulkOperationResult(affected_count=1, job_ids=[job.id], message="已取消 pending job")

    def cancel_task_run_pending(self, task_run_id: str, *, reason: str, actor_user_id: str | None = None) -> BulkOperationResult:
        job_ids = self.job_repo.cancel_pending_jobs(reason=reason, task_run_id=task_run_id, dry_run=False)
        for job_id in job_ids:
            self._audit(job_id, "job_cancelled", {"reason": reason, "actor_user_id": actor_user_id, "task_run_id": task_run_id})
        return BulkOperationResult(affected_count=len(job_ids), job_ids=job_ids, message=f"已取消 {len(job_ids)} 个 pending job")

    def fail_stale_running(self, *, reason: str, actor_user_id: str | None = None) -> BulkOperationResult:
        settings = get_settings()
        count = self.job_repo.fail_stale_running_jobs(max_running_seconds=settings.job_running_timeout_seconds)
        return BulkOperationResult(affected_count=count, message=f"已将 {count} 个超时 running job 标记为 failed")

    def cleanup_legacy_pending(
        self,
        *,
        reason: str,
        agent_id: str | None = None,
        created_before_hours: float | None = None,
        dry_run: bool = False,
    ) -> BulkOperationResult:
        created_before = None
        if created_before_hours is not None:
            created_before = datetime.now(timezone.utc) - timedelta(hours=created_before_hours)
        job_ids = self.job_repo.cancel_pending_jobs(
            reason=reason,
            agent_id=agent_id,
            created_before=created_before,
            only_legacy=True,
            dry_run=dry_run,
        )
        return BulkOperationResult(
            affected_count=len(job_ids),
            job_ids=job_ids[:100],
            message=f"{'将取消' if dry_run else '已取消'} {len(job_ids)} 个 legacy pending job",
        )

    def retry_job(self, job_id: str, *, reason: str, actor_user_id: str | None = None) -> BulkOperationResult:
        job = self.job_repo.retry_failed_job(job_id, reason=reason)
        self._audit(job.id, "job_retried", {"reason": reason, "actor_user_id": actor_user_id})
        return BulkOperationResult(affected_count=1, job_ids=[job.id], message="failed job 已重新排队")

    def retry_task_run(self, task_run_id: str, *, reason: str, actor_user_id: str | None = None) -> BulkOperationResult:
        job_ids = self.job_repo.retry_failed_jobs_for_task_run(task_run_id, reason=reason)
        for job_id in job_ids:
            self._audit(job_id, "job_retried", {"reason": reason, "actor_user_id": actor_user_id, "task_run_id": task_run_id})
        run = self.db.get(TaskRun, task_run_id)
        if run:
            TaskMaterializationService(self.db).refresh_task_run(run)
        return BulkOperationResult(affected_count=len(job_ids), job_ids=job_ids, message=f"已重试排队 {len(job_ids)} 个 failed job")

    def _task_run_item(self, run: TaskRun, *, stuck_run_ids: set[str] | None = None) -> TaskRunListItem:
        template = self.db.get(TaskTemplate, run.task_template_id)
        requested_by = self.db.get(User, run.requested_by_user_id) if run.requested_by_user_id else None
        executor_account = self.db.get(PlatformAccount, run.executor_account_id) if run.executor_account_id else None
        owner_employee = self.db.get(Employee, executor_account.employee_id) if executor_account and executor_account.employee_id else None
        has_active = run.jobs_pending > 0 or run.jobs_running > 0
        has_stuck = run.id in stuck_run_ids if stuck_run_ids is not None else False
        return TaskRunListItem(
            id=run.id,
            task_template_id=run.task_template_id,
            task_template_name=template.name if template else None,
            trigger_type=run.trigger_type,
            status=run.status,
            requested_by_user_id=run.requested_by_user_id,
            requested_by_display_name=requested_by.display_name if requested_by else None,
            owner_employee_id=owner_employee.id if owner_employee else None,
            owner_employee_name=owner_employee.display_name if owner_employee else None,
            executor_account_id=executor_account.id if executor_account else None,
            executor_account_name=executor_account.display_name if executor_account else None,
            task_schedule_id=run.task_schedule_id,
            jobs_total=run.jobs_total,
            jobs_pending=run.jobs_pending,
            jobs_running=run.jobs_running,
            jobs_success=run.jobs_success,
            jobs_failed=run.jobs_failed,
            result_summary=run.result_summary_json or {},
            error_summary=run.error_summary_json or {},
            created_at=run.created_at,
            updated_at=run.updated_at,
            finished_at=run.finished_at,
            has_active_jobs=has_active,
            has_stuck_jobs=has_stuck,
        )

    def _job_item(self, job: Job) -> JobListItem:
        settings = get_settings()
        stale_running = is_job_stale_running(job, timeout_seconds=settings.job_running_timeout_seconds)
        stale_claimed = is_job_stale_claimed(job)
        template_name = None
        if job.task_run_id:
            run = self.db.get(TaskRun, job.task_run_id)
            if run:
                template = self.db.get(TaskTemplate, run.task_template_id)
                template_name = template.name if template else None
        agent_name = None
        if job.claimed_by_agent_id:
            agent = self.db.get(LocalAgent, job.claimed_by_agent_id)
            agent_name = agent.device_name if agent else job.claimed_by_agent_id
        return JobListItem(
            id=job.id,
            task_run_id=job.task_run_id,
            task_template_name=template_name,
            job_type=job.job_type,
            status=job.status,
            priority=job.priority,
            account_id=job.account_id,
            local_agent_id=job.local_agent_id,
            claimed_by_agent_id=job.claimed_by_agent_id,
            claimed_by_agent_name=agent_name,
            retry_count=job.retry_count,
            last_error_code=job.last_error_code,
            last_error_message=job.last_error_message,
            created_at=job.created_at,
            started_at=job.started_at,
            finished_at=job.finished_at,
            is_legacy=is_legacy_test_job_payload(job.payload_json),
            is_stale_running=stale_running,
            is_stale_claimed=stale_claimed,
            payload_json=job.payload_json or {},
            result_summary_json=job.result_summary_json or {},
        )

    def _audit(self, job_id: str, event_type: str, payload: dict[str, Any]) -> None:
        self.job_repo.add_event(job_id, event_type, payload)
