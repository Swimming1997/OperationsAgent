from intelligence_engine.audit.intelligence_center_audit import audit_search_context_integrity
from intelligence_engine.domain.enums import ContentType, JobType, Platform, SourceSurface
from intelligence_engine.domain.schemas import FeedCandidateInput
from intelligence_engine.storage.repositories.content_repository import ContentRepository
from intelligence_engine.storage.repositories.job_repository import JobRepository
from intelligence_engine.db.models import utcnow


def test_search_filter_context_fields_persisted_to_discovery_meta(db_session):
    job = JobRepository(db_session).create_job(job_type=JobType.SEARCH_COLLECT, payload={})
    candidate = FeedCandidateInput(
        platform=Platform.XHS,
        platform_content_id="filter-ctx-1",
        content_type=ContentType.IMAGE_TEXT,
        title_or_summary="SCI",
        source_surface=SourceSurface.SEARCH,
        feed_position=2,
        discovered_at=utcnow(),
        raw_payload={
            "search_keyword": "医学",
            "search_sort": "most_liked",
            "note_type": "image_text",
            "publish_time": "half_year",
            "search_scope": "all",
            "location_filter": "all",
            "search_rank": 2,
            "requested_filter_context": {
                "search_sort": "most_liked",
                "note_type": "image_text",
                "publish_time": "half_year",
                "search_scope": "all",
                "location_filter": "all",
            },
            "applied_filter_context": None,
            "filter_apply_status": "not_implemented",
        },
    )
    _content, _is_new, event, _detail, _prelim = ContentRepository(db_session).ingest_feed_candidate(
        job_id=job.id,
        account_id=None,
        candidate=candidate,
        enqueue_detail_job=False,
    )
    meta = event.discovery_meta_json
    assert meta["search_keyword"] == "医学"
    assert meta["search_sort"] == "most_liked"
    assert meta["filter_apply_status"] == "not_implemented"
    report = audit_search_context_integrity(db_session)
    assert report["search_content_total"] >= 1
    keyword_row = next(row for row in report["field_stats"] if row["field"] == "search_keyword")
    assert keyword_row["non_empty_count"] >= 1
    assert report["filter_apply_status_counts"].get("not_implemented", 0) >= 1
