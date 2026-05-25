from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from intelligence_engine.db.models import Job, TaskRun, TaskTemplate, utcnow
from intelligence_engine.db.session import get_db
from intelligence_engine.domain.enums import JobStatus, JobType, TaskRunTriggerType, TaskTemplateType
from intelligence_engine.main import create_app


def _client(db_session, *, role: str = "supervisor") -> TestClient:
    app = create_app()

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    client.headers.update({"X-Role": role, "X-User-Id": f"{role}-user"})
    return client


def _seed_template_and_run(db_session) -> tuple[TaskTemplate, TaskRun, Job]:
    template = TaskTemplate(
        name="关键词搜索",
        template_type=TaskTemplateType.KEYWORD_SEARCH_TASK.value,
        config_json={"keywords": ["论文"], "max_items": 20, "platform": "xhs"},
        enabled=True,
    )
    db_session.add(template)
    db_session.flush()
    run = TaskRun(
        task_template_id=template.id,
        trigger_type=TaskRunTriggerType.MANUAL.value,
        status="queued",
        jobs_total=1,
        jobs_pending=1,
        jobs_running=0,
        jobs_success=0,
        jobs_failed=0,
    )
    db_session.add(run)
    db_session.flush()
    job = Job(
        job_type=JobType.SEARCH_COLLECT.value,
        status=JobStatus.PENDING.value,
        priority=10,
        task_run_id=run.id,
        payload_json={"keywords": ["论文"], "max_items": 20},
    )
    db_session.add(job)
    db_session.commit()
    return template, run, job


def test_operations_queue_summary_and_list(db_session):
    _seed_template_and_run(db_session)
    client = _client(db_session)
    summary = client.get("/api/operations/queue-summary")
    assert summary.status_code == 200
    body = summary.json()
    assert body["status_counts"]["pending"] >= 1
    runs = client.get("/api/operations/task-runs")
    assert runs.status_code == 200
    assert runs.json()["total"] >= 1
    jobs = client.get("/api/operations/jobs?job_type=search_collect")
    assert jobs.status_code == 200
    assert any(item["job_type"] == "search_collect" for item in jobs.json()["items"])


def test_operations_cancel_and_retry(db_session):
    template, run, job = _seed_template_and_run(db_session)
    client = _client(db_session)
    cancel = client.post(f"/api/operations/jobs/{job.id}/cancel", json={"reason": "test_cancel"})
    assert cancel.status_code == 200
    assert cancel.json()["affected_count"] == 1
    db_session.refresh(job)
    assert job.status == JobStatus.CANCELLED.value

    failed = Job(
        job_type=JobType.DETAIL_FETCH.value,
        status=JobStatus.FAILED.value,
        priority=80,
        task_run_id=run.id,
        payload_json={"content_id": "c1"},
        retry_count=0,
        max_retries=3,
    )
    db_session.add(failed)
    db_session.commit()
    retry = client.post(f"/api/operations/jobs/{failed.id}/retry", json={"reason": "test_retry"})
    assert retry.status_code == 200
    db_session.refresh(failed)
    assert failed.status == JobStatus.PENDING.value


def test_operations_fail_stale_running(db_session):
    stale = Job(
        job_type=JobType.FEED_COLLECT.value,
        status=JobStatus.RUNNING.value,
        priority=30,
        started_at=utcnow() - timedelta(hours=2),
        payload_json={},
    )
    db_session.add(stale)
    db_session.commit()
    client = _client(db_session)
    result = client.post("/api/operations/jobs/fail-stale-running", json={"reason": "test_stale"})
    assert result.status_code == 200
    assert result.json()["affected_count"] >= 1
    db_session.refresh(stale)
    assert stale.status == JobStatus.FAILED.value


def test_operations_task_run_status_synced_with_running_job(db_session):
    template, run, job = _seed_template_and_run(db_session)
    job.status = JobStatus.RUNNING.value
    job.started_at = utcnow()
    run.status = "queued"
    run.jobs_pending = 1
    run.jobs_running = 0
    db_session.commit()

    client = _client(db_session)
    summary = client.get("/api/operations/queue-summary")
    assert summary.status_code == 200
    body = summary.json()
    assert body["job_status_counts"]["running"] >= 1
    assert body["task_run_status_counts"]["running"] >= 1

    runs = client.get("/api/operations/task-runs?status=running")
    assert runs.status_code == 200
    assert runs.json()["total"] >= 1
    assert any(item["id"] == run.id for item in runs.json()["items"])


def test_operations_orphan_running_job_counted_separately(db_session):
    orphan = Job(
        job_type=JobType.FEED_COLLECT.value,
        status=JobStatus.RUNNING.value,
        priority=30,
        task_run_id=None,
        started_at=utcnow(),
        payload_json={},
    )
    db_session.add(orphan)
    db_session.commit()
    client = _client(db_session)
    body = client.get("/api/operations/queue-summary").json()
    assert body["job_status_counts"]["running"] >= 1
    assert body["orphan_active_job_count"] >= 1
    assert client.get("/api/operations/task-runs?status=running").json()["total"] == 0


def test_operations_operator_read_only(db_session):
    _seed_template_and_run(db_session)
    client = _client(db_session, role="operator")
    assert client.get("/api/operations/queue-summary").status_code == 200
    cancel = client.post("/api/operations/jobs/fail-stale-running", json={"reason": "deny"})
    assert cancel.status_code == 403
