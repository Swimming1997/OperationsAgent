from fastapi.testclient import TestClient
from sqlalchemy import select

from intelligence_engine.db.models import CandidateDecision, ContentIdentity, CreatorMonitorEvent, Job, KeywordRule, KeywordRuleSet, XhsSearchSuggestion
from intelligence_engine.db.session import get_db
from intelligence_engine.domain.enums import ContentType, FeedType, JobType, Platform, SessionStatus, SourceSurface
from intelligence_engine.domain.schemas import DetailSnapshotInput, FeedCandidateInput
from intelligence_engine.main import create_app
from intelligence_engine.storage.repositories.account_repository import AccountRepository
from intelligence_engine.storage.repositories.content_repository import ContentRepository
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


def test_unified_search_suggestions_ingestion_persists_platform(db_session):
    client = _client(db_session)
    payload = {
        "job_id": "job-dy-sug",
        "account_id": None,
        "platform": "douyin",
        "core_keyword": "SCI论文",
        "items": [
            {"core_keyword": "SCI论文", "suggested_keyword": "sci论文怎么写", "suggestion_rank": 1, "raw_payload": {"source": "search_sug_intercept"}, "fetched_at": "2026-06-13T08:00:00Z"},
            {"core_keyword": "SCI论文", "suggested_keyword": "sci论文辅导", "suggestion_rank": 2, "raw_payload": {}, "fetched_at": "2026-06-13T08:00:00Z"},
        ],
    }

    response = client.post("/api/ingestion/search-suggestions", json=payload)

    assert response.status_code == 200, response.text
    assert response.json()["inserted"] == 2
    db_session.expire_all()
    rows = list(db_session.scalars(select(XhsSearchSuggestion).where(XhsSearchSuggestion.core_keyword == "SCI论文")))
    assert len(rows) == 2
    assert {r.platform for r in rows} == {"douyin"}


def test_legacy_xhs_search_suggestions_endpoint_defaults_to_xhs(db_session):
    client = _client(db_session)
    payload = {
        "core_keyword": "考研复习",
        "items": [
            {"core_keyword": "考研复习", "suggested_keyword": "考研复习规划", "suggestion_rank": 1, "raw_payload": {}, "fetched_at": "2026-06-13T08:00:00Z"},
        ],
    }

    response = client.post("/api/ingestion/xhs-search-suggestions", json=payload)

    assert response.status_code == 200, response.text
    db_session.expire_all()
    row = db_session.scalar(select(XhsSearchSuggestion).where(XhsSearchSuggestion.core_keyword == "考研复习"))
    assert row is not None
    assert row.platform == "xhs"


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


def test_creator_monitor_duplicate_item_is_reevaluated_with_current_rule_set(db_session):
    client = _client(db_session)
    monitor = CreatorMonitorRepository(db_session).create_monitor(
        platform=Platform.XHS.value,
        creator_platform_id="creator-runtime",
        creator_display_name=None,
        monitor_group_key=None,
        mapped_business_account_type=None,
        check_interval_seconds=900,
    )
    rule_set = KeywordRuleSet(
        name="租房规则",
        rule_scope="intelligence",
        enabled=True,
        config_json={"visible_like_threshold": 999, "lead_intent_keywords": []},
    )
    db_session.add(rule_set)
    db_session.flush()
    db_session.add(KeywordRule(rule_set_id=rule_set.id, keyword="租房", normalized_keyword="租房", match_mode="contains", enabled=True, weight=1))
    existing_job = JobRepository(db_session).create_job(job_type=JobType.CREATOR_MONITOR, creator_monitor_id=monitor.id, payload={"creator_monitor_id": monitor.id, "platform": "xhs"})
    candidate_payload = {
        "platform": "xhs",
        "platform_content_id": "runtime-note-dup",
        "canonical_url": "https://www.xiaohongshu.com/explore/runtime-note-dup",
        "content_type": ContentType.IMAGE_TEXT.value,
        "title_or_summary": "杭州滨江租房转租",
        "source_surface": SourceSurface.CREATOR_MONITOR.value,
        "feed_type": FeedType.XHS_HOME_FEED.value,
        "feed_position": 1,
        "discovered_at": "2026-05-19T01:00:00Z",
        "raw_payload": {},
        "platform_context": {"note_id": "runtime-note-dup"},
    }
    repo = ContentRepository(db_session)
    content, _is_new, _event, _detail_enqueued, _prelim = repo.ingest_feed_candidate(
        job_id=existing_job.id,
        account_id=None,
        candidate=FeedCandidateInput(**candidate_payload),
        enqueue_detail_job=True,
    )
    snapshot = repo.create_snapshot(
        content_id=content.id,
        account_id=None,
        snapshot=DetailSnapshotInput(title="杭州滨江租房转租", body_text="个人转租"),
    )
    repo.evaluate_candidate(content_id=content.id, snapshot_id=snapshot.id)
    current_job = JobRepository(db_session).create_job(
        job_type=JobType.CREATOR_MONITOR,
        creator_monitor_id=monitor.id,
        payload={"creator_monitor_id": monitor.id, "platform": "xhs", "rule_set_id": rule_set.id},
    )
    db_session.commit()

    response = client.post(
        "/api/ingestion/creator-monitor-items",
        json={
            "job_id": current_job.id,
            "creator_monitor_id": monitor.id,
            "items": [candidate_payload],
            "raw_payload": {},
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["new_content_count"] == 0
    assert body["duplicate_content_count"] == 1
    assert body["detail_job_enqueue_count"] == 0
    latest_decision = db_session.scalar(
        select(CandidateDecision)
        .where(CandidateDecision.content_id == content.id)
        .order_by(CandidateDecision.evaluated_at.desc(), CandidateDecision.created_at.desc())
    )
    assert latest_decision is not None
    assert latest_decision.business_keyword_hits_json == ["租房"]
    assert latest_decision.candidate_bucket == "pending_enrichment"
