from fastapi.testclient import TestClient

from intelligence_engine.db.session import get_db
from intelligence_engine.domain.enums import ErrorCode, JobStatus, JobType
from intelligence_engine.main import create_app
from intelligence_engine.storage.repositories.job_repository import JobRepository


def _client(db_session):
    app = create_app()

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)


def test_job_start_rejects_stale_agent_callback(db_session):
    repo = JobRepository(db_session)
    job = repo.create_job(job_type=JobType.FEED_COLLECT, payload={})
    job.status = JobStatus.CLAIMED.value
    job.claimed_by_agent_id = "agent-owner"
    db_session.commit()

    response = _client(db_session).post(f"/api/jobs/{job.id}/start", json={"agent_id": "agent-stale"})

    assert response.status_code == 409
    db_session.refresh(job)
    assert job.status == JobStatus.CLAIMED.value
    assert job.claimed_by_agent_id == "agent-owner"


def test_job_progress_complete_and_fail_reject_stale_agent_callback(db_session):
    repo = JobRepository(db_session)
    client = _client(db_session)

    progress_job = repo.create_job(job_type=JobType.FEED_COLLECT, payload={})
    progress_job.status = JobStatus.RUNNING.value
    progress_job.claimed_by_agent_id = "agent-owner"
    complete_job = repo.create_job(job_type=JobType.DETAIL_FETCH, payload={})
    complete_job.status = JobStatus.RUNNING.value
    complete_job.claimed_by_agent_id = "agent-owner"
    fail_job = repo.create_job(job_type=JobType.COMMENT_FETCH, payload={})
    fail_job.status = JobStatus.RUNNING.value
    fail_job.claimed_by_agent_id = "agent-owner"
    db_session.commit()

    progress = client.post(
        f"/api/jobs/{progress_job.id}/progress",
        json={"agent_id": "agent-stale", "checkpoint": {"cursor": "1"}, "partial_metrics": {}},
    )
    complete = client.post(
        f"/api/jobs/{complete_job.id}/complete",
        json={"agent_id": "agent-stale", "status": "success", "result_summary": {"ok": True}},
    )
    fail = client.post(
        f"/api/jobs/{fail_job.id}/fail",
        json={
            "agent_id": "agent-stale",
            "error": {"code": ErrorCode.INTERNAL_ENGINE_ERROR.value, "message": "late callback"},
            "checkpoint": {"cursor": "late"},
        },
    )

    assert progress.status_code == 409
    assert complete.status_code == 409
    assert fail.status_code == 409
    db_session.refresh(progress_job)
    db_session.refresh(complete_job)
    db_session.refresh(fail_job)
    assert progress_job.checkpoint_json == {}
    assert complete_job.status == JobStatus.RUNNING.value
    assert fail_job.status == JobStatus.RUNNING.value
