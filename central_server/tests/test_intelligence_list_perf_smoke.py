import time

from fastapi.testclient import TestClient

from intelligence_engine.db.models import CandidateDecision, ContentDiscoveryEvent, ContentIdentity, ContentSnapshot, ContentWorkflowState, utcnow
from intelligence_engine.db.session import get_db
from intelligence_engine.domain.enums import CandidateBucket, ContentType, Platform, SourceSurface
from intelligence_engine.main import create_app


def _seed_many(db_session, count: int) -> None:
    now = utcnow()
    for index in range(count):
        content_id = f"perf-smoke-{index:04d}"
        if db_session.get(ContentIdentity, content_id):
            continue
        snapshot_id = f"perf-smoke-snapshot-{index:04d}"
        identity = ContentIdentity(
            id=content_id,
            platform=Platform.XHS.value,
            platform_content_id=f"perf-smoke-note-{index}",
            canonical_url=f"https://example.com/{index}",
            content_type=ContentType.IMAGE_TEXT.value,
            first_seen_at=now,
            last_seen_at=now,
            latest_snapshot_id=None,
            metadata_json={"visible_like_count": 80 + index, "manual_tags": ["perf"]},
        )
        db_session.add(identity)
        db_session.add(
            ContentSnapshot(
                id=snapshot_id,
                content_id=content_id,
                title=f"性能冒烟内容 {index}",
                body_text="论文 SCI 投稿",
                like_count=80 + index,
                comment_count=index % 20,
                fetched_at=now,
            )
        )
        identity.latest_snapshot_id = snapshot_id
        db_session.add(
            ContentDiscoveryEvent(
                id=f"perf-smoke-event-{index:04d}",
                content_id=content_id,
                platform=Platform.XHS.value,
                source_surface=SourceSurface.XHS_HOME_FEED.value,
                discovered_at=now,
                discovery_meta_json={"search_keyword": "SCI"},
            )
        )
        db_session.add(
            CandidateDecision(
                id=f"perf-smoke-decision-{index:04d}",
                content_id=content_id,
                snapshot_id=snapshot_id,
                business_keyword_hits_json=["论文"],
                lead_keyword_hits_json=[],
                comment_keyword_hits_json=[],
                like_threshold_hit=True,
                comment_threshold_hit=False,
                candidate_bucket=CandidateBucket.CONTENT_CANDIDATE.value,
                decision_reason_json={"seed": True},
                evaluated_at=now,
            )
        )
        db_session.add(
            ContentWorkflowState(
                id=f"perf-smoke-workflow-{index:04d}",
                content_id=content_id,
                workflow_status="pending_review",
            )
        )
    db_session.commit()


def _client(db_session) -> TestClient:
    app = create_app()

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    client.headers.update({"X-Role": "admin", "X-User-Id": "admin-user"})
    return client


def test_intelligence_product_list_p95_under_budget_for_seeded_pool(db_session):
    _seed_many(db_session, 150)
    client = _client(db_session)
    durations_ms: list[float] = []
    for _ in range(10):
        start = time.perf_counter()
        response = client.get(
            "/api/intelligence/contents/product",
            params={"page": 1, "page_size": 50, "sort_by": "latest_discovered_at", "sort_order": "desc"},
        )
        durations_ms.append((time.perf_counter() - start) * 1000)
        assert response.status_code == 200, response.text

    ordered = sorted(durations_ms)
    p95 = ordered[max(0, int(len(ordered) * 0.95) - 1)]
    assert p95 < 500, f"p95={p95:.1f}ms exceeds 500ms smoke budget"
