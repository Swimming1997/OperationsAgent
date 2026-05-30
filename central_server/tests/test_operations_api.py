from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from intelligence_engine.db.models import Employee, Job, PlatformAccount, TaskRun, TaskTemplate, User, utcnow
from intelligence_engine.db.session import get_db
from intelligence_engine.domain.enums import (
    AccountRole,
    AccountStatus,
    AuthStatus,
    JobStatus,
    JobType,
    Platform,
    TaskRunTriggerType,
    TaskTemplateType,
)
from intelligence_engine.main import create_app
from intelligence_engine.storage.repositories.product_repository import ProductRepository


def _client(db_session, *, role: str = "supervisor", user_id: str | None = None) -> TestClient:
    app = create_app()

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    client.headers.update({"X-Role": role, "X-User-Id": user_id or f"{role}-user"})
    return client


def _seed_account(db_session, *, employee_id: str, display_name: str) -> PlatformAccount:
    account = PlatformAccount(
        employee_id=employee_id,
        platform=Platform.XHS.value,
        display_name=display_name,
        status=AccountStatus.ACTIVE.value,
        auth_status=AuthStatus.ACTIVE.value,
        account_role=AccountRole.INTELLIGENCE_COLLECTOR.value,
    )
    db_session.add(account)
    db_session.flush()
    return account


def _seed_scoped_operator_runs(db_session) -> tuple[Employee, Employee, TaskRun, TaskRun]:
    product = ProductRepository(db_session)
    employee_a = product.create_employee(user_id="op-a-user", display_name="运营甲", email=None, status="active")
    employee_b = product.create_employee(user_id="op-b-user", display_name="运营乙", email=None, status="active")
    account_a = _seed_account(db_session, employee_id=employee_a.id, display_name="甲账号")
    account_b = _seed_account(db_session, employee_id=employee_b.id, display_name="乙账号")
    template = TaskTemplate(
        name="推荐流",
        template_type=TaskTemplateType.RECOMMENDATION_FEED_TASK.value,
        config_json={"feed_type": "xhs_home_feed", "target_count": 10},
        enabled=True,
    )
    db_session.add(template)
    db_session.flush()

    def _run_for(account: PlatformAccount, *, status: str) -> TaskRun:
        run = TaskRun(
            task_template_id=template.id,
            trigger_type=TaskRunTriggerType.MANUAL.value,
            status=status,
            executor_account_id=account.id,
            jobs_total=1,
            jobs_pending=0 if status == "failed" else 1,
            jobs_running=0,
            jobs_success=0,
            jobs_failed=1 if status == "failed" else 0,
        )
        db_session.add(run)
        db_session.flush()
        job = Job(
            job_type=JobType.FEED_COLLECT.value,
            status=JobStatus.FAILED.value if status == "failed" else JobStatus.PENDING.value,
            priority=10,
            task_run_id=run.id,
            account_id=account.id,
            payload_json={},
            retry_count=0,
            max_retries=3,
        )
        db_session.add(job)
        return run

    run_a = _run_for(account_a, status="failed")
    run_b = _run_for(account_b, status="queued")
    db_session.commit()
    return employee_a, employee_b, run_a, run_b


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
    product = ProductRepository(db_session)
    product.create_employee(user_id="operator-user", display_name="运营", email=None, status="active")
    db_session.commit()
    client = _client(db_session, role="operator")
    assert client.get("/api/operations/queue-summary").status_code == 403
    cancel = client.post("/api/operations/jobs/fail-stale-running", json={"reason": "deny"})
    assert cancel.status_code == 403


def test_operations_operator_scoped_task_runs(db_session):
    _employee_a, _employee_b, run_a, run_b = _seed_scoped_operator_runs(db_session)
    client_a = _client(db_session, role="operator", user_id="op-a-user")
    listed = client_a.get("/api/operations/task-runs")
    assert listed.status_code == 200
    ids = {item["id"] for item in listed.json()["items"]}
    assert run_a.id in ids
    assert run_b.id not in ids

    assert client_a.get(f"/api/operations/task-runs/{run_a.id}").status_code == 200
    assert client_a.get(f"/api/operations/task-runs/{run_b.id}").status_code == 404

    retry_own = client_a.post(f"/api/operations/task-runs/{run_a.id}/retry", json={"reason": "operator_retry"})
    assert retry_own.status_code == 200
    retry_other = client_a.post(f"/api/operations/task-runs/{run_b.id}/retry", json={"reason": "deny"})
    assert retry_other.status_code == 404

    supervisor = _client(db_session, role="supervisor")
    assert supervisor.get("/api/operations/task-runs").json()["total"] >= 2


def test_operations_task_run_status_group_active(db_session):
    template, run, job = _seed_template_and_run(db_session)
    failed_run = TaskRun(
        task_template_id=template.id,
        trigger_type=TaskRunTriggerType.MANUAL.value,
        status="failed",
        jobs_total=1,
        jobs_pending=0,
        jobs_running=0,
        jobs_success=0,
        jobs_failed=1,
    )
    db_session.add(failed_run)
    db_session.commit()

    client = _client(db_session)
    body = client.get("/api/operations/task-runs?status_group=active").json()
    assert body["total"] == 1
    assert body["items"][0]["id"] == run.id


def test_operations_task_run_status_group_needs_action(db_session):
    template, run, job = _seed_template_and_run(db_session)
    job.status = JobStatus.FAILED.value
    run.status = "failed"
    run.jobs_pending = 0
    run.jobs_failed = 1
    db_session.commit()

    client = _client(db_session)
    body = client.get("/api/operations/task-runs?status_group=needs_action").json()
    assert body["total"] >= 1
    assert any(item["id"] == run.id for item in body["items"])

    healthy_run = TaskRun(
        task_template_id=template.id,
        trigger_type=TaskRunTriggerType.MANUAL.value,
        status="running",
        jobs_total=1,
        jobs_pending=0,
        jobs_running=1,
        jobs_success=0,
        jobs_failed=0,
    )
    db_session.add(healthy_run)
    db_session.flush()
    healthy_job = Job(
        job_type=JobType.SEARCH_COLLECT.value,
        status=JobStatus.RUNNING.value,
        priority=10,
        task_run_id=healthy_run.id,
        started_at=utcnow(),
        payload_json={},
    )
    db_session.add(healthy_job)
    stale_run = TaskRun(
        task_template_id=template.id,
        trigger_type=TaskRunTriggerType.MANUAL.value,
        status="running",
        jobs_total=1,
        jobs_pending=0,
        jobs_running=1,
        jobs_success=0,
        jobs_failed=0,
    )
    db_session.add(stale_run)
    db_session.flush()
    stale_job = Job(
        job_type=JobType.SEARCH_COLLECT.value,
        status=JobStatus.RUNNING.value,
        priority=10,
        task_run_id=stale_run.id,
        started_at=utcnow() - timedelta(hours=2),
        payload_json={},
    )
    db_session.add(stale_job)
    db_session.commit()

    active_body = client.get("/api/operations/task-runs?status_group=active").json()
    assert any(item["id"] == healthy_run.id for item in active_body["items"])
    assert not any(item["id"] == stale_run.id for item in active_body["items"])

    needs_action_body = client.get("/api/operations/task-runs?status_group=needs_action").json()
    assert any(item["id"] == stale_run.id for item in needs_action_body["items"])
    assert any(item["has_stuck_jobs"] for item in needs_action_body["items"] if item["id"] == stale_run.id)


def test_operations_task_run_stuck_only(db_session):
    template, run, job = _seed_template_and_run(db_session)
    job.status = JobStatus.RUNNING.value
    job.started_at = utcnow() - timedelta(hours=2)
    run.status = "running"
    run.jobs_pending = 0
    run.jobs_running = 1
    db_session.commit()

    client = _client(db_session)
    body = client.get("/api/operations/task-runs?stuck_only=true").json()
    assert body["total"] == 1
    assert body["items"][0]["id"] == run.id
    assert body["items"][0]["has_stuck_jobs"] is True


def test_operations_queue_summary_bucket_counts(db_session):
    template, run, job = _seed_template_and_run(db_session)
    success_run = TaskRun(
        task_template_id=template.id,
        trigger_type=TaskRunTriggerType.MANUAL.value,
        status="success",
        jobs_total=1,
        jobs_pending=0,
        jobs_running=0,
        jobs_success=1,
        jobs_failed=0,
    )
    failed_run = TaskRun(
        task_template_id=template.id,
        trigger_type=TaskRunTriggerType.MANUAL.value,
        status="failed",
        jobs_total=1,
        jobs_pending=0,
        jobs_running=0,
        jobs_success=0,
        jobs_failed=1,
    )
    db_session.add_all([success_run, failed_run])
    db_session.commit()

    client = _client(db_session)
    body = client.get("/api/operations/queue-summary").json()
    buckets = body["task_run_bucket_counts"]
    assert buckets["active"] >= 1
    assert buckets["needs_action"] >= 1
    assert buckets["done"] >= 1
    assert buckets["active"] + buckets["needs_action"] + buckets["done"] == 3


def test_operations_job_stale_claimed_flag(db_session):
    template, run, job = _seed_template_and_run(db_session)
    job.status = JobStatus.CLAIMED.value
    job.claimed_at = utcnow() - timedelta(minutes=30)
    db_session.commit()

    client = _client(db_session)
    items = client.get("/api/operations/jobs").json()["items"]
    matched = next(item for item in items if item["id"] == job.id)
    assert matched["is_stale_claimed"] is True
    assert matched["is_stale_running"] is False

    stuck_items = client.get("/api/operations/jobs?stale_running_only=true").json()["items"]
    assert any(item["id"] == job.id for item in stuck_items)
