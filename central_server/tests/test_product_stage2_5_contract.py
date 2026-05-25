import json
import os
import subprocess
import sys
from datetime import timedelta
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from intelligence_engine.db.base import Base
from intelligence_engine.db import models  # noqa: F401
from intelligence_engine.db.models import Job, TaskSchedule, utcnow
from intelligence_engine.db.session import get_db
from intelligence_engine.domain.enums import ContentType, FeedType, JobType, Platform, SourceSurface
from intelligence_engine.domain.product_schemas import KeywordSearchTaskTemplateCreate, RecommendationFeedTaskTemplateCreate
from intelligence_engine.domain.schemas import CommentSnapshotInput, DetailSnapshotInput, FeedCandidateInput
from intelligence_engine.main import create_app
from intelligence_engine.storage.repositories.account_repository import AccountRepository
from intelligence_engine.storage.repositories.content_repository import ContentRepository
from intelligence_engine.storage.repositories.job_repository import JobRepository
from intelligence_engine.storage.repositories.product_repository import ProductRepository


CENTRAL_ROOT = Path(__file__).resolve().parents[1]

ADMIN_HEADERS = {"X-Role": "admin", "X-User-Id": "admin-user"}
OPERATOR_HEADERS = {"X-Role": "operator", "X-User-Id": "operator-user"}


def _client(db_session, headers: dict | None = None) -> TestClient:
    app = create_app()

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    if headers:
        client.headers.update(headers)
    return client


def _account(db_session):
    agent = AccountRepository(db_session).register_agent(
        employee_id=None,
        device_name="contract-pc",
        machine_fingerprint="contract-fp",
        agent_version="0.2.0",
        capabilities={},
    )
    account = AccountRepository(db_session).create_account(
        employee_id=None,
        platform=Platform.XHS.value,
        display_name="contract-account",
        external_account_id=None,
        business_account_type=None,
        default_agent_id=agent.id,
        metadata={},
    )
    db_session.flush()
    return account


def _content_with_snapshot(db_session):
    job = JobRepository(db_session).create_job(job_type=JobType.FEED_COLLECT, payload={})
    candidate = FeedCandidateInput(
        platform=Platform.XHS,
        platform_content_id="contract-content",
        canonical_url="https://www.xiaohongshu.com/explore/contract-content",
        content_type=ContentType.IMAGE_TEXT,
        title_or_summary="SCI论文投稿",
        cover_url="https://img.local/cover.jpg",
        author_name="作者",
        visible_like_count=99,
        source_surface=SourceSurface.XHS_HOME_FEED,
        feed_type=FeedType.XHS_HOME_FEED,
        feed_position=1,
        discovered_at=utcnow(),
    )
    content, _is_new, _event, _detail, _prelim = ContentRepository(db_session).ingest_feed_candidate(job_id=job.id, account_id=None, candidate=candidate)
    snapshot = ContentRepository(db_session).create_snapshot(
        content_id=content.id,
        account_id=None,
        snapshot=DetailSnapshotInput(title="SCI论文投稿避坑", body_text="投稿经验", author_name="作者", like_count=99, comment_count=8, collect_count=3),
    )
    ContentRepository(db_session).evaluate_candidate(content_id=content.id, snapshot_id=snapshot.id)
    ContentRepository(db_session).create_or_update_comments(
        content_id=content.id,
        comments=[
            CommentSnapshotInput(
                platform_comment_id="comment-1",
                author_platform_id="commenter-1",
                author_name="评论者",
                body_text="求推荐，怎么联系？",
                like_count=3,
                created_time=utcnow(),
            )
        ],
    )
    db_session.flush()
    return content


def test_typed_task_template_dto_validation_and_endpoints(db_session):
    account = _account(db_session)
    RecommendationFeedTaskTemplateCreate(
        name="推荐流表单",
        executor_account_id=account.id,
        feed_type=FeedType.XHS_HOME_FEED,
        target_count=50,
    )
    try:
        KeywordSearchTaskTemplateCreate(name="搜索", executor_account_id=account.id, platform=Platform.XHS, keywords=[])
    except ValueError as exc:
        assert "keywords" in str(exc)
    else:
        raise AssertionError("empty keywords should fail validation")

    client = _client(db_session, ADMIN_HEADERS)
    created = client.post(
        "/api/task-templates/recommendation-feed",
        json={
            "name": "推荐流表单",
            "executor_account_id": account.id,
            "feed_type": "xhs_home_feed",
            "target_count": 20,
            "behavior_profile_id": "behavior-1",
        },
    )
    assert created.status_code == 200, created.text
    body = created.json()
    assert body["template_type"] == "recommendation_feed_task"
    assert body["typed_payload"]["target_count"] == 20
    assert body["typed_payload"]["behavior_profile_id"] == "behavior-1"

    updated = client.patch(f"/api/task-templates/recommendation-feed/{body['id']}", json={"target_count": 30, "enabled": False})
    assert updated.status_code == 200
    assert updated.json()["typed_payload"]["target_count"] == 30
    assert updated.json()["enabled"] is False

    detail = client.get(f"/api/task-templates/{body['id']}")
    assert detail.status_code == 200
    listed = client.get("/api/task-templates/list")
    assert listed.status_code == 200
    assert listed.json()[0]["key_fields"]["target_count"] == 30


def test_product_intelligence_list_and_detail_contract(db_session):
    content = _content_with_snapshot(db_session)
    client = _client(db_session, ADMIN_HEADERS)
    client.post(f"/api/intelligence/contents/{content.id}/assign", json={"assigned_to_user_id": "operator-user"})
    client.post(f"/api/intelligence/contents/{content.id}/notes", json={"user_id": "operator-user", "note": "列表备注"})

    listed = client.get("/api/intelligence/contents/product", params={"workflow_status": "assigned"})
    assert listed.status_code == 200, listed.text
    item = listed.json()["items"][0]
    assert item["content_id"] == content.id
    assert item["collect_count"] == 3
    assert item["latest_snapshot_time"] is not None
    assert item["first_seen_at"] is not None
    assert item["last_seen_at"] is not None
    assert "discovery_sources_summary" in item

    detail = client.get(f"/api/intelligence/contents/{content.id}/product-detail")
    assert detail.status_code == 200, detail.text
    body = detail.json()
    assert body["identity"]["id"] == content.id
    assert body["latest_snapshot"]["title"] == "SCI论文投稿避坑"
    assert body["latest_candidate_decision"]["candidate_bucket"] in {"content_candidate", "lead_candidate", "pending_enrichment", "discard"}
    assert body["workflow_state"]["workflow_status"] == "assigned"
    assert body["notes"][0]["note"] == "列表备注"
    assert body["comments"][0]["body_text"] == "求推荐，怎么联系？"
    assert body["comments"][0]["author_platform_id"] == "commenter-1"
    assert body["assignment_history"][0]["assigned_to_user_id"] == "operator-user"
    assert body["discovery_events_summary"][0]["source_surface"] == "xhs_home_feed"


def test_options_api_and_permission_boundaries(db_session):
    client = _client(db_session)
    options = client.get("/api/product/options")
    assert options.status_code == 200
    assert "xhs" in {item["value"] for item in options.json()["platforms"]}
    assert client.get("/api/product/options/roles").status_code == 200

    forbidden = client.get("/api/users")
    assert forbidden.status_code == 403
    operator_client = _client(db_session, OPERATOR_HEADERS)
    assert operator_client.get("/api/users").status_code == 403

    content = _content_with_snapshot(db_session)
    admin_client = _client(db_session, ADMIN_HEADERS)
    admin_client.post(f"/api/intelligence/contents/{content.id}/assign", json={"assigned_to_user_id": "operator-user"})
    assert operator_client.post(f"/api/intelligence/contents/{content.id}/notes", json={"user_id": "operator-user", "note": "operator note"}).status_code == 200
    own_list = operator_client.get("/api/intelligence/contents/product")
    assert own_list.status_code == 200
    assert own_list.json()["total"] == 1


def test_scheduler_cli_dry_run_and_run(tmp_path):
    db_path = tmp_path / "scheduler.db"
    database_url = f"sqlite:///{db_path}"
    engine = create_engine(database_url, connect_args={"check_same_thread": False}, future=True)
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    with SessionLocal() as session:
        account = AccountRepository(session).create_account(
            employee_id=None,
            platform=Platform.XHS.value,
            display_name="scheduler-account",
            external_account_id=None,
            business_account_type=None,
            default_agent_id=None,
            metadata={},
        )
        template = ProductRepository(session).create_task_template(
            name="due-template",
            template_type="recommendation_feed_task",
            platform=Platform.XHS.value,
            account_id=account.id,
            business_account_type_id=None,
            config={"executor_account_id": account.id, "feed_type": "xhs_home_feed", "target_count": 1},
            enabled=True,
        )
        ProductRepository(session).create_task_schedule(
            task_template_id=template.id,
            schedule_type="interval_seconds",
            interval_seconds=60,
            daily_time_window={},
            enabled=True,
            next_run_at=utcnow() - timedelta(seconds=1),
        )
        session.commit()
    engine.dispose()

    env = os.environ.copy()
    env["INTEL_ENGINE_DATABASE_URL"] = database_url
    dry = subprocess.run([sys.executable, "scripts/materialize_due_schedules.py", "--dry-run"], cwd=CENTRAL_ROOT, env=env, capture_output=True, text=True, encoding="utf-8")
    assert dry.returncode == 0, dry.stderr
    assert json.loads(dry.stdout)["due_schedule_count"] == 1

    run = subprocess.run([sys.executable, "scripts/materialize_due_schedules.py"], cwd=CENTRAL_ROOT, env=env, capture_output=True, text=True, encoding="utf-8")
    assert run.returncode == 0, run.stderr
    assert json.loads(run.stdout)["job_count"] == 1
    engine = create_engine(database_url, connect_args={"check_same_thread": False}, future=True)
    with sessionmaker(bind=engine, future=True)() as session:
        assert session.query(Job).count() == 1
        assert session.query(TaskSchedule).first().last_materialized_at is not None
    engine.dispose()
