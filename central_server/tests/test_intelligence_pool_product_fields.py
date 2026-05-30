from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from intelligence_engine.db.models import CandidateDecision, CommentSnapshot, ContentIdentity, ContentSnapshot, Employee, Job, PlatformAccount, User, utcnow
from intelligence_engine.db.session import get_db
from intelligence_engine.domain.enums import AccountRole, AccountStatus, AuthStatus, CandidateBucket, ContentType, ContentWorkflowStatus, JobType, Platform, SourceSurface
from intelligence_engine.domain.schemas import FeedCandidateInput
from intelligence_engine.main import create_app
from intelligence_engine.domain.schemas import DetailSnapshotInput
from intelligence_engine.storage.repositories.content_repository import ContentRepository
from intelligence_engine.storage.repositories.job_repository import JobRepository
from intelligence_engine.storage.repositories.workflow_repository import WorkflowRepository


def _client(db_session, *, role: str = "admin", user_id: str = "admin-user") -> TestClient:
    app = create_app()

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    client.headers.update({"X-Role": role, "X-User-Id": user_id})
    return client


def _seed_account(db_session, *, employee_id: str | None = None, display_name: str = "采集账号") -> PlatformAccount:
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


def _seed_employee_account(db_session, *, user_id: str = "operator-user") -> tuple[Employee, PlatformAccount]:
    user = User(id=user_id, username=user_id, display_name="运营")
    employee = Employee(user_id=user.id, display_name="运营")
    db_session.add_all([user, employee])
    db_session.flush()
    account = _seed_account(db_session, employee_id=employee.id, display_name="运营采集号")
    return employee, account


def _seed_content(db_session, *, account_id: str | None = None):
    job = JobRepository(db_session).create_job(job_type=JobType.SEARCH_COLLECT, payload={"keywords": ["SCI"]})
    candidate = FeedCandidateInput(
        platform=Platform.XHS,
        platform_content_id="pool-product-1",
        canonical_url="https://www.xiaohongshu.com/explore/pool-product-1",
        content_type=ContentType.IMAGE_TEXT,
        title_or_summary="SCI投稿经验",
        author_name="作者",
        visible_like_count=120,
        source_surface=SourceSurface.SEARCH,
        feed_position=2,
        discovered_at=utcnow(),
        raw_payload={
            "search_keyword": "SCI",
            "search_sort": "comprehensive",
            "note_type": "all",
            "publish_time": "one_week",
            "search_scope": "all",
            "location_filter": "all",
            "search_rank": 2,
        },
    )
    repo = ContentRepository(db_session)
    content, _is_new, _event, _detail, _prelim = repo.ingest_feed_candidate(job_id=job.id, account_id=account_id, candidate=candidate, enqueue_detail_job=False)
    snapshot = repo.create_snapshot(
        content_id=content.id,
        account_id=None,
        snapshot=DetailSnapshotInput(
            title="SCI投稿经验",
            body_text="#SCI #医学SCI 投稿经验",
            raw_payload={"platform_tags": ["#SCI", "#医学SCI"]},
        ),
    )
    content.latest_snapshot_id = snapshot.id
    metadata = dict(content.metadata_json or {})
    metadata["manual_tags"] = ["可仿写"]
    metadata["platform_tags"] = ["#SCI"]
    content.metadata_json = metadata
    db_session.add(
        CommentSnapshot(
            content_id=content.id,
            platform_comment_id="c1",
            body_text="评论",
            fetched_at=utcnow(),
        )
    )
    repo.evaluate_candidate(content_id=content.id, snapshot_id=snapshot.id)
    db_session.flush()
    return content


def test_product_list_content_query_matches_title(db_session):
    content = _seed_content(db_session)
    client = _client(db_session)
    hit = client.get("/api/intelligence/contents/product", params={"content_query": "SCI投稿"})
    assert hit.status_code == 200, hit.text
    assert any(row["content_id"] == content.id for row in hit.json()["items"])

    legacy = client.get("/api/intelligence/contents/product", params={"business_keyword": "SCI投稿"})
    assert legacy.status_code == 200, legacy.text
    assert any(row["content_id"] == content.id for row in legacy.json()["items"])


def test_product_list_returns_enriched_fields(db_session):
    content = _seed_content(db_session)
    response = _client(db_session).get("/api/intelligence/contents/product")
    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] >= 1
    item = next(row for row in payload["items"] if row["content_id"] == content.id)
    assert item["data_status"] == "comments_ready"
    assert item["discovery_count"] >= 1
    assert item["search_keyword"] == "SCI"
    assert item["manual_tags"] == ["可仿写"]
    assert item["platform_tags"]


def test_product_list_filters_by_data_status_and_sort(db_session):
    _seed_content(db_session)
    response = _client(db_session).get("/api/intelligence/contents/product", params={"data_status": "comments_ready", "sort_by": "like_count"})
    assert response.status_code == 200
    assert response.json()["total"] >= 1


def test_bulk_status_marks_contents_discarded(db_session):
    content = _seed_content(db_session)
    response = _client(db_session).post(
        "/api/intelligence/contents/bulk-status",
        json={"content_ids": [content.id], "action": "discard", "user_id": "admin-user"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["failed"] == []
    assert payload["succeeded"][0]["content_id"] == content.id
    assert payload["succeeded"][0]["workflow_status"] == "discarded"


def test_content_query_finds_discard_bucket_title(db_session):
    job = JobRepository(db_session).create_job(job_type=JobType.SEARCH_COLLECT, payload={"keywords": ["滨江"]})
    candidate = FeedCandidateInput(
        platform=Platform.XHS,
        platform_content_id="pool-binjiang-1",
        canonical_url="https://www.xiaohongshu.com/explore/pool-binjiang-1",
        content_type=ContentType.IMAGE_TEXT,
        title_or_summary="滨江好房推荐",
        author_name="作者",
        visible_like_count=10,
        source_surface=SourceSurface.SEARCH,
        feed_position=1,
        discovered_at=utcnow(),
        raw_payload={"search_keyword": "滨江"},
    )
    repo = ContentRepository(db_session)
    content, *_ = repo.ingest_feed_candidate(job_id=job.id, account_id=None, candidate=candidate, enqueue_detail_job=False)
    snapshot = repo.create_snapshot(
        content_id=content.id,
        account_id=None,
        snapshot=DetailSnapshotInput(title="滨江好房推荐", body_text="正文", raw_payload={}),
    )
    content.latest_snapshot_id = snapshot.id
    repo.evaluate_candidate(content_id=content.id, snapshot_id=snapshot.id)
    decision = WorkflowRepository(db_session).latest_decision_for_content(content.id)
    assert decision is not None
    decision.candidate_bucket = CandidateBucket.DISCARD.value
    db_session.flush()

    client = _client(db_session)
    default_list = client.get("/api/intelligence/contents/product")
    assert any(row["content_id"] == content.id for row in default_list.json()["items"])

    search = client.get("/api/intelligence/contents/product", params={"content_query": "滨江"})
    assert search.status_code == 200
    assert any(row["content_id"] == content.id for row in search.json()["items"])
    hit = next(row for row in search.json()["items"] if row["content_id"] == content.id)
    assert hit["candidate_bucket"] == "discard"
    assert "滨江" in (hit["title"] or "")


def test_content_query_applies_other_filters(db_session):
    job = JobRepository(db_session).create_job(job_type=JobType.SEARCH_COLLECT, payload={"keywords": ["滨江"]})
    old_discovered = utcnow() - timedelta(days=30)
    candidate = FeedCandidateInput(
        platform=Platform.XHS,
        platform_content_id="pool-binjiang-old-1",
        canonical_url="https://www.xiaohongshu.com/explore/pool-binjiang-old-1",
        content_type=ContentType.IMAGE_TEXT,
        title_or_summary="滨江老条目",
        author_name="作者",
        visible_like_count=10,
        source_surface=SourceSurface.SEARCH,
        feed_position=1,
        discovered_at=old_discovered,
        raw_payload={"search_keyword": "滨江"},
    )
    repo = ContentRepository(db_session)
    content, *_ = repo.ingest_feed_candidate(job_id=job.id, account_id=None, candidate=candidate, enqueue_detail_job=False)
    snapshot = repo.create_snapshot(
        content_id=content.id,
        account_id=None,
        snapshot=DetailSnapshotInput(title="滨江老条目", body_text="正文", raw_payload={}),
    )
    content.latest_snapshot_id = snapshot.id
    repo.evaluate_candidate(content_id=content.id, snapshot_id=snapshot.id)
    decision = WorkflowRepository(db_session).latest_decision_for_content(content.id)
    assert decision is not None
    decision.candidate_bucket = CandidateBucket.DISCARD.value
    db_session.flush()

    future_after = (utcnow() + timedelta(days=1)).isoformat()
    response = _client(db_session).get(
        "/api/intelligence/contents/product",
        params={
            "content_query": "滨江",
            "discovered_after": future_after,
            "in_reference_library": False,
            "platform": Platform.XHS.value,
        },
    )
    assert response.status_code == 200
    assert not any(row["content_id"] == content.id for row in response.json()["items"])


def test_discarded_filter_keeps_discard_bucket_contents(db_session):
    content = _seed_content(db_session)
    WorkflowRepository(db_session).set_status(
        content_id=content.id,
        status=ContentWorkflowStatus.DISCARDED,
        user_id="admin-user",
    )
    db_session.add(
        CandidateDecision(
            content_id=content.id,
            snapshot_id=content.latest_snapshot_id,
            candidate_bucket=CandidateBucket.DISCARD.value,
            decision_reason_json={"reason": "detail fetch rule reevaluated"},
            evaluated_at=utcnow(),
        )
    )
    db_session.flush()

    response = _client(db_session).get(
        "/api/intelligence/contents/product",
        params={"workflow_status": "discarded"},
    )

    assert response.status_code == 200
    assert any(item["content_id"] == content.id for item in response.json()["items"])


def test_intelligence_filters_accept_status_and_bucket_unions(db_session):
    content = _seed_content(db_session)
    WorkflowRepository(db_session).set_status(
        content_id=content.id,
        status=ContentWorkflowStatus.DISCARDED,
        user_id="admin-user",
    )
    db_session.add(
        CandidateDecision(
            content_id=content.id,
            snapshot_id=content.latest_snapshot_id,
            candidate_bucket=CandidateBucket.DISCARD.value,
            decision_reason_json={"reason": "detail fetch rule reevaluated"},
            evaluated_at=utcnow(),
        )
    )
    db_session.flush()

    response = _client(db_session).get(
        "/api/intelligence/contents/product",
        params={
            "workflow_status": "pending_review,discarded",
            "candidate_bucket": "lead_candidate,discard",
        },
    )

    assert response.status_code == 200
    assert any(item["content_id"] == content.id for item in response.json()["items"])


def test_manual_enqueue_fetch_sets_pending_job_on_detail(db_session):
    content = _seed_content(db_session)
    client = _client(db_session)

    detail_response = client.post(f"/api/intelligence/contents/{content.id}/enqueue-detail-fetch")
    comment_response = client.post(f"/api/intelligence/contents/{content.id}/enqueue-comment-fetch")

    assert detail_response.status_code == 200
    assert comment_response.status_code == 200
    detail = client.get(f"/api/intelligence/contents/{content.id}/product-detail")
    assert detail.status_code == 200
    payload = detail.json()
    assert payload["pending_detail_job_id"] == detail_response.json()["job_id"]
    assert payload["pending_comment_job_id"] == comment_response.json()["job_id"]


def test_admin_manual_enqueue_uses_latest_discovery_account(db_session):
    discovery_account = _seed_account(db_session, display_name="最近发现账号")
    content = _seed_content(db_session, account_id=discovery_account.id)
    response = _client(db_session).post(f"/api/intelligence/contents/{content.id}/enqueue-detail-fetch")

    assert response.status_code == 200
    job = db_session.get(Job, response.json()["job_id"])
    assert job.account_id == discovery_account.id


def test_operator_manual_enqueue_uses_employee_account(db_session):
    discovery_account = _seed_account(db_session, display_name="最近发现账号")
    _employee, employee_account = _seed_employee_account(db_session)
    content = _seed_content(db_session, account_id=discovery_account.id)
    response = _client(db_session, role="operator", user_id="operator-user").post(
        f"/api/intelligence/contents/{content.id}/enqueue-comment-fetch"
    )

    assert response.status_code == 200
    job = db_session.get(Job, response.json()["job_id"])
    assert job.account_id == employee_account.id
