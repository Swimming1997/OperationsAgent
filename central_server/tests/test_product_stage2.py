from datetime import timedelta

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from intelligence_engine.db.models import (
    ContentAssignment,
    ContentIdentity,
    ContentOperatorNote,
    ContentWorkflowState,
    Job,
    KeywordRuleSet,
    LocalAgent,
    utcnow,
)
from intelligence_engine.db.session import get_db
from intelligence_engine.domain.enums import AgentStatus, ContentType, FeedType, JobStatus, JobType, Platform, SessionStatus, SourceSurface
from intelligence_engine.domain.schemas import DetailSnapshotInput, FeedCandidateInput
from intelligence_engine.main import create_app
from intelligence_engine.services.task_materialization import TaskMaterializationService
from intelligence_engine.storage.repositories.account_repository import AccountRepository
from intelligence_engine.storage.repositories.content_repository import ContentRepository
from intelligence_engine.storage.repositories.creator_repository import CreatorMonitorRepository
from intelligence_engine.storage.repositories.job_repository import JobRepository
from intelligence_engine.storage.repositories.product_repository import ProductRepository


def _client(db_session) -> TestClient:
    app = create_app()

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    client.headers.update({"X-Role": "admin", "X-User-Id": "admin-user"})
    return client


def _account(db_session):
    agent = AccountRepository(db_session).register_agent(
        employee_id=None,
        device_name="stage2-pc",
        machine_fingerprint="stage2-fp",
        agent_version="0.2.0",
        capabilities={"tasks": ["feed_collect", "creator_monitor", "search_collect"]},
    )
    account = AccountRepository(db_session).create_account(
        employee_id=None,
        platform=Platform.XHS.value,
        display_name="stage2-account",
        external_account_id=None,
        business_account_type=None,
        default_agent_id=agent.id,
        metadata={},
    )
    AccountRepository(db_session).create_session(
        account=account,
        local_agent_id=agent.id,
        session_type="browser_profile",
        profile_ref="profiles/test",
        cookie_ref=None,
        status=SessionStatus.READY.value,
        session_meta={},
    )
    db_session.flush()
    return account


def _content(db_session):
    job = JobRepository(db_session).create_job(job_type=JobType.FEED_COLLECT, payload={})
    candidate = FeedCandidateInput(
        platform=Platform.XHS,
        platform_content_id="stage2-content",
        canonical_url="https://www.xiaohongshu.com/explore/stage2-content",
        content_type=ContentType.IMAGE_TEXT,
        title_or_summary="SCI论文投稿经验",
        author_name="作者",
        visible_like_count=88,
        source_surface=SourceSurface.XHS_HOME_FEED,
        feed_type=FeedType.XHS_HOME_FEED,
        feed_position=1,
        discovered_at=utcnow(),
        raw_payload={},
    )
    repo = ContentRepository(db_session)
    content, _is_new, _event, _detail, _prelim = repo.ingest_feed_candidate(job_id=job.id, account_id=None, candidate=candidate)
    snapshot = repo.create_snapshot(
        content_id=content.id,
        account_id=None,
        snapshot=DetailSnapshotInput(title="SCI论文投稿经验", body_text="SCI 投稿经验和论文润色咨询"),
    )
    repo.evaluate_candidate(content_id=content.id, snapshot_id=snapshot.id)
    db_session.flush()
    return content


def test_recommendation_task_template_materializes_feed_collect_job(db_session):
    account = _account(db_session)
    template = ProductRepository(db_session).create_task_template(
        name="推荐流巡检",
        template_type="recommendation_feed_task",
        platform=Platform.XHS.value,
        account_id=account.id,
        business_account_type_id=None,
        config={"executor_account_id": account.id, "feed_type": "xhs_home_feed", "target_count": 10, "refresh_rounds": 1, "per_round_scroll_target": 10},
        enabled=True,
    )
    job_ids = TaskMaterializationService(db_session).materialize_template(template)
    job = db_session.get(Job, job_ids[0])

    assert job.job_type == JobType.FEED_COLLECT.value
    assert job.account_id == account.id
    assert job.local_agent_id == account.default_agent_id
    assert job.payload_json["target_count"] == 10


def test_creator_task_template_materializes_multiple_creator_monitor_jobs(db_session):
    account = _account(db_session)
    repo = ProductRepository(db_session)
    group = repo.create_benchmark_group(name="对标组", description=None, owner_employee_id=None, enabled=True, metadata={})
    monitor = CreatorMonitorRepository(db_session).create_monitor(
        platform=Platform.XHS.value,
        creator_platform_id="creator-a",
        creator_display_name="A",
        monitor_group_key=None,
        mapped_business_account_type=None,
        check_interval_seconds=900,
    )
    repo.add_benchmark_member(
        benchmark_group_id=group.id,
        creator_monitor_id=monitor.id,
        platform=Platform.XHS.value,
        creator_platform_id="creator-a",
        creator_profile_url=None,
        display_name="A",
        platform_context={},
        enabled=True,
    )
    repo.add_benchmark_member(
        benchmark_group_id=group.id,
        creator_monitor_id=None,
        platform=Platform.XHS.value,
        creator_platform_id="creator-b",
        creator_profile_url="https://www.xiaohongshu.com/user/profile/creator-b",
        display_name="B",
        platform_context={"xsec_source": "pc_feed"},
        enabled=True,
    )
    template = repo.create_task_template(
        name="对标监控",
        template_type="creator_monitor_task",
        platform=Platform.XHS.value,
        account_id=account.id,
        business_account_type_id=None,
        config={"executor_account_id": account.id, "benchmark_group_id": group.id, "max_latest_items": 20},
        enabled=True,
    )
    job_ids = TaskMaterializationService(db_session).materialize_template(template)

    assert len(job_ids) == 2
    jobs = list(db_session.scalars(select(Job).where(Job.id.in_(job_ids))))
    assert {job.job_type for job in jobs} == {JobType.CREATOR_MONITOR.value}
    assert all(job.account_id == account.id for job in jobs)
    assert db_session.scalar(select(func.count()).select_from(Job).where(Job.job_type == JobType.CREATOR_MONITOR.value)) == 2


def test_search_task_template_materializes_search_collect_job(db_session):
    account = _account(db_session)
    template = ProductRepository(db_session).create_task_template(
        name="关键词搜索",
        template_type="keyword_search_task",
        platform=Platform.XHS.value,
        account_id=account.id,
        business_account_type_id=None,
        config={"executor_account_id": account.id, "platform": "xhs", "keywords": ["论文", "投稿"], "max_items": 30},
        enabled=True,
    )
    job_ids = TaskMaterializationService(db_session).materialize_template(template)
    job = db_session.get(Job, job_ids[0])

    assert job.job_type == JobType.SEARCH_COLLECT.value
    assert job.payload_json["keywords"] == ["论文", "投稿"]
    assert job.payload_json["max_items"] == 30


def test_manual_run_api_and_due_schedule_materialization(db_session):
    client = _client(db_session)
    account = _account(db_session)
    template = client.post(
        "/api/task-templates",
        json={
            "name": "手动推荐流",
            "template_type": "recommendation_feed_task",
            "platform": "xhs",
            "config": {"executor_account_id": account.id, "feed_type": "xhs_home_feed", "target_count": 5},
        },
    ).json()
    run_response = client.post(f"/api/task-templates/{template['id']}/run")
    assert run_response.status_code == 200
    assert run_response.json()["jobs_created"] == 1
    assert run_response.json()["task_run_id"]

    schedule = client.post(
        "/api/task-schedules",
        json={
            "task_template_id": template["id"],
            "schedule_type": "interval_seconds",
            "interval_seconds": 60,
            "next_run_at": (utcnow() - timedelta(seconds=1)).isoformat(),
        },
    ).json()
    materialize_response = client.post("/api/task-schedules/materialize-due")
    assert materialize_response.status_code == 200
    assert materialize_response.json()["job_count"] == 1
    assert materialize_response.json()["materialized"][0]["task_run_id"]
    db_session.expire_all()
    assert db_session.get(__import__("intelligence_engine.db.models", fromlist=["TaskSchedule"]).TaskSchedule, schedule["id"]).last_materialized_at is not None


def test_register_agent_updates_capabilities_by_machine_fingerprint(db_session):
    client = _client(db_session)
    agent = AccountRepository(db_session).register_agent(
        employee_id=None,
        device_name="Old Device",
        machine_fingerprint="register-update-fp",
        agent_version="0.0.1",
        capabilities={"runner": "legacy_runner"},
    )
    db_session.commit()
    response = client.post(
        "/api/agents/register",
        json={
            "device_name": "AMiracle Local Agent",
            "machine_fingerprint": "register-update-fp",
            "agent_version": "0.1.0",
            "capabilities": {
                "platforms": ["xhs"],
                "job_types": ["feed_collect"],
                "runtime": "local_agent_runtime_v1",
            },
        },
    )
    assert response.status_code == 200
    assert response.json()["agent_id"] == agent.id
    db_session.expire_all()
    updated = db_session.get(LocalAgent, agent.id)
    assert updated.device_name == "AMiracle Local Agent"
    assert updated.capabilities_json["runtime"] == "local_agent_runtime_v1"
    assert "feed_collect" in updated.capabilities_json["job_types"]


def test_task_template_readiness_accepts_runtime_job_types_capabilities(db_session):
    client = _client(db_session)
    agent = AccountRepository(db_session).register_agent(
        employee_id=None,
        device_name="AMiracle Local Agent",
        machine_fingerprint="runtime-v1-fp",
        agent_version="0.1.0",
        capabilities={
            "platforms": ["xhs"],
            "supports_cdp": True,
            "job_types": ["feed_collect", "creator_monitor", "detail_fetch", "comment_fetch", "search_collect"],
            "runtime": "local_agent_runtime_v1",
        },
    )
    account = AccountRepository(db_session).create_account(
        employee_id=None,
        platform=Platform.XHS.value,
        display_name="runtime-account",
        external_account_id=None,
        business_account_type=None,
        default_agent_id=agent.id,
        metadata={},
    )
    AccountRepository(db_session).create_session(
        account=account,
        local_agent_id=agent.id,
        session_type="browser",
        profile_ref=None,
        cookie_ref=None,
        status=SessionStatus.READY.value,
        session_meta={"cdp_url": "http://127.0.0.1:9222"},
    )
    template = ProductRepository(db_session).create_task_template(
        name="Runtime 推荐流",
        template_type="recommendation_feed_task",
        platform=Platform.XHS.value,
        account_id=account.id,
        business_account_type_id=None,
        config={
            "executor_account_id": account.id,
            "feed_type": "xhs_home_feed",
            "target_count": 5,
            "refresh_rounds": 1,
            "per_round_scroll_target": 5,
        },
        enabled=True,
    )
    db_session.commit()

    response = client.get(f"/api/task-templates/{template.id}/readiness")

    assert response.status_code == 200
    body = response.json()
    assert body["ready"] is True
    support_check = next(item for item in body["checks"] if item["key"] == "agent_supports_job_type")
    assert support_check["ok"] is True
    assert "feed_collect" in support_check["message"]


def test_task_template_readiness_success_and_failure(db_session):
    client = _client(db_session)
    account = _account(db_session)
    template = ProductRepository(db_session).create_task_template(
        name="可运行推荐流",
        template_type="recommendation_feed_task",
        platform=Platform.XHS.value,
        account_id=account.id,
        business_account_type_id=None,
        config={"executor_account_id": account.id, "feed_type": "xhs_home_feed", "target_count": 5, "refresh_rounds": 1, "per_round_scroll_target": 5},
        enabled=True,
    )
    db_session.commit()
    response = client.get(f"/api/task-templates/{template.id}/readiness")
    assert response.status_code == 200
    assert response.json()["ready"] is True

    account.default_agent_id = None
    db_session.commit()
    blocked = client.get(f"/api/task-templates/{template.id}/readiness")
    assert blocked.json()["ready"] is False
    assert "账号未绑定 Agent" in blocked.json()["messages"]


def test_manual_run_creates_task_run_and_job_detail_aggregates_feed_summary(db_session):
    client = _client(db_session)
    account = _account(db_session)
    template = ProductRepository(db_session).create_task_template(
        name="运行摘要推荐流",
        template_type="recommendation_feed_task",
        platform=Platform.XHS.value,
        account_id=account.id,
        business_account_type_id=None,
        config={"executor_account_id": account.id, "feed_type": "xhs_home_feed", "target_count": 10, "refresh_rounds": 1, "per_round_scroll_target": 10},
        enabled=True,
    )
    db_session.commit()
    run_body = client.post(f"/api/task-templates/{template.id}/run").json()
    assert run_body["jobs_created"] == 1
    job = db_session.get(Job, run_body["jobs"][0]["job_id"])
    assert job.task_run_id == run_body["task_run_id"]

    job_repo = JobRepository(db_session)
    job_repo.claim_jobs_for_agent(agent_id=account.default_agent_id, supported_job_types=[JobType.FEED_COLLECT], max_jobs=1, ttl_seconds=60)
    job_repo.mark_started(job, agent_id=account.default_agent_id)
    job_repo.mark_success(job, status=JobStatus.SUCCESS, result_summary={"raw_items_seen": 10, "ingestion_success_count": 10, "unique_contents_inserted": 3, "detail_jobs_enqueued": 3})
    db_session.commit()

    detail = client.get(f"/api/task-runs/{run_body['task_run_id']}")
    assert detail.status_code == 200
    body = detail.json()
    assert body["status"] == "success"
    assert body["jobs_success"] == 1
    assert body["result_summary"]["feed_collect"]["inserted_count"] == 3
    assert body["result_summary"]["feed_collect"]["duplicate_count"] == 7


def test_task_run_detail_aggregates_creator_summary(db_session):
    client = _client(db_session)
    account = _account(db_session)
    repo = ProductRepository(db_session)
    group = repo.create_benchmark_group(name="对标组摘要", description=None, owner_employee_id=None, enabled=True, metadata={})
    monitor = CreatorMonitorRepository(db_session).create_monitor(
        platform=Platform.XHS.value,
        creator_platform_id="creator-summary",
        creator_display_name="摘要作者",
        monitor_group_key=None,
        mapped_business_account_type=None,
        check_interval_seconds=900,
    )
    repo.add_benchmark_member(
        benchmark_group_id=group.id,
        creator_monitor_id=monitor.id,
        platform=Platform.XHS.value,
        creator_platform_id="creator-summary",
        creator_profile_url=None,
        display_name="摘要作者",
        platform_context={},
        enabled=True,
    )
    template = repo.create_task_template(
        name="对标摘要",
        template_type="creator_monitor_task",
        platform=Platform.XHS.value,
        account_id=account.id,
        business_account_type_id=None,
        config={"executor_account_id": account.id, "benchmark_group_id": group.id, "auto_detail_fetch": True},
        enabled=True,
    )
    db_session.commit()
    run_body = client.post(f"/api/task-templates/{template.id}/run").json()
    job = db_session.get(Job, run_body["jobs"][0]["job_id"])
    job_repo = JobRepository(db_session)
    job_repo.claim_jobs_for_agent(agent_id=account.default_agent_id, supported_job_types=[JobType.CREATOR_MONITOR], max_jobs=1, ttl_seconds=60)
    job_repo.mark_started(job, agent_id=account.default_agent_id)
    job_repo.mark_success(job, status=JobStatus.SUCCESS, result_summary={"items_seen": 5, "new_content_count": 2, "duplicate_content_count": 3, "detail_job_enqueue_count": 2})
    db_session.commit()

    body = client.get(f"/api/task-runs/{run_body['task_run_id']}").json()
    assert body["result_summary"]["creator_monitor"]["new_count"] == 2
    assert body["result_summary"]["creator_monitor"]["duplicate_count"] == 3


def test_content_workflow_state_assign_select_discard_archive_and_notes(db_session):
    client = _client(db_session)
    content = _content(db_session)
    assert db_session.scalar(select(ContentWorkflowState).where(ContentWorkflowState.content_id == content.id)).workflow_status == "pending_review"

    assign_response = client.post(f"/api/intelligence/contents/{content.id}/assign", json={"assigned_to_user_id": "user-a", "assigned_by_user_id": "user-b", "remark": "跟进"})
    assert assign_response.status_code == 200
    assert assign_response.json()["workflow_status"] == "assigned"
    assert db_session.scalar(select(func.count()).select_from(ContentAssignment)) == 1

    note_response = client.post(f"/api/intelligence/contents/{content.id}/notes", json={"user_id": "user-a", "note": "值得看"})
    assert note_response.status_code == 200
    notes_response = client.get(f"/api/intelligence/contents/{content.id}/notes")
    assert notes_response.status_code == 200
    assert notes_response.json()[0]["note"] == "值得看"

    select_response = client.post(f"/api/intelligence/contents/{content.id}/select", json={"user_id": "user-a", "note": "选中"})
    assert select_response.json()["workflow_status"] == "selected"
    discard_response = client.post(f"/api/intelligence/contents/{content.id}/discard", json={"user_id": "user-a", "note": "测试丢弃"})
    assert discard_response.json()["workflow_status"] == "discarded"
    archive_response = client.post(f"/api/intelligence/contents/{content.id}/archive", json={"user_id": "user-a"})
    assert archive_response.json()["workflow_status"] == "archived"
    assert db_session.scalar(select(func.count()).select_from(ContentOperatorNote)) == 3


def test_intelligence_contents_query_includes_workflow_info(db_session):
    client = _client(db_session)
    content = _content(db_session)
    client.post(f"/api/intelligence/contents/{content.id}/assign", json={"assigned_to_user_id": "user-a"})
    response = client.get("/api/intelligence/contents/product", params={"workflow_status": "assigned", "business_keyword": "SCI"})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total"] == 1
    item = body["items"][0]
    assert item["content_id"] == content.id
    assert item["workflow_status"] == "assigned"
    assert item["assigned_to_user_id"] == "user-a"
    assert item["discovery_sources_summary"]["source_surfaces"]["xhs_home_feed"] == 1


def test_business_account_type_rule_set_binding_api(db_session):
    client = _client(db_session)
    business_type = client.post("/api/business-account-types", json={"name": "论文账号"}).json()
    rule_set = KeywordRuleSet(name="论文获客V1", rule_scope="xhs", enabled=True, config_json={})
    db_session.add(rule_set)
    db_session.commit()

    bind_response = client.post(f"/api/business-account-types/{business_type['id']}/rule-sets", json={"rule_set_id": rule_set.id, "is_default": True})
    assert bind_response.status_code == 200
    assert bind_response.json()["rule_set_name"] == "论文获客V1"

    list_response = client.get(f"/api/business-account-types/{business_type['id']}/rule-sets")
    assert list_response.status_code == 200
    assert list_response.json()[0]["is_default"] is True
