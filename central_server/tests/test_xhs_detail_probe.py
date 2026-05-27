from datetime import datetime, timezone

from fastapi.testclient import TestClient

from sqlalchemy import func, select

from intelligence_engine.db.models import ContentIdentity, ReferenceLibraryEvent, ReferenceLibraryItem
from intelligence_engine.db.session import get_db
from intelligence_engine.domain.enums import ContentType, JobType, Platform
from intelligence_engine.domain.schemas import DetailIngestionRequest, DetailSnapshotInput
from intelligence_engine.main import create_app
from intelligence_engine.storage.repositories.job_repository import JobRepository


def test_detail_ingestion_api_creates_snapshot_and_comment_job(db_session):
    app = create_app()

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    content = ContentIdentity(
        platform=Platform.XHS.value,
        platform_content_id="65abc123def4560001",
        canonical_url="https://www.xiaohongshu.com/explore/65abc123def4560001",
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
        },
    )
    snapshot = DetailSnapshotInput(
        title="SCI投稿经验：如何选择期刊",
        body_text="正文内容：期刊选择、投稿流程、发表周期。",
        author_platform_id="user001",
        author_name="作者A",
        like_count=12000,
        comment_count=88,
        collect_count=456,
        share_count=12,
        image_urls=["https://sns-img-qc.xhscdn.com/image-1.jpg"],
    )
    request = DetailIngestionRequest(job_id=job.id, content_id=content.id, snapshot=snapshot)

    response = TestClient(app).post("/api/ingestion/content-detail", json=request.model_dump(mode="json"))

    assert response.status_code == 200
    body = response.json()
    assert body["snapshot_id"]
    assert body["comment_job_enqueued"] is True
    assert db_session.get(ContentIdentity, content.id).latest_snapshot_id == body["snapshot_id"]
    item = db_session.scalar(select(ReferenceLibraryItem).where(ReferenceLibraryItem.content_id == content.id))
    assert item is not None
    assert item.library_type == "non_lead"
    assert item.rating == "good"
    assert item.selection_sources_json == ["ai"]


def test_detail_ingestion_auto_evaluation_is_idempotent_per_rule_version(db_session):
    app = create_app()

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    content = ContentIdentity(
        platform=Platform.XHS.value,
        platform_content_id="65abc123def4560002",
        canonical_url="https://www.xiaohongshu.com/explore/65abc123def4560002",
        content_type=ContentType.IMAGE_TEXT.value,
        first_seen_at=datetime.now(timezone.utc),
        last_seen_at=datetime.now(timezone.utc),
        metadata_json={},
    )
    db_session.add(content)
    db_session.flush()
    job = JobRepository(db_session).create_job(
        job_type=JobType.DETAIL_FETCH,
        payload={"content_id": content.id, "platform": Platform.XHS.value, "platform_content_id": content.platform_content_id},
    )
    snapshot = DetailSnapshotInput(title="SCI投稿经验", body_text="期刊投稿流程", like_count=600, comment_count=1)
    request = DetailIngestionRequest(job_id=job.id, content_id=content.id, snapshot=snapshot)
    client = TestClient(app)

    first = client.post("/api/ingestion/content-detail", json=request.model_dump(mode="json"))
    second = client.post("/api/ingestion/content-detail", json=request.model_dump(mode="json"))

    assert first.status_code == 200
    assert second.status_code == 200
    item = db_session.scalar(select(ReferenceLibraryItem).where(ReferenceLibraryItem.content_id == content.id))
    assert item is not None
    event_count = db_session.scalar(select(func.count(ReferenceLibraryEvent.id)).where(ReferenceLibraryEvent.library_item_id == item.id))
    assert event_count == 1
