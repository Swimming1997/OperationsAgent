from datetime import datetime, timezone

from fastapi.testclient import TestClient

from intelligence_engine.api.routes import get_settings
from intelligence_engine.domain.xhs_context import (
    build_xhs_note_url,
    parse_xhs_note_context,
    url_has_xsec_context,
)
from intelligence_engine.db.models import ContentIdentity, Job
from intelligence_engine.db.session import get_db
from intelligence_engine.domain.enums import ContentType, FeedType, JobType, Platform, SourceSurface
from intelligence_engine.domain.schemas import DetailIngestionRequest, FeedCandidateIngestionRequest, FeedCandidateInput
from intelligence_engine.main import create_app
from intelligence_engine.storage.repositories.content_repository import ContentRepository
from intelligence_engine.storage.repositories.job_repository import JobRepository


FULL_XHS_URL = (
    "https://www.xiaohongshu.com/explore/69f5b80a000000003701d4a1"
    "?xsec_token=ABmMrqaue5oUcxMMprm6lAbvciTOw8BoyPYnWKkzWJE10%3D"
    "&xsec_source=pc_feed"
)


def test_parse_xhs_note_context_from_full_url():
    context = parse_xhs_note_context(FULL_XHS_URL)

    assert context is not None
    assert context.note_id == "69f5b80a000000003701d4a1"
    assert context.xsec_source == "pc_feed"
    assert context.xsec_token.startswith("ABmMrq")
    assert context.has_xsec_context is True
    assert url_has_xsec_context(FULL_XHS_URL) is True


def test_build_xhs_note_url_preserves_xsec_context():
    built = build_xhs_note_url(
        {
            "note_id": "69f5b80a000000003701d4a1",
            "xsec_token": "TOKEN",
            "xsec_source": "pc_feed",
        }
    )
    assert built == (
        "https://www.xiaohongshu.com/explore/69f5b80a000000003701d4a1"
        "?xsec_token=TOKEN&xsec_source=pc_feed"
    )


def test_ingest_candidate_enqueues_detail_job_with_xhs_context(db_session):
    job = JobRepository(db_session).create_job(job_type=JobType.FEED_COLLECT, payload={})
    candidate = FeedCandidateInput(
        platform=Platform.XHS,
        platform_content_id="69f5b80a000000003701d4a1",
        canonical_url=FULL_XHS_URL,
        content_type=ContentType.IMAGE_TEXT,
        title_or_summary="SCI论文测试",
        source_surface=SourceSurface.XHS_HOME_FEED,
        feed_type=FeedType.XHS_HOME_FEED,
        feed_position=1,
        visible_like_count=120,
        discovered_at=datetime.now(timezone.utc),
        platform_context={
            "note_id": "69f5b80a000000003701d4a1",
            "xsec_token": "TOKEN",
            "xsec_source": "pc_feed",
            "has_xsec_context": True,
        },
    )

    content, _, _, detail_enqueued, _prelim = ContentRepository(db_session).ingest_feed_candidate(
        job_id=job.id,
        account_id=None,
        candidate=candidate,
    )
    detail_job = db_session.query(Job).filter(Job.job_type == JobType.DETAIL_FETCH.value).one()

    assert detail_enqueued is True
    assert content.metadata_json["platform_context"]["xsec_source"] == "pc_feed"
    assert detail_job.payload_json["canonical_url"] == FULL_XHS_URL
    assert detail_job.payload_json["platform_context"]["xsec_token"] == "TOKEN"
    assert detail_job.payload_json["platform_context"]["xsec_source"] == "pc_feed"
    assert detail_job.payload_json["platform_context"]["note_id"] == "69f5b80a000000003701d4a1"


def test_feed_candidate_ingestion_api_enqueues_detail_job_with_complete_xhs_context(db_session):
    app = create_app()

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    job = JobRepository(db_session).create_job(job_type=JobType.FEED_COLLECT, payload={})
    candidate = FeedCandidateInput(
        platform=Platform.XHS,
        platform_content_id="69f5b80a000000003701d4a1",
        canonical_url=FULL_XHS_URL,
        content_type=ContentType.IMAGE_TEXT,
        title_or_summary="SCI论文测试",
        source_surface=SourceSurface.XHS_HOME_FEED,
        feed_type=FeedType.XHS_HOME_FEED,
        feed_position=1,
        visible_like_count=120,
        discovered_at=datetime.now(timezone.utc),
        platform_context={
            "note_id": "69f5b80a000000003701d4a1",
            "xsec_token": "TOKEN",
            "xsec_source": "pc_feed",
            "has_xsec_context": True,
        },
    )
    request = FeedCandidateIngestionRequest(job_id=job.id, account_id=None, candidates=[candidate])

    response = TestClient(app).post("/api/ingestion/feed-candidates", json=request.model_dump(mode="json"))

    assert response.status_code == 200
    detail_job = db_session.query(Job).filter(Job.job_type == JobType.DETAIL_FETCH.value).one()
    assert detail_job.payload_json["canonical_url"] == FULL_XHS_URL
    assert detail_job.payload_json["platform_context"] == {
        "note_id": "69f5b80a000000003701d4a1",
        "xsec_token": "TOKEN",
        "xsec_source": "pc_feed",
        "has_xsec_context": True,
    }


def test_detail_ingestion_enqueues_comment_job_with_context(db_session):
    app = create_app()

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    content = ContentIdentity(
        platform=Platform.XHS.value,
        platform_content_id="69f5b80a000000003701d4a1",
        canonical_url=FULL_XHS_URL,
        content_type=ContentType.IMAGE_TEXT.value,
        first_seen_at=datetime.now(timezone.utc),
        last_seen_at=datetime.now(timezone.utc),
        metadata_json={
            "platform_context": {
                "note_id": "69f5b80a000000003701d4a1",
                "xsec_token": "TOKEN",
                "xsec_source": "pc_feed",
                "has_xsec_context": True,
            }
        },
    )
    db_session.add(content)
    db_session.flush()
    job = JobRepository(db_session).create_job(
        job_type=JobType.DETAIL_FETCH,
        account_id=None,
        payload={
            "content_id": content.id,
            "platform": Platform.XHS.value,
            "platform_content_id": content.platform_content_id,
            "canonical_url": FULL_XHS_URL,
            "platform_context": content.metadata_json["platform_context"],
        },
    )
    request = DetailIngestionRequest(
        job_id=job.id,
        content_id=content.id,
        snapshot={
            "title": "标题",
            "body_text": "正文",
            "comment_count": 20,
            "raw_payload": {},
        },
    )
    response = TestClient(app).post("/api/ingestion/content-detail", json=request.model_dump(mode="json"))

    assert response.status_code == 200
    comment_job = db_session.query(Job).filter(Job.job_type == JobType.COMMENT_FETCH.value).one()
    assert comment_job.payload_json["canonical_url"] == FULL_XHS_URL
    assert comment_job.payload_json["platform_context"]["xsec_token"] == "TOKEN"
    assert comment_job.payload_json["platform_context"]["xsec_source"] == "pc_feed"
    assert comment_job.payload_json["platform_context"]["note_id"] == "69f5b80a000000003701d4a1"


def test_detail_ingestion_inherits_xhs_context_from_detail_job_payload_when_content_metadata_is_empty(db_session):
    app = create_app()

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    content = ContentIdentity(
        platform=Platform.XHS.value,
        platform_content_id="69f5b80a000000003701d4a1",
        canonical_url="https://www.xiaohongshu.com/explore/69f5b80a000000003701d4a1",
        content_type=ContentType.IMAGE_TEXT.value,
        first_seen_at=datetime.now(timezone.utc),
        last_seen_at=datetime.now(timezone.utc),
        metadata_json={},
    )
    db_session.add(content)
    db_session.flush()
    job = JobRepository(db_session).create_job(
        job_type=JobType.DETAIL_FETCH,
        account_id=None,
        payload={
            "content_id": content.id,
            "platform": Platform.XHS.value,
            "platform_content_id": content.platform_content_id,
            "canonical_url": FULL_XHS_URL,
            "platform_context": {
                "note_id": "69f5b80a000000003701d4a1",
                "xsec_token": "TOKEN",
                "xsec_source": "pc_feed",
                "has_xsec_context": True,
            },
        },
    )
    request = DetailIngestionRequest(
        job_id=job.id,
        content_id=content.id,
        snapshot={
            "title": "标题",
            "body_text": "正文",
            "comment_count": 20,
            "raw_payload": {},
        },
    )

    response = TestClient(app).post("/api/ingestion/content-detail", json=request.model_dump(mode="json"))

    assert response.status_code == 200
    comment_job = db_session.query(Job).filter(Job.job_type == JobType.COMMENT_FETCH.value).one()
    assert comment_job.payload_json["canonical_url"] == FULL_XHS_URL
    assert comment_job.payload_json["platform_context"] == {
        "note_id": "69f5b80a000000003701d4a1",
        "xsec_token": "TOKEN",
        "xsec_source": "pc_feed",
        "has_xsec_context": True,
    }
