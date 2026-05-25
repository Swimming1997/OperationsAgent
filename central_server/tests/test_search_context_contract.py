from intelligence_engine.domain.product_schemas import KeywordSearchTaskPayload
from intelligence_engine.domain.enums import Platform
from intelligence_engine.domain.intelligence_pool import build_discovery_meta_from_candidate
from intelligence_engine.storage.repositories.content_repository import ContentRepository
from intelligence_engine.storage.repositories.job_repository import JobRepository
from intelligence_engine.domain.enums import ContentType, JobType, Platform as PlatformEnum, SourceSurface
from intelligence_engine.domain.schemas import FeedCandidateInput
from intelligence_engine.db.models import ContentDiscoveryEvent, utcnow
from sqlalchemy import select


def test_keyword_search_payload_contract():
    payload = KeywordSearchTaskPayload(
        executor_account_id="account-1",
        platform=Platform.XHS,
        keywords=["SCI"],
        search_sort="latest",
        note_type="video",
        publish_time="one_week",
        search_scope="unviewed",
        location_filter="same_city",
        collect_suggestions_first=True,
    )
    dumped = payload.model_dump(mode="json")
    assert dumped["search_sort"] == "latest"
    assert dumped["note_type"] == "video"
    assert dumped["collect_suggestions_first"] is True


def test_discovery_meta_json_records_search_context(db_session):
    job = JobRepository(db_session).create_job(job_type=JobType.SEARCH_COLLECT, payload={"keywords": ["SCI"]})
    candidate = FeedCandidateInput(
        platform=PlatformEnum.XHS,
        platform_content_id="search-context-1",
        content_type=ContentType.IMAGE_TEXT,
        title_or_summary="SCI",
        source_surface=SourceSurface.SEARCH,
        feed_position=4,
        discovered_at=utcnow(),
        raw_payload={
            "search_keyword": "SCI",
            "core_keyword": "SCI",
            "search_sort": "comprehensive",
            "note_type": "all",
            "publish_time": "all",
            "search_scope": "all",
            "location_filter": "all",
            "search_rank": 4,
        },
    )
    _content, _is_new, event, _detail, _prelim = ContentRepository(db_session).ingest_feed_candidate(
        job_id=job.id,
        account_id=None,
        candidate=candidate,
        enqueue_detail_job=False,
    )
    meta = event.discovery_meta_json
    assert meta["search_keyword"] == "SCI"
    assert meta["search_rank"] == 4
    assert meta["search_sort"] == "comprehensive"
    assert build_discovery_meta_from_candidate(candidate.raw_payload, feed_position=4)["core_keyword"] == "SCI"
