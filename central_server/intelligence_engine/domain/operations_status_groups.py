from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.orm import Session

from intelligence_engine.db.models import Job, utcnow
from intelligence_engine.domain.enums import JobStatus, TaskRunStatus

if TYPE_CHECKING:
    from intelligence_engine.config import Settings

TASK_RUN_BUCKETS = ("active", "needs_action", "done")

TASK_RUN_ACTIVE_STATUSES = {
    TaskRunStatus.MATERIALIZED.value,
    TaskRunStatus.QUEUED.value,
    TaskRunStatus.RUNNING.value,
}

TASK_RUN_NEEDS_ACTION_STATUSES = {
    TaskRunStatus.FAILED.value,
    TaskRunStatus.PARTIAL_SUCCESS.value,
}

TASK_RUN_DONE_STATUSES = {
    TaskRunStatus.SUCCESS.value,
}

JOB_WAITING_STATUSES = {
    JobStatus.PENDING.value,
    JobStatus.CLAIMED.value,
}

JOB_FINISHED_STATUSES = {
    JobStatus.SUCCESS.value,
    JobStatus.FAILED.value,
    JobStatus.CANCELLED.value,
    JobStatus.PARTIAL_SUCCESS.value,
}

DEFAULT_STALE_CLAIMED_SECONDS = 600


def _coerce_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def is_job_stale_running(job: Job, *, timeout_seconds: int) -> bool:
    if job.status != JobStatus.RUNNING.value or job.started_at is None:
        return False
    elapsed = (_coerce_utc(utcnow()) - _coerce_utc(job.started_at)).total_seconds()
    return elapsed > timeout_seconds


def is_job_stale_claimed(job: Job, *, stale_claimed_seconds: int = DEFAULT_STALE_CLAIMED_SECONDS) -> bool:
    if job.status != JobStatus.CLAIMED.value or job.claimed_at is None:
        return False
    elapsed = (_coerce_utc(utcnow()) - _coerce_utc(job.claimed_at)).total_seconds()
    return elapsed > stale_claimed_seconds


def is_job_stuck(job: Job, settings: Settings, *, stale_claimed_seconds: int = DEFAULT_STALE_CLAIMED_SECONDS) -> bool:
    return is_job_stale_running(job, timeout_seconds=settings.job_running_timeout_seconds) or is_job_stale_claimed(
        job,
        stale_claimed_seconds=stale_claimed_seconds,
    )


def classify_task_run_bucket(run_status: str, has_stuck_jobs: bool) -> str:
    if has_stuck_jobs or run_status in TASK_RUN_NEEDS_ACTION_STATUSES:
        return "needs_action"
    if run_status in TASK_RUN_ACTIVE_STATUSES:
        return "active"
    if run_status in TASK_RUN_DONE_STATUSES:
        return "done"
    return "done"


def build_stuck_task_run_ids(
    db: Session,
    settings: Settings,
    *,
    stale_claimed_seconds: int = DEFAULT_STALE_CLAIMED_SECONDS,
) -> set[str]:
    now = _coerce_utc(utcnow())
    running_cutoff = now - timedelta(seconds=settings.job_running_timeout_seconds)
    claimed_cutoff = now - timedelta(seconds=stale_claimed_seconds)

    stale_running_ids = db.scalars(
        select(Job.task_run_id)
        .where(
            Job.task_run_id.is_not(None),
            Job.status == JobStatus.RUNNING.value,
            Job.started_at.is_not(None),
            Job.started_at < running_cutoff,
        )
        .distinct()
    )
    stale_claimed_ids = db.scalars(
        select(Job.task_run_id)
        .where(
            Job.task_run_id.is_not(None),
            Job.status == JobStatus.CLAIMED.value,
            Job.claimed_at.is_not(None),
            Job.claimed_at < claimed_cutoff,
        )
        .distinct()
    )
    return {run_id for run_id in (*stale_running_ids, *stale_claimed_ids) if run_id}


def build_task_run_bucket_counts(runs: list, stuck_run_ids: set[str]) -> dict[str, int]:
    counts = {bucket: 0 for bucket in TASK_RUN_BUCKETS}
    for run in runs:
        bucket = classify_task_run_bucket(run.status, run.id in stuck_run_ids)
        counts[bucket] += 1
    return counts
