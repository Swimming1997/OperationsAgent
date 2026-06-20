from datetime import timedelta

from intelligence_engine.db.models import AccountLoginSession, Job, PlatformAccount, TaskRun, utcnow
from intelligence_engine.domain.enums import AuthStatus, JobStatus, JobType, LoginSessionStatus, Platform, TaskRunStatus, TaskRunTriggerType
from intelligence_engine.jobs.maintenance import JobMaintenanceService


def test_job_maintenance_requeues_claims_and_expires_login_sessions(db_session):
    claimed = Job(
        job_type=JobType.FEED_COLLECT.value,
        status=JobStatus.CLAIMED.value,
        payload_json={},
        checkpoint_json={},
        result_summary_json={},
        claimed_by_agent_id="agent-old",
        claimed_at=utcnow() - timedelta(minutes=20),
        claim_expires_at=utcnow() - timedelta(seconds=1),
    )
    account = PlatformAccount(
        platform=Platform.XHS.value,
        display_name="login-account",
        auth_status=AuthStatus.LOGIN_PENDING.value,
        metadata_json={},
    )
    db_session.add_all([claimed, account])
    db_session.flush()
    session = AccountLoginSession(
        platform_account_id=account.id,
        status=LoginSessionStatus.WAITING_USER_LOGIN.value,
        profile_key="profile-1",
        expires_at=utcnow() - timedelta(seconds=1),
    )
    db_session.add(session)
    db_session.commit()

    result = JobMaintenanceService(db_session).run_once()

    assert result.expired_claim_count == 1
    assert result.expired_login_session_count == 1
    assert claimed.status == JobStatus.PENDING.value
    assert claimed.claimed_by_agent_id is None
    assert session.status == LoginSessionStatus.EXPIRED.value
    assert account.auth_status == AuthStatus.ERROR.value
    assert result.task_run_refreshed_count == 0


def test_job_maintenance_refreshes_task_run_after_stale_running_job(db_session, monkeypatch):
    monkeypatch.setenv("INTEL_ENGINE_JOB_RUNNING_TIMEOUT_SECONDS", "60")
    run = TaskRun(
        trigger_type=TaskRunTriggerType.MANUAL.value,
        status=TaskRunStatus.RUNNING.value,
        result_summary_json={},
        error_summary_json={},
    )
    db_session.add(run)
    db_session.flush()
    job = Job(
        task_run_id=run.id,
        job_type=JobType.FEED_COLLECT.value,
        status=JobStatus.RUNNING.value,
        payload_json={},
        checkpoint_json={},
        result_summary_json={},
        started_at=utcnow() - timedelta(minutes=10),
    )
    db_session.add(job)
    db_session.commit()

    result = JobMaintenanceService(db_session).run_once()

    assert result.stale_running_failed_count == 1
    assert result.task_run_refreshed_count == 1
    assert result.stale_running_requeued_count == 1
    assert job.status == JobStatus.PENDING.value
    assert job.last_error_code is None
    assert job.retry_count == 1
    assert run.status in {TaskRunStatus.QUEUED.value, TaskRunStatus.RUNNING.value}
    assert run.jobs_total == 1
    assert run.jobs_failed == 0
    assert run.finished_at is None


def test_job_maintenance_leaves_stale_job_failed_when_retry_budget_exhausted(db_session, monkeypatch):
    monkeypatch.setenv("INTEL_ENGINE_JOB_RUNNING_TIMEOUT_SECONDS", "60")
    job = Job(
        job_type=JobType.FEED_COLLECT.value,
        status=JobStatus.RUNNING.value,
        payload_json={},
        checkpoint_json={},
        result_summary_json={},
        started_at=utcnow() - timedelta(minutes=10),
        retry_count=3,
        max_retries=3,
    )
    db_session.add(job)
    db_session.commit()

    result = JobMaintenanceService(db_session).run_once()

    assert result.stale_running_failed_count == 1
    assert result.stale_running_requeued_count == 0
    assert job.status == JobStatus.FAILED.value
    assert job.last_error_code == "job_execution_timeout"
