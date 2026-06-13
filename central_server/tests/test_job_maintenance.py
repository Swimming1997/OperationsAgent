from datetime import timedelta

from intelligence_engine.db.models import AccountLoginSession, Job, PlatformAccount, utcnow
from intelligence_engine.domain.enums import AuthStatus, JobStatus, JobType, LoginSessionStatus, Platform
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

