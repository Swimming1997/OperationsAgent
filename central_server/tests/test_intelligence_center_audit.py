from pathlib import Path

from intelligence_engine.audit.intelligence_center_audit import (
    render_audit_markdown,
    run_intelligence_center_audit,
    write_audit_outputs,
)
from intelligence_engine.db.models import CommentSnapshot, ContentIdentity, ContentSnapshot, utcnow
from intelligence_engine.domain.enums import ContentType, JobType, Platform, SourceSurface
from intelligence_engine.domain.schemas import DetailSnapshotInput, FeedCandidateInput
from intelligence_engine.storage.repositories.content_repository import ContentRepository
from intelligence_engine.storage.repositories.job_repository import JobRepository


def _seed_search_content(db_session):
    job = JobRepository(db_session).create_job(job_type=JobType.SEARCH_COLLECT, payload={"keywords": ["SCI"]})
    candidate = FeedCandidateInput(
        platform=Platform.XHS,
        platform_content_id="audit-search-1",
        content_type=ContentType.IMAGE_TEXT,
        title_or_summary="SCI投稿",
        source_surface=SourceSurface.SEARCH,
        feed_position=1,
        discovered_at=utcnow(),
        raw_payload={
            "search_keyword": "SCI",
            "search_sort": "comprehensive",
            "note_type": "all",
            "publish_time": "all",
            "search_scope": "all",
            "location_filter": "all",
            "search_rank": 1,
            "requested_filter_context": {"search_sort": "comprehensive"},
            "applied_filter_context": None,
            "filter_apply_status": "not_implemented",
        },
    )
    content, _is_new, event, _detail, _prelim = ContentRepository(db_session).ingest_feed_candidate(
        job_id=job.id,
        account_id=None,
        candidate=candidate,
        enqueue_detail_job=False,
    )
    snapshot = ContentRepository(db_session).create_snapshot(
        content_id=content.id,
        account_id=None,
        snapshot=DetailSnapshotInput(title="SCI投稿", body_text="正文", raw_payload={"platform_tags": ["#SCI"]}),
    )
    content.latest_snapshot_id = snapshot.id
    db_session.add(
        CommentSnapshot(content_id=content.id, platform_comment_id="c-audit", body_text="评论", fetched_at=utcnow())
    )
    db_session.flush()
    return content, event


def test_audit_script_generates_outputs(db_session, tmp_path):
    _seed_search_content(db_session)
    report = run_intelligence_center_audit(db_session, window_hours=24)
    paths = write_audit_outputs(report, tmp_path)
    assert Path(paths["markdown"]).exists()
    assert Path(paths["json"]).exists()
    assert Path(paths["ndjson"]).exists()
    markdown = Path(paths["markdown"]).read_text(encoding="utf-8")
    assert "情报中心验收审计报告" in markdown
    assert report["pool_totals"]["content_identity_total"] >= 1
    assert "search_context" in report
    assert report["search_context"]["filter_context_note"]


def test_data_status_sample_validation(db_session):
    content, _event = _seed_search_content(db_session)
    report = run_intelligence_center_audit(db_session, window_hours=24)
    samples = report["data_status"]["sample_validation"]
    assert samples
    assert any(sample["content_id"] == content.id for sample in samples)
    assert report["data_status"]["distribution"].get("comments_ready", 0) >= 1


def test_audit_markdown_contains_checklist(db_session):
    report = run_intelligence_center_audit(db_session, window_hours=24)
    markdown = render_audit_markdown(report)
    assert "真实链路手工验收清单" in markdown
    assert "推荐页采集" in markdown
