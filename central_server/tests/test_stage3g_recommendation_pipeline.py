from datetime import datetime, timezone

from intelligence_engine.db.models import Job, TaskRun, TaskTemplate
from intelligence_engine.domain.enums import CandidateBucket, JobStatus, JobType, TaskRunStatus, TaskTemplateType
from intelligence_engine.domain.schemas import FeedCandidateInput
from intelligence_engine.services.task_materialization import TaskMaterializationService, summarize_jobs
from intelligence_engine.storage.repositories.content_repository import ContentRepository, sanitize_feed_author_name
from intelligence_engine.storage.repositories.job_repository import JobRepository


def _feed_candidate(**overrides):
    base = {
        "platform": "xhs",
        "platform_content_id": "note-001",
        "canonical_url": "https://www.xiaohongshu.com/explore/note-001",
        "content_type": "image_text",
        "title_or_summary": "SCI论文投稿经验",
        "cover_url": "https://example.com/cover.jpg",
        "author_name": "科研小白",
        "visible_like_count": 120,
        "source_surface": "xhs_home_feed",
        "feed_type": "xhs_home_feed",
        "feed_position": 1,
        "discovered_at": datetime.now(timezone.utc),
    }
    base.update(overrides)
    return FeedCandidateInput.model_validate(base)


def test_summarize_jobs_includes_prelim_counters():
    job = Job(job_type=JobType.FEED_COLLECT.value, status=JobStatus.SUCCESS.value, result_summary_json={})
    job.result_summary_json = {
        "raw_items_seen": 10,
        "unique_contents_inserted": 8,
        "prelim_pass_count": 3,
        "prelim_discard_count": 7,
        "detail_jobs_enqueued": 8,
    }
    summary = summarize_jobs([job])
    assert summary["feed_collect"]["prelim_pass_count"] == 3
    assert summary["feed_collect"]["prelim_discard_count"] == 7
    assert "预筛建议优先 3 条" in summary["feed_collect"]["message"]


def test_feed_collect_result_summary_reads_raw_items_seen():
    job = Job(job_type=JobType.FEED_COLLECT.value, status=JobStatus.SUCCESS.value, result_summary_json={})
    job.result_summary_json = {
        "raw_items_seen": 10,
        "unique_contents_inserted": 8,
        "detail_jobs_enqueued": 8,
    }
    summary = summarize_jobs([job])
    assert summary["feed_collect"]["sampled_count"] == 10
    assert summary["feed_collect"]["inserted_count"] == 8


def test_detail_fetch_inherits_task_run_and_blocks_early_success(db_session):
    template = TaskTemplate(
        name="推荐页巡检",
        template_type=TaskTemplateType.RECOMMENDATION_FEED_TASK.value,
        config_json={
            "executor_account_id": "acct-1",
            "feed_type": "xhs_home_feed",
            "target_count": 10,
            "refresh_rounds": 1,
            "per_round_scroll_target": 10,
        },
    )
    db_session.add(template)
    db_session.flush()

    run = TaskRun(task_template_id=template.id, trigger_type="manual", status=TaskRunStatus.MATERIALIZED.value)
    db_session.add(run)
    db_session.flush()

    feed_job = JobRepository(db_session).create_job(
        job_type=JobType.FEED_COLLECT,
        task_run_id=run.id,
        payload={"materialized_from_task": True, "target_count": 10},
        priority=10,
    )
    content_repo = ContentRepository(db_session)
    for index in range(2):
        content_repo.ingest_feed_candidate(
            job_id=feed_job.id,
            account_id=None,
            candidate=_feed_candidate(platform_content_id=f"note-{index}", title_or_summary="SCI paper journal"),
        )

    job_repo = JobRepository(db_session)
    job_repo.claim_jobs_for_agent(agent_id="agent-test", supported_job_types=[JobType.FEED_COLLECT], max_jobs=1, ttl_seconds=60)
    job_repo.mark_started(feed_job, agent_id="agent-test")
    job_repo.mark_success(
        feed_job,
        status=JobStatus.SUCCESS,
        result_summary={"raw_items_seen": 2, "unique_contents_inserted": 2, "detail_jobs_enqueued": 2},
    )

    from sqlalchemy import select

    detail_jobs = list(db_session.scalars(select(Job).where(Job.job_type == JobType.DETAIL_FETCH.value)))
    assert len(detail_jobs) == 2
    assert all(job.task_run_id == run.id for job in detail_jobs)

    service = TaskMaterializationService(db_session)
    service.refresh_task_run(run)
    assert run.status in {TaskRunStatus.QUEUED.value, TaskRunStatus.RUNNING.value}
    assert run.jobs_pending >= 2


def test_feed_prelim_deprioritizes_without_auto_detail_enqueue(db_session):
    feed_job = JobRepository(db_session).create_job(
        job_type=JobType.FEED_COLLECT,
        payload={"materialized_from_task": True},
        priority=10,
    )
    content_repo = ContentRepository(db_session)
    _content, _is_new, _event, detail_enqueued, prelim_pass = content_repo.ingest_feed_candidate(
        job_id=feed_job.id,
        account_id=None,
        candidate=_feed_candidate(
            platform_content_id="note-food",
            title_or_summary="today lunch ideas",
            visible_like_count=3,
        ),
    )
    assert detail_enqueued is False
    assert prelim_pass is False


def test_sanitize_feed_author_name_rejects_profile_nav_label():
    assert sanitize_feed_author_name("我") is None
    assert sanitize_feed_author_name("我的") is None
    assert sanitize_feed_author_name("科研作者") == "科研作者"
