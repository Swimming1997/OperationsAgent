from datetime import datetime, timedelta, timezone

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from intelligence_engine.db.models import AccountSession, Job, JobEvent, LocalAgent, PlatformAccount, utcnow
from intelligence_engine.domain.enums import JobStatus, JobType
from intelligence_engine.jobs.state_machine import assert_transition


def enum_value(value):
    return getattr(value, "value", value)


def _coerce_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


class JobRepository:
    def __init__(self, db: Session):
        self.db = db

    def _ensure_claim_owner(self, job: Job, *, agent_id: str | None) -> None:
        """Reject stale agent callbacks once a job has an explicit owner."""
        if not agent_id or not job.claimed_by_agent_id:
            return
        if job.claimed_by_agent_id != agent_id:
            raise ValueError(f"job is claimed by another agent: {job.claimed_by_agent_id}")

    def create_job(
        self,
        *,
        job_type: JobType,
        payload: dict,
        account_id: str | None = None,
        local_agent_id: str | None = None,
        creator_monitor_id: str | None = None,
        task_run_id: str | None = None,
        priority: int = 100,
        checkpoint: dict | None = None,
    ) -> Job:
        job = Job(
            job_type=job_type.value,
            status=JobStatus.PENDING.value,
            priority=priority,
            account_id=account_id,
            local_agent_id=local_agent_id,
            creator_monitor_id=creator_monitor_id,
            task_run_id=task_run_id,
            payload_json=payload,
            checkpoint_json=checkpoint or {},
        )
        self.db.add(job)
        self.db.flush()
        self.add_event(job.id, "job_created", {"job_type": job.job_type})
        return job

    def add_event(self, job_id: str, event_type: str, payload: dict | None = None) -> None:
        self.db.add(JobEvent(job_id=job_id, event_type=event_type, event_payload_json=payload or {}))

    def get(self, job_id: str) -> Job | None:
        return self.db.get(Job, job_id)

    def fail_stale_running_jobs(self, *, max_running_seconds: int) -> int:
        now = utcnow()
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        cutoff = now - timedelta(seconds=max_running_seconds)
        jobs = list(self.db.scalars(select(Job).where(Job.status == JobStatus.RUNNING.value).where(Job.started_at.is_not(None))))
        jobs = [job for job in jobs if _coerce_utc(job.started_at) < cutoff]
        for job in jobs:
            self.mark_failed(
                job,
                error_code="job_execution_timeout",
                error_message=f"job exceeded running timeout ({max_running_seconds}s)",
                checkpoint=job.checkpoint_json,
            )
        self.db.flush()
        return len(jobs)

    def cancel_job(self, job: Job, *, reason: str) -> Job:
        if job.status != JobStatus.PENDING.value:
            raise ValueError(f"only pending jobs can be cancelled: {job.status}")
        assert_transition(job.status, JobStatus.CANCELLED)
        job.status = JobStatus.CANCELLED.value
        job.last_error_code = "cancelled"
        job.last_error_message = reason
        job.finished_at = utcnow()
        job.updated_at = job.finished_at
        self.add_event(job.id, "job_cancelled", {"reason": reason})
        return job

    def retry_failed_job(self, job_id: str, *, reason: str) -> Job:
        job = self.get(job_id)
        if not job:
            raise KeyError(f"job not found: {job_id}")
        if job.status != JobStatus.FAILED.value:
            raise ValueError(f"only failed jobs can be retried: {job.status}")
        if job.retry_count >= job.max_retries:
            raise ValueError("job exceeded max retries")
        assert_transition(job.status, JobStatus.PENDING)
        job.status = JobStatus.PENDING.value
        job.claimed_by_agent_id = None
        job.claimed_at = None
        job.claim_expires_at = None
        job.started_at = None
        job.finished_at = None
        job.last_error_code = None
        job.last_error_message = None
        job.updated_at = utcnow()
        self.add_event(job.id, "job_retried", {"reason": reason})
        return job

    def retry_failed_jobs_for_task_run(self, task_run_id: str, *, reason: str) -> list[str]:
        jobs = list(
            self.db.scalars(
                select(Job).where(Job.task_run_id == task_run_id).where(Job.status == JobStatus.FAILED.value).order_by(Job.created_at.asc())
            )
        )
        retried: list[str] = []
        for job in jobs:
            if job.retry_count >= job.max_retries:
                continue
            self.retry_failed_job(job.id, reason=reason)
            retried.append(job.id)
        self.db.flush()
        return retried

    def cancel_pending_jobs(
        self,
        *,
        reason: str,
        agent_id: str | None = None,
        task_run_id: str | None = None,
        created_before=None,
        only_legacy: bool = False,
        dry_run: bool = False,
    ) -> list[str]:
        stmt = select(Job).where(Job.status == JobStatus.PENDING.value)
        if agent_id:
            stmt = stmt.where((Job.local_agent_id.is_(None)) | (Job.local_agent_id == agent_id))
        if task_run_id:
            stmt = stmt.where(Job.task_run_id == task_run_id)
        if created_before is not None:
            stmt = stmt.where(Job.created_at < created_before)
        jobs = list(self.db.scalars(stmt.order_by(Job.created_at.asc())))
        if only_legacy:
            from intelligence_engine.domain.job_priority import is_legacy_test_job_payload

            jobs = [job for job in jobs if is_legacy_test_job_payload(job.payload_json)]
        if dry_run:
            return [job.id for job in jobs]
        cancelled: list[str] = []
        for job in jobs:
            assert_transition(job.status, JobStatus.CANCELLED)
            job.status = JobStatus.CANCELLED.value
            job.last_error_code = "dev_cancelled"
            job.last_error_message = reason
            job.finished_at = utcnow()
            job.updated_at = job.finished_at
            self.add_event(job.id, "job_cancelled", {"reason": reason})
            cancelled.append(job.id)
        self.db.flush()
        return cancelled

    def fail_active_jobs(
        self,
        *,
        reason: str,
        error_code: str = "dev_cleanup",
        agent_id: str | None = None,
        dry_run: bool = False,
    ) -> list[str]:
        stmt = select(Job).where(Job.status.in_([JobStatus.CLAIMED.value, JobStatus.RUNNING.value]))
        if agent_id:
            stmt = stmt.where(Job.claimed_by_agent_id == agent_id)
        jobs = list(self.db.scalars(stmt))
        if dry_run:
            return [job.id for job in jobs]
        failed: list[str] = []
        for job in jobs:
            self.mark_failed(job, error_code=error_code, error_message=reason, checkpoint=job.checkpoint_json)
            failed.append(job.id)
        self.db.flush()
        return failed

    def _agent_has_active_work(self, agent_id: str) -> bool:
        active = self.db.scalar(
            select(Job.id)
            .where(Job.claimed_by_agent_id == agent_id)
            .where(Job.status.in_([JobStatus.CLAIMED.value, JobStatus.RUNNING.value]))
            .limit(1)
        )
        return bool(active)

    def _agent_can_run_job(self, *, agent_id: str, job: Job) -> bool:
        if job.local_agent_id and job.local_agent_id != agent_id:
            return False
        if self._agent_has_active_work(agent_id):
            return False
        agent = self.db.get(LocalAgent, agent_id)
        if agent and agent.status == "retired":
            return False
        if not job.account_id:
            return True
        if not agent:
            return False
        account = self.db.get(PlatformAccount, job.account_id)
        if not account:
            return False
        if account.employee_id and agent.employee_id != account.employee_id:
            return False
        if job.local_agent_id == agent_id:
            return True
        ready_session = self.db.scalar(
            select(AccountSession.id).where(
                AccountSession.account_id == job.account_id,
                AccountSession.local_agent_id == agent_id,
                AccountSession.status == "ready",
            )
        )
        return bool(ready_session)

    def claim_jobs_for_agent(self, *, agent_id: str, supported_job_types: list[JobType], max_jobs: int, ttl_seconds: int) -> list[Job]:
        self.requeue_expired_claims()
        agent = self.db.get(LocalAgent, agent_id)
        if agent and agent.status == "retired":
            return []
        now = utcnow()
        expires_at = now + timedelta(seconds=ttl_seconds)
        supported = [enum_value(job_type) for job_type in supported_job_types] or [job_type.value for job_type in JobType]
        stmt = (
            select(Job)
            .where(Job.status == JobStatus.PENDING.value)
            .where(Job.job_type.in_(supported))
            .order_by(Job.priority.asc(), Job.created_at.asc())
            .limit(max_jobs * 5)
        )
        candidates = list(self.db.scalars(stmt))
        jobs: list[Job] = []
        for item in candidates:
            if len(jobs) >= max_jobs:
                break
            if self._agent_can_run_job(agent_id=agent_id, job=item):
                jobs.append(item)
        for job in jobs:
            assert_transition(job.status, JobStatus.CLAIMED)
            job.status = JobStatus.CLAIMED.value
            job.local_agent_id = agent_id
            job.claimed_by_agent_id = agent_id
            job.claimed_at = now
            job.claim_expires_at = expires_at
            job.updated_at = now
            self.add_event(job.id, "job_claimed", {"agent_id": agent_id})
        self.db.flush()
        return jobs

    def mark_started(self, job: Job, *, agent_id: str) -> Job:
        self._ensure_claim_owner(job, agent_id=agent_id)
        assert_transition(job.status, JobStatus.RUNNING)
        job.status = JobStatus.RUNNING.value
        job.claimed_by_agent_id = agent_id
        job.started_at = utcnow()
        job.updated_at = job.started_at
        self.add_event(job.id, "job_started", {"agent_id": agent_id})
        return job

    def update_checkpoint(self, job: Job, *, checkpoint: dict, partial_metrics: dict | None = None, agent_id: str | None = None) -> Job:
        self._ensure_claim_owner(job, agent_id=agent_id)
        job.checkpoint_json = checkpoint
        job.updated_at = utcnow()
        self.add_event(job.id, "checkpoint_updated", {"checkpoint": checkpoint, "partial_metrics": partial_metrics or {}, "agent_id": agent_id})
        return job

    def mark_success(self, job: Job, *, status: JobStatus, result_summary: dict, agent_id: str | None = None) -> Job:
        self._ensure_claim_owner(job, agent_id=agent_id)
        target_status = JobStatus(enum_value(status))
        assert_transition(job.status, target_status)
        job.status = target_status.value
        job.result_summary_json = result_summary
        job.finished_at = utcnow()
        job.updated_at = job.finished_at
        self.add_event(job.id, "job_success" if target_status == JobStatus.SUCCESS else "job_partial_success", result_summary)
        return job

    def mark_failed(self, job: Job, *, error_code: str, error_message: str, checkpoint: dict | None = None, agent_id: str | None = None) -> Job:
        self._ensure_claim_owner(job, agent_id=agent_id)
        assert_transition(job.status, JobStatus.FAILED)
        job.status = JobStatus.FAILED.value
        job.last_error_code = error_code
        job.last_error_message = error_message
        job.checkpoint_json = checkpoint or job.checkpoint_json
        job.retry_count += 1
        job.finished_at = utcnow()
        job.updated_at = job.finished_at
        self.add_event(job.id, "job_failed", {"error_code": error_code, "error_message": error_message})
        return job

    def pause(self, job: Job) -> Job:
        assert_transition(job.status, JobStatus.PAUSED)
        job.status = JobStatus.PAUSED.value
        job.updated_at = utcnow()
        self.add_event(job.id, "job_paused")
        return job

    def resume(self, job: Job) -> Job:
        assert_transition(job.status, JobStatus.PENDING)
        job.status = JobStatus.PENDING.value
        job.claimed_by_agent_id = None
        job.claimed_at = None
        job.claim_expires_at = None
        job.updated_at = utcnow()
        self.add_event(job.id, "job_resumed")
        return job

    def requeue_expired_claims(self) -> int:
        now = utcnow()
        self.db.flush()
        jobs = list(
            self.db.scalars(
                select(Job).where(Job.status == JobStatus.CLAIMED.value, Job.claim_expires_at.is_not(None), Job.claim_expires_at < now)
            )
        )
        for job in jobs:
            job.status = JobStatus.PENDING.value
            job.local_agent_id = None
            job.claimed_by_agent_id = None
            job.claimed_at = None
            job.claim_expires_at = None
            job.updated_at = now
            self.add_event(job.id, "job_claim_expired")
        self.db.flush()
        return len(jobs)
