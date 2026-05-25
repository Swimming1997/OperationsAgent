from datetime import datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from intelligence_engine.db.models import CommentSnapshot, ContentIdentity
from intelligence_engine.db.session import get_db
from intelligence_engine.domain.enums import ContentType, JobType, Platform
from intelligence_engine.domain.schemas import CommentIngestionRequest, CommentSnapshotInput
from intelligence_engine.main import create_app
from intelligence_engine.storage.repositories.job_repository import JobRepository


def test_comment_ingestion_api_writes_snapshots_and_keyword_hits(db_session):
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
        job_type=JobType.COMMENT_FETCH,
        payload={
            "content_id": content.id,
            "platform": Platform.XHS.value,
            "platform_content_id": content.platform_content_id,
        },
    )
    comments = [
        CommentSnapshotInput(
            platform_comment_id="c001",
            author_platform_id="u001",
            author_name="评论者A",
            body_text="求推荐，怎么联系？",
            like_count=12,
            created_time=datetime.now(timezone.utc),
        ),
        CommentSnapshotInput(
            platform_comment_id="c002",
            author_platform_id="u002",
            author_name="评论者B",
            body_text="已私信",
            like_count=1,
            created_time=datetime.now(timezone.utc),
        ),
    ]
    request = CommentIngestionRequest(job_id=job.id, content_id=content.id, comments=comments)

    response = TestClient(app).post("/api/ingestion/comments", json=request.model_dump(mode="json"))

    assert response.status_code == 200
    body = response.json()
    assert body["inserted"] == 2
    assert "求推荐" in body["lead_keyword_hits"]
    assert db_session.scalar(select(func.count(CommentSnapshot.id)).where(CommentSnapshot.content_id == content.id)) == 2
