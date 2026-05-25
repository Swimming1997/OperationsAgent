from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from intelligence_engine.db.models import Job, LocalAgent, TaskRun, utcnow
from intelligence_engine.domain.enums import JobStatus
from intelligence_engine.domain.job_priority import is_legacy_test_job_payload


ACTIVE_STATUSES = {
    JobStatus.PENDING.value,
    JobStatus.CLAIMED.value,
    JobStatus.RUNNING.value,
}


def collect_job_queue_report(
    db: Session,
    *,
    agent_id: str | None = None,
    stale_running_seconds: int = 1800,
    stale_claimed_seconds: int = 600,
) -> dict[str, Any]:
    now = _coerce_utc(utcnow())
    jobs = list(db.scalars(select(Job)))
    status_counts = Counter(job.status for job in jobs)
    type_status_counts: dict[str, dict[str, int]] = defaultdict(lambda: Counter())
    task_run_status_counts: dict[str, dict[str, int]] = defaultdict(lambda: Counter())
    legacy_pending = 0
    stale_running: list[dict[str, Any]] = []
    stale_claimed: list[dict[str, Any]] = []

    for job in jobs:
        type_status_counts[job.job_type][job.status] += 1
        bucket = job.task_run_id or "(no_task_run)"
        task_run_status_counts[bucket][job.status] += 1
        if job.status == JobStatus.PENDING.value and (job.task_run_id is None or is_legacy_test_job_payload(job.payload_json)):
            legacy_pending += 1
        if job.status == JobStatus.RUNNING.value and job.started_at and (now - _coerce_utc(job.started_at)) > timedelta(seconds=stale_running_seconds):
            stale_running.append(_job_brief(job, extra={"stale_for_seconds": int((now - _coerce_utc(job.started_at)).total_seconds())}))
        if job.status == JobStatus.CLAIMED.value and job.claimed_at and (now - _coerce_utc(job.claimed_at)) > timedelta(seconds=stale_claimed_seconds):
            stale_claimed.append(_job_brief(job, extra={"stale_for_seconds": int((now - _coerce_utc(job.claimed_at)).total_seconds())}))

    agent_section: dict[str, Any] | None = None
    if agent_id:
        agent = db.get(LocalAgent, agent_id)
        pending_for_agent = list(
            db.scalars(
                select(Job)
                .where(Job.status == JobStatus.PENDING.value)
                .where((Job.local_agent_id.is_(None)) | (Job.local_agent_id == agent_id))
                .order_by(Job.priority.asc(), Job.created_at.asc())
            )
        )
        active_for_agent = list(
            db.scalars(
                select(Job)
                .where(Job.status.in_([JobStatus.CLAIMED.value, JobStatus.RUNNING.value]))
                .where(Job.claimed_by_agent_id == agent_id)
                .order_by(Job.started_at.asc().nullslast(), Job.claimed_at.asc().nullslast())
            )
        )
        agent_section = {
            "agent_id": agent_id,
            "device_name": agent.device_name if agent else None,
            "status": agent.status if agent else None,
            "pending_queue_length": len(pending_for_agent),
            "next_pending_jobs": [_job_brief(job) for job in pending_for_agent[:10]],
            "active_jobs": [_job_brief(job) for job in active_for_agent],
        }

    return {
        "generated_at": now.isoformat(),
        "status_counts": dict(status_counts),
        "job_type_status_counts": {job_type: dict(counter) for job_type, counter in type_status_counts.items()},
        "task_run_status_counts": {task_run_id: dict(counter) for task_run_id, counter in task_run_status_counts.items()},
        "legacy_pending_estimate": legacy_pending,
        "stale_running_jobs": stale_running,
        "stale_claimed_jobs": stale_claimed,
        "agent": agent_section,
    }


def build_task_run_queue_context(db: Session, run: TaskRun) -> dict[str, Any]:
    now = _coerce_utc(utcnow())
    run_jobs = list(db.scalars(select(Job).where(Job.task_run_id == run.id).order_by(Job.created_at.asc())))
    if not run_jobs:
        return {"waiting_reason": "no_jobs", "message": "本次运行未生成 Job", "pending_jobs_ahead": 0}

    pending_jobs = [job for job in run_jobs if job.status in {JobStatus.PENDING.value, JobStatus.CLAIMED.value}]
    running_jobs = [job for job in run_jobs if job.status == JobStatus.RUNNING.value]
    if running_jobs:
        current = running_jobs[0]
        return {
            "waiting_reason": "executing",
            "message": f"当前运行中的 Job：{current.job_type}",
            "pending_jobs_ahead": 0,
            "job_priority": current.priority,
            "agent_running_job_id": current.id,
            "agent_running_job_type": current.job_type,
            "agent_running_since": current.started_at.isoformat() if current.started_at else None,
        }

    if not pending_jobs:
        return {"waiting_reason": "finished", "message": "本次运行 Job 已结束调度", "pending_jobs_ahead": 0}

    target_job = pending_jobs[0]
    priority_hint = target_job.priority
    account_agent_id = target_job.local_agent_id
    if not account_agent_id and target_job.account_id:
        from intelligence_engine.db.models import PlatformAccount

        account = db.get(PlatformAccount, target_job.account_id)
        account_agent_id = account.default_agent_id if account else None

    ahead = 0
    agent_running_job: Job | None = None
    if account_agent_id:
        agent_running_job = db.scalar(
            select(Job)
            .where(Job.claimed_by_agent_id == account_agent_id)
            .where(Job.status == JobStatus.RUNNING.value)
            .order_by(Job.started_at.asc().nullslast())
        )
        ahead = db.scalar(
            select(func.count())
            .select_from(Job)
            .where(Job.status == JobStatus.PENDING.value)
            .where((Job.local_agent_id.is_(None)) | (Job.local_agent_id == account_agent_id))
            .where(
                (Job.priority < target_job.priority)
                | ((Job.priority == target_job.priority) & (Job.created_at < target_job.created_at))
            )
        ) or 0

    if agent_running_job and agent_running_job.id != target_job.id:
        return {
            "waiting_reason": "agent_busy",
            "message": "当前 Agent 正在执行其他任务，本次运行等待调度",
            "pending_jobs_ahead": int(ahead),
            "job_priority": priority_hint,
            "agent_running_job_id": agent_running_job.id,
            "agent_running_job_type": agent_running_job.job_type,
            "agent_running_since": agent_running_job.started_at.isoformat() if agent_running_job.started_at else None,
        }
    if ahead > 0:
        return {
            "waiting_reason": "queue_backlog",
            "message": f"队列前方还有 {ahead} 个待执行 Job，本次运行等待调度",
            "pending_jobs_ahead": int(ahead),
            "job_priority": priority_hint,
            "agent_running_job_id": agent_running_job.id if agent_running_job else None,
            "agent_running_job_type": agent_running_job.job_type if agent_running_job else None,
            "agent_running_since": agent_running_job.started_at.isoformat() if agent_running_job and agent_running_job.started_at else None,
        }
    return {
        "waiting_reason": "ready",
        "message": "等待 Agent 领取本次 Job",
        "pending_jobs_ahead": 0,
        "job_priority": priority_hint,
        "agent_running_job_id": None,
        "agent_running_job_type": None,
        "agent_running_since": None,
    }


def _coerce_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _job_brief(job: Job, *, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = job.payload_json or {}
    item = {
        "job_id": job.id,
        "job_type": job.job_type,
        "status": job.status,
        "priority": job.priority,
        "task_run_id": job.task_run_id,
        "account_id": job.account_id,
        "claimed_by_agent_id": job.claimed_by_agent_id,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "legacy_candidate": job.task_run_id is None or is_legacy_test_job_payload(payload),
    }
    if extra:
        item.update(extra)
    return item
