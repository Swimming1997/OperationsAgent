from datetime import datetime, timezone

from sqlalchemy import select

from intelligence_engine.db.models import ContentWorkflowState
from intelligence_engine.domain.enums import ContentType, ContentWorkflowStatus, JobType, Platform, SourceSurface
from intelligence_engine.domain.schemas import FeedCandidateInput
from intelligence_engine.storage.repositories.content_repository import ContentRepository
from intelligence_engine.storage.repositories.job_repository import JobRepository
from intelligence_engine.storage.repositories.workflow_repository import WorkflowRepository
from tests.test_intelligence_pool_product_fields import _client, _seed_content, _seed_employee_account


def test_ingest_auto_assigns_to_platform_account_owner(db_session):
    _employee, account = _seed_employee_account(db_session, user_id="operator-wang")
    content = _seed_content(db_session, account_id=account.id)

    state = db_session.scalar(select(ContentWorkflowState).where(ContentWorkflowState.content_id == content.id))
    assert state is not None
    assert state.assigned_to_user_id == "operator-wang"
    assert state.workflow_status == ContentWorkflowStatus.ASSIGNED.value


def test_ingest_does_not_override_existing_assignment(db_session):
    _employee, account = _seed_employee_account(db_session, user_id="operator-wang")
    _seed_employee_account(db_session, user_id="operator-other")
    content = _seed_content(db_session, account_id=account.id)
    WorkflowRepository(db_session).assign(
        content_id=content.id,
        assigned_to_user_id="operator-other",
        assigned_by_user_id="supervisor-user",
        remark="主管已分配",
    )

    state = db_session.scalar(select(ContentWorkflowState).where(ContentWorkflowState.content_id == content.id))
    assert state.assigned_to_user_id == "operator-other"


def test_ingest_without_account_does_not_auto_assign(db_session):
    content = _seed_content(db_session, account_id=None)
    state = db_session.scalar(select(ContentWorkflowState).where(ContentWorkflowState.content_id == content.id))
    assert state.workflow_status == ContentWorkflowStatus.PENDING_REVIEW.value
    assert state.assigned_to_user_id is None


def test_operator_lists_auto_assigned_content(db_session):
    from fastapi.testclient import TestClient

    from intelligence_engine.db.session import get_db
    from intelligence_engine.main import create_app

    _employee, account = _seed_employee_account(db_session, user_id="operator-wang")
    content = _seed_content(db_session, account_id=account.id)

    app = create_app()

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    client.headers.update({"X-Role": "operator", "X-User-Id": "operator-wang"})

    response = client.get(
        "/api/intelligence/contents/product",
        params={"workflow_status": "assigned", "page": 1, "page_size": 20},
    )
    assert response.status_code == 200, response.text
    ids = {item["content_id"] for item in response.json()["items"]}
    assert content.id in ids


def test_operator_content_query_stays_scoped_to_assignee(db_session):
    _seed_employee_account(db_session, user_id="operator-other")
    _employee, account = _seed_employee_account(db_session, user_id="operator-wang")
    wang_content = _seed_content(db_session, account_id=account.id)

    job = JobRepository(db_session).create_job(job_type=JobType.SEARCH_COLLECT, payload={"keywords": ["SCI"]})
    candidate = FeedCandidateInput(
        platform=Platform.XHS,
        platform_content_id="pool-other-sci",
        canonical_url="https://www.xiaohongshu.com/explore/pool-other-sci",
        content_type=ContentType.IMAGE_TEXT,
        title_or_summary="SCI投稿经验-他人负责",
        author_name="作者",
        visible_like_count=10,
        source_surface=SourceSurface.SEARCH,
        feed_position=1,
        discovered_at=datetime.now(timezone.utc),
        raw_payload={"search_keyword": "SCI"},
    )
    other_content, *_ = ContentRepository(db_session).ingest_feed_candidate(
        job_id=job.id,
        account_id=None,
        candidate=candidate,
        enqueue_detail_job=False,
    )
    WorkflowRepository(db_session).assign(
        content_id=other_content.id,
        assigned_to_user_id="operator-other",
        assigned_by_user_id="supervisor-user",
        remark="主管分配",
    )
    db_session.commit()

    client = _client(db_session, role="operator", user_id="operator-wang")
    response = client.get("/api/intelligence/contents/product", params={"content_query": "SCI投稿"})
    assert response.status_code == 200, response.text
    ids = {item["content_id"] for item in response.json()["items"]}
    assert wang_content.id in ids
    assert other_content.id not in ids


def test_operator_sees_unassigned_content_discovered_by_owned_account(db_session):
    _employee, account = _seed_employee_account(db_session, user_id="operator-wang")
    content = _seed_content(db_session, account_id=account.id)
    state = db_session.scalar(select(ContentWorkflowState).where(ContentWorkflowState.content_id == content.id))
    assert state is not None
    state.assigned_to_user_id = None
    state.workflow_status = ContentWorkflowStatus.PENDING_REVIEW.value
    db_session.flush()

    client = _client(db_session, role="operator", user_id="operator-wang")
    response = client.get(
        "/api/intelligence/contents/product",
        params={"workflow_status": "pending_review,assigned,selected", "page": 1, "page_size": 50},
    )
    assert response.status_code == 200, response.text
    ids = {item["content_id"] for item in response.json()["items"]}
    assert content.id in ids
