from datetime import datetime, timezone

from sqlalchemy import func, select

from intelligence_engine.db.models import ContentIdentity, CreatorMonitorEvent, Job
from intelligence_engine.domain.enums import ContentType, FeedType, JobType, Platform, SourceSurface
from intelligence_engine.domain.schemas import FeedCandidateInput
from intelligence_engine.storage.repositories.content_repository import ContentRepository
from intelligence_engine.storage.repositories.creator_repository import CreatorMonitorRepository


def test_creator_monitor_dedup_and_new_content_event(db_session):
    creator_repo = CreatorMonitorRepository(db_session)
    monitor = creator_repo.create_monitor(
        platform=Platform.XHS.value,
        creator_platform_id="5eb8e1d400000000010075ae",
        creator_display_name="creator",
        monitor_group_key=None,
        mapped_business_account_type=None,
        check_interval_seconds=900,
    )
    monitor_job = Job(
        job_type=JobType.CREATOR_MONITOR.value,
        status="pending",
        creator_monitor_id=monitor.id,
        payload_json={},
        checkpoint_json={},
        result_summary_json={},
    )
    db_session.add(monitor_job)
    db_session.flush()
    candidate = FeedCandidateInput(
        platform=Platform.XHS,
        platform_content_id="66fad51c000000001b0224b8",
        canonical_url="https://www.xiaohongshu.com/explore/66fad51c000000001b0224b8?xsec_token=NOTE_TOKEN&xsec_source=pc_feed",
        content_type=ContentType.IMAGE_TEXT,
        title_or_summary="SCI 投稿经验",
        source_surface=SourceSurface.CREATOR_MONITOR,
        feed_type=FeedType.XHS_HOME_FEED,
        feed_position=1,
        discovered_at=datetime.now(timezone.utc),
        platform_context={
            "note_id": "66fad51c000000001b0224b8",
            "xsec_token": "NOTE_TOKEN",
            "xsec_source": "pc_feed",
            "has_xsec_context": True,
        },
    )

    content_repo = ContentRepository(db_session)
    content, is_new, _event, detail_enqueued, _prelim = content_repo.ingest_feed_candidate(
        job_id=monitor_job.id,
        account_id=None,
        candidate=candidate,
        enqueue_detail_job=True,
    )
    if is_new:
        creator_repo.add_event(
            monitor_id=monitor.id,
            content_id=content.id,
            event_type="new_content_detected",
            payload={"platform_content_id": content.platform_content_id},
        )
    second_content, second_is_new, _second_event, second_detail_enqueued, _prelim2 = content_repo.ingest_feed_candidate(
        job_id=monitor_job.id,
        account_id=None,
        candidate=candidate,
        enqueue_detail_job=True,
    )

    assert is_new is True
    assert detail_enqueued is True
    assert second_content.id == content.id
    assert second_is_new is False
    assert second_detail_enqueued is False
    assert db_session.scalar(select(func.count(ContentIdentity.id))) == 1
    assert db_session.scalar(select(func.count(Job.id)).where(Job.job_type == JobType.DETAIL_FETCH.value)) == 1
    assert db_session.scalar(select(func.count(CreatorMonitorEvent.id)).where(CreatorMonitorEvent.event_type == "new_content_detected")) == 1
