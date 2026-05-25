from datetime import datetime, timezone

from fastapi.testclient import TestClient

from intelligence_engine.db.models import CommentSnapshot, ContentIdentity, ContentSnapshot, utcnow
from intelligence_engine.db.session import get_db
from intelligence_engine.domain.enums import ContentType, JobType, Platform, SourceSurface
from intelligence_engine.domain.schemas import FeedCandidateInput
from intelligence_engine.main import create_app
from intelligence_engine.domain.schemas import DetailSnapshotInput
from intelligence_engine.storage.repositories.content_repository import ContentRepository
from intelligence_engine.storage.repositories.job_repository import JobRepository
from intelligence_engine.storage.repositories.workflow_repository import WorkflowRepository


def _client(db_session) -> TestClient:
    app = create_app()

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    client.headers.update({"X-Role": "admin", "X-User-Id": "admin-user"})
    return client


def _seed_content(db_session):
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
    content, _is_new, _event, _detail, _prelim = repo.ingest_feed_candidate(job_id=job.id, account_id=None, candidate=candidate, enqueue_detail_job=False)
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
