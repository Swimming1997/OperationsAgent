from fastapi.testclient import TestClient
from sqlalchemy import select

from intelligence_engine.db.models import ContentIdentity, CreatorMonitorEvent, Job
from intelligence_engine.db.session import get_db
from intelligence_engine.domain.enums import ContentType, FeedType, JobType, Platform, SessionStatus, SourceSurface
from intelligence_engine.main import create_app
from intelligence_engine.storage.repositories.account_repository import AccountRepository
from intelligence_engine.storage.repositories.creator_repository import CreatorMonitorRepository
from intelligence_engine.storage.repositories.job_repository import JobRepository


def _client(db_session) -> TestClient:
    app = create_app()

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)


def test_ready_account_session_query_for_local_agent(db_session):
    client = _client(db_session)
    account_repo = AccountRepository(db_session)
    agent = account_repo.register_agent(employee_id=None, device_name="pc", machine_fingerprint="runtime-api-agent", agent_version="0.1.0", capabilities={})
    account = account_repo.create_account(employee_id=None, platform=Platform.XHS.value, display_name="xhs", external_account_id=None, business_account_type=None, default_agent_id=agent.id, metadata={})
    account_repo.create_session(
        account=account,
        local_agent_id=agent.id,
        session_type="browser",
        profile_ref=None,
        cookie_ref=None,
        status=SessionStatus.READY.value,
        session_meta={"cdp_url": "http://127.0.0.1:9222"},
    )
    db_session.commit()

    response = client.get(f"/api/accounts/{account.id}/sessions/ready", params={"local_agent_id": agent.id})

    assert response.status_code == 200
    assert response.json()["session_meta"]["cdp_url"] == "http://127.0.0.1:9222"


def test_creator_monitor_items_ingestion_writes_events_and_detail_job(db_session):
    client = _client(db_session)
    monitor = CreatorMonitorRepository(db_session).create_monitor(
        platform=Platform.XHS.value,
        creator_platform_id="creator-runtime",
        creator_display_name=None,
        monitor_group_key=None,
        mapped_business_account_type=None,
        check_interval_seconds=900,
    )
    job = JobRepository(db_session).create_job(
        job_type=JobType.CREATOR_MONITOR,
        creator_monitor_id=monitor.id,
        payload={"creator_monitor_id": monitor.id, "platform": "xhs"},
    )
    db_session.commit()
    payload = {
        "job_id": job.id,
        "creator_monitor_id": monitor.id,
        "creator_display_name": "Creator A",
        "items": [
            {
                "platform": "xhs",
                "platform_content_id": "runtime-note-1",
                "canonical_url": "https://www.xiaohongshu.com/explore/runtime-note-1?xsec_token=t&xsec_source=pc_feed",
                "content_type": ContentType.IMAGE_TEXT.value,
                "title_or_summary": "SCI 投稿经验",
                "source_surface": SourceSurface.CREATOR_MONITOR.value,
                "feed_type": FeedType.XHS_HOME_FEED.value,
                "feed_position": 1,
                "discovered_at": "2026-05-19T01:00:00Z",
                "raw_payload": {},
                "platform_context": {"note_id": "runtime-note-1", "xsec_token": "t", "xsec_source": "pc_feed"},
            }
        ],
    }

    response = client.post("/api/ingestion/creator-monitor-items", json=payload)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["items_seen"] == 1
    assert body["new_content_count"] == 1
    assert body["detail_job_enqueue_count"] == 1
    db_session.expire_all()
    content = db_session.scalar(select(ContentIdentity).where(ContentIdentity.platform_content_id == "runtime-note-1"))
    assert content is not None
    assert db_session.scalar(select(CreatorMonitorEvent).where(CreatorMonitorEvent.content_id == content.id)) is not None
    detail_job = next(
        job
        for job in db_session.scalars(select(Job).where(Job.job_type == JobType.DETAIL_FETCH.value))
        if job.payload_json.get("content_id") == content.id
    )
    assert detail_job is not None
    assert detail_job.payload_json["platform_context"]["xsec_token"] == "t"
