from intelligence_engine.domain.enums import JobStatus, JobType, TaskRunTriggerType
from intelligence_engine.domain.job_priority import JobPriority, priority_for_task_run_trigger
from intelligence_engine.storage.repositories.job_repository import JobRepository


def test_manual_task_run_priority_is_higher_than_ingestion_jobs(db_session):
    repo = JobRepository(db_session)
    manual = repo.create_job(job_type=JobType.FEED_COLLECT, payload={"materialized_from_task": True}, priority=JobPriority.MANUAL_TASK_RUN)
    detail = repo.create_job(job_type=JobType.DETAIL_FETCH, payload={}, priority=JobPriority.INGESTION_ENRICHMENT)
    legacy = repo.create_job(job_type=JobType.FEED_COLLECT, payload={}, priority=JobPriority.LEGACY_BACKLOG)
    db_session.commit()

    claimed = repo.claim_jobs_for_agent(agent_id="agent-priority", supported_job_types=[JobType.FEED_COLLECT, JobType.DETAIL_FETCH], max_jobs=1, ttl_seconds=60)
    assert claimed[0].id == manual.id
    assert claimed[0].status == JobStatus.CLAIMED.value

    repo.mark_failed(claimed[0], error_code="test", error_message="done")
    db_session.commit()
    claimed2 = repo.claim_jobs_for_agent(agent_id="agent-priority", supported_job_types=[JobType.FEED_COLLECT, JobType.DETAIL_FETCH], max_jobs=1, ttl_seconds=60)
    assert claimed2[0].id == detail.id

    repo.mark_failed(claimed2[0], error_code="test", error_message="done")
    db_session.commit()
    claimed3 = repo.claim_jobs_for_agent(agent_id="agent-priority", supported_job_types=[JobType.FEED_COLLECT, JobType.DETAIL_FETCH], max_jobs=1, ttl_seconds=60)
    assert claimed3[0].id == legacy.id


def test_priority_for_task_run_trigger_values():
    assert priority_for_task_run_trigger(TaskRunTriggerType.MANUAL) == JobPriority.MANUAL_TASK_RUN
    assert priority_for_task_run_trigger(TaskRunTriggerType.SCHEDULED) == JobPriority.SCHEDULED_TASK_RUN
