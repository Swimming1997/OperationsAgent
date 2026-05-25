from intelligence_engine.config import get_settings
from intelligence_engine.domain.enums import CandidateBucket, JobType, Platform, SourceSurface
from intelligence_engine.domain.schemas import FeedCandidateInput
from intelligence_engine.services.enrichment_policy import should_enqueue_comment_fetch, should_enqueue_detail_fetch
from intelligence_engine.storage.repositories.content_repository import ContentRepository
from intelligence_engine.storage.repositories.job_repository import JobRepository
from intelligence_engine.domain.enums import ContentType
from intelligence_engine.db.models import utcnow


def test_detail_policy_candidate_only_blocks_low_signal(db_session, monkeypatch):
    monkeypatch.setenv("INTEL_ENGINE_ENQUEUE_DETAIL_POLICY", "candidate_only")
    get_settings.cache_clear()
    candidate = FeedCandidateInput(
        platform=Platform.XHS,
        platform_content_id="policy-1",
        content_type=ContentType.IMAGE_TEXT,
        title_or_summary="无关内容",
        visible_like_count=1,
        source_surface=SourceSurface.XHS_HOME_FEED,
        discovered_at=utcnow(),
        raw_payload={},
    )
    assert should_enqueue_detail_fetch(candidate=candidate, is_new=True, feed_prelim_pass=False, parent_job_type=JobType.FEED_COLLECT.value) is False


def test_detail_policy_manual_enqueue(db_session):
    candidate = FeedCandidateInput(
        platform=Platform.XHS,
        platform_content_id="policy-2",
        content_type=ContentType.IMAGE_TEXT,
        title_or_summary="SCI",
        visible_like_count=1,
        source_surface=SourceSurface.SEARCH,
        discovered_at=utcnow(),
        raw_payload={"search_rank": 99},
    )
    assert should_enqueue_detail_fetch(candidate=candidate, is_new=False, feed_prelim_pass=None, parent_job_type=None, manual=True) is True


def test_comment_policy_high_comment_only(db_session, monkeypatch):
    monkeypatch.setenv("INTEL_ENGINE_ENQUEUE_COMMENT_POLICY", "high_comment_only")
    monkeypatch.setenv("INTEL_ENGINE_COMMENT_AUTO_COUNT_THRESHOLD", "10")
    get_settings.cache_clear()
    assert should_enqueue_comment_fetch(comment_count=20) is True
    assert should_enqueue_comment_fetch(comment_count=2) is False


def test_ingest_feed_candidate_respects_default_policy(db_session, monkeypatch):
    monkeypatch.setenv("INTEL_ENGINE_ENQUEUE_DETAIL_POLICY", "manual_only")
    get_settings.cache_clear()
    job = JobRepository(db_session).create_job(job_type=JobType.FEED_COLLECT, payload={})
    candidate = FeedCandidateInput(
        platform=Platform.XHS,
        platform_content_id="policy-3",
        content_type=ContentType.IMAGE_TEXT,
        title_or_summary="SCI论文",
        visible_like_count=100,
        source_surface=SourceSurface.SEARCH,
        discovered_at=utcnow(),
        raw_payload={"search_rank": 1},
    )
    _content, _is_new, _event, detail_enqueued, _prelim = ContentRepository(db_session).ingest_feed_candidate(
        job_id=job.id,
        account_id=None,
        candidate=candidate,
    )
    assert detail_enqueued is False
