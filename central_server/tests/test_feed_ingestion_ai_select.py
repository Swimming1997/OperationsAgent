from fastapi.testclient import TestClient

from intelligence_engine.db.session import get_db
from intelligence_engine.domain.enums import ContentType, JobType, Platform, SourceSurface
from intelligence_engine.domain.schemas import FeedCandidateInput
from intelligence_engine.main import create_app
from intelligence_engine.services.rule_profile import RuleProfileService
from intelligence_engine.storage.repositories.job_repository import JobRepository
from intelligence_engine.storage.repositories.reference_library_repository import ReferenceLibraryRepository


def _client(db_session) -> TestClient:
    app = create_app()

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    client.headers.update({"X-Role": "admin", "X-User-Id": "admin-user"})
    return client


def test_feed_ingestion_triggers_ai_select_after_commit(db_session):
    RuleProfileService(db_session).ensure_defaults(created_by_user_id="admin-user")
    job = JobRepository(db_session).create_job(
        job_type=JobType.FEED_COLLECT,
        payload={"materialized_from_task": True, "target_count": 10},
    )
    db_session.commit()
    client = _client(db_session)
    response = client.post(
        "/api/ingestion/feed-candidates",
        json={
            "job_id": job.id,
            "account_id": None,
            "candidates": [
                {
                    "platform": Platform.XHS.value,
                    "platform_content_id": "feed-ai-select-1",
                    "canonical_url": "https://www.xiaohongshu.com/explore/feed-ai-select-1",
                    "content_type": ContentType.IMAGE_TEXT.value,
                    "title_or_summary": "求推 论文投稿",
                    "author_name": "作者",
                    "visible_like_count": 200,
                    "source_surface": SourceSurface.XHS_HOME_FEED.value,
                    "feed_position": 1,
                    "discovered_at": "2026-05-26T00:00:00Z",
                    "raw_payload": {},
                }
            ],
        },
    )
    assert response.status_code == 200, response.text
    content_id = response.json()["results"][0]["content_id"]
    db_session.commit()
    item = ReferenceLibraryRepository(db_session).get_active_item(content_id=content_id)
    assert item is not None
    assert "ai" in (item.selection_sources_json or [])
    assert (item.metadata_json or {}).get("trigger_source") == "feed_ingestion"
