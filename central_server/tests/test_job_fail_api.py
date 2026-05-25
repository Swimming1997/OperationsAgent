from fastapi.testclient import TestClient

from intelligence_engine.db.session import get_db
from intelligence_engine.domain.enums import ErrorCode, JobStatus, JobType
from intelligence_engine.domain.schemas import ErrorPayload, JobFailRequest
from intelligence_engine.main import create_app
from intelligence_engine.storage.repositories.job_repository import JobRepository


def test_job_fail_api_accepts_runner_dto_payload(db_session):
    app = create_app()

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    repo = JobRepository(db_session)
    job = repo.create_job(job_type=JobType.COMMENT_FETCH, payload={})
    job.status = JobStatus.RUNNING.value
    db_session.commit()

    request = JobFailRequest(
        agent_id="xhs-main-chain-smoke-runner",
        error=ErrorPayload(
            code=ErrorCode.MISSING_XSEC_CONTEXT,
            message="missing xsec context",
            retryable=False,
            raw_context={"platform_context": {}},
        ),
        checkpoint={"cursor": "0"},
    )
    response = TestClient(app).post(f"/api/jobs/{job.id}/fail", json=request.model_dump(mode="json"))

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "failed"
    assert body["last_error_code"] == "missing_xsec_context"
    assert body["checkpoint"] == {"cursor": "0"}


def test_job_fail_api_accepts_current_smoke_runner_failure_payload(db_session):
    app = create_app()

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    repo = JobRepository(db_session)
    job = repo.create_job(job_type=JobType.COMMENT_FETCH, payload={"content_id": "content-1"})
    job.status = JobStatus.RUNNING.value
    job.checkpoint_json = {}
    db_session.commit()

    payload = {
        "agent_id": "xhs-main-chain-smoke-runner",
        "error": {
            "code": "missing_xsec_context",
            "message": "xhs comment fetch requires xsec_token and xsec_source from the full note URL/context",
            "retryable": False,
            "raw_context": {
                "url": "https://www.xiaohongshu.com/explore/69f5b80a000000003701d4a1",
                "platform_content_id": "69f5b80a000000003701d4a1",
                "platform_context": {
                    "note_id": "69f5b80a000000003701d4a1",
                    "xsec_token": "",
                    "xsec_source": "",
                    "has_xsec_context": False,
                },
            },
        },
        "checkpoint": {},
    }
    response = TestClient(app).post(f"/api/jobs/{job.id}/fail", json=payload)

    assert response.status_code == 200, response.text
    assert response.json()["last_error_code"] == "missing_xsec_context"
