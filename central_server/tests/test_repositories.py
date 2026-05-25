from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select

from intelligence_engine.db.models import ContentDiscoveryEvent, Job
from intelligence_engine.domain.enums import (
    AccountStatus,
    ContentType,
    FeedType,
    JobStatus,
    JobType,
    LeaseResourceType,
    ErrorCode,
    Platform,
    SourceSurface,
)
from intelligence_engine.domain.schemas import DetailSnapshotInput, FeedCandidateInput
from intelligence_engine.storage.repositories.account_repository import AccountRepository
from intelligence_engine.storage.repositories.content_repository import ContentRepository
from intelligence_engine.storage.repositories.job_repository import JobRepository
from intelligence_engine.storage.repositories.lease_repository import LeaseRepository


def test_account_agent_job_claim_and_requeue(db_session):
    account_repo = AccountRepository(db_session)
    agent = account_repo.register_agent(
        employee_id=None,
        device_name="test-agent",
        machine_fingerprint="test-fp",
        agent_version="0.1.0",
        capabilities={"platforms": ["xhs"]},
    )
    account = account_repo.create_account(
        employee_id=None,
        platform=Platform.XHS.value,
        display_name="xhs-account",
        external_account_id=None,
        business_account_type=None,
        default_agent_id=agent.id,
        metadata={},
    )
    job_repo = JobRepository(db_session)
    job_repo.create_job(
        job_type=JobType.FEED_COLLECT,
        account_id=account.id,
        local_agent_id=agent.id,
        payload={"feed_type": FeedType.XHS_HOME_FEED.value},
    )
    claimed = job_repo.claim_jobs_for_agent(
        agent_id=agent.id,
        supported_job_types=[JobType.FEED_COLLECT],
        max_jobs=1,
        ttl_seconds=300,
    )
    assert len(claimed) == 1
    assert claimed[0].status == JobStatus.CLAIMED.value


def test_content_dedup_enqueues_detail_only_once(db_session):
    job = JobRepository(db_session).create_job(job_type=JobType.FEED_COLLECT, payload={})
    candidate = FeedCandidateInput(
        platform=Platform.XHS,
        platform_content_id="same-id",
        canonical_url="https://fake.local/same-id",
        content_type=ContentType.IMAGE_TEXT,
        title_or_summary="SCI论文投稿",
        source_surface=SourceSurface.XHS_HOME_FEED,
        feed_type=FeedType.XHS_HOME_FEED,
        feed_position=1,
        visible_like_count=120,
        discovered_at=datetime.now(timezone.utc),
    )
    repo = ContentRepository(db_session)
    _, is_new_1, _, detail_job_1, _ = repo.ingest_feed_candidate(job_id=job.id, account_id=None, candidate=candidate)
    _, is_new_2, _, detail_job_2, _ = repo.ingest_feed_candidate(job_id=job.id, account_id=None, candidate=candidate)

    assert is_new_1 is True
    assert is_new_2 is False
    assert detail_job_1 is True
    assert detail_job_2 is False


def test_fetch_lease_allows_single_active_owner(db_session):
    job = JobRepository(db_session).create_job(job_type=JobType.DETAIL_FETCH, payload={})
    lease_repo = LeaseRepository(db_session)

    first = lease_repo.try_acquire(
        resource_type=LeaseResourceType.DETAIL_FETCH,
        resource_key="detail:xhs:content-1",
        owner_job_id=job.id,
        ttl_seconds=300,
    )
    second = lease_repo.try_acquire(
        resource_type=LeaseResourceType.DETAIL_FETCH,
        resource_key="detail:xhs:content-1",
        owner_job_id=job.id,
        ttl_seconds=300,
    )

    assert first is not None
    assert second is None

    lease_repo.release(first)
    third = lease_repo.try_acquire(
        resource_type=LeaseResourceType.DETAIL_FETCH,
        resource_key="detail:xhs:content-1",
        owner_job_id=job.id,
        ttl_seconds=300,
    )

    assert third is not None


def test_fetch_lease_expire_stale_allows_reacquire(db_session):
    job = JobRepository(db_session).create_job(job_type=JobType.DETAIL_FETCH, payload={})
    lease_repo = LeaseRepository(db_session)
    first = lease_repo.try_acquire(
        resource_type=LeaseResourceType.DETAIL_FETCH,
        resource_key="detail:xhs:expired-content",
        owner_job_id=job.id,
        ttl_seconds=300,
    )
    first.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    expired = lease_repo.expire_stale_leases()
    second = lease_repo.try_acquire(
        resource_type=LeaseResourceType.DETAIL_FETCH,
        resource_key="detail:xhs:expired-content",
        owner_job_id=job.id,
        ttl_seconds=300,
    )

    assert expired == 1
    assert first.status == "expired"
    assert second is not None


def test_claim_expiry_requeues_and_allows_reclaim(db_session):
    job_repo = JobRepository(db_session)
    job = job_repo.create_job(job_type=JobType.FEED_COLLECT, payload={})
    claimed = job_repo.claim_jobs_for_agent(
        agent_id="agent-a",
        supported_job_types=[JobType.FEED_COLLECT],
        max_jobs=1,
        ttl_seconds=1,
    )[0]
    claimed.claim_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)

    requeued = job_repo.requeue_expired_claims()
    reclaimed = job_repo.claim_jobs_for_agent(
        agent_id="agent-b",
        supported_job_types=[JobType.FEED_COLLECT],
        max_jobs=1,
        ttl_seconds=300,
    )

    assert requeued == 1
    assert job.status == JobStatus.CLAIMED.value
    assert reclaimed[0].id == job.id
    assert reclaimed[0].claimed_by_agent_id == "agent-b"


def test_resume_failed_paused_and_partial_success_checkpoint(db_session):
    job_repo = JobRepository(db_session)
    failed = job_repo.create_job(job_type=JobType.DETAIL_FETCH, payload={}, checkpoint={"cursor": "a"})
    failed.status = JobStatus.CLAIMED.value
    job_repo.mark_started(failed, agent_id="agent-a")
    job_repo.mark_failed(
        failed,
        error_code=ErrorCode.RETRYABLE_NETWORK_ERROR.value,
        error_message="temporary",
        checkpoint={"cursor": "b"},
    )
    job_repo.resume(failed)

    paused = job_repo.create_job(job_type=JobType.FEED_COLLECT, payload={}, checkpoint={"items_seen": 3})
    job_repo.pause(paused)
    job_repo.resume(paused)

    partial = job_repo.create_job(job_type=JobType.COMMENT_FETCH, payload={}, checkpoint={"cursor": "page-2"})
    partial.status = JobStatus.CLAIMED.value
    job_repo.mark_started(partial, agent_id="agent-a")
    job_repo.mark_success(partial, status=JobStatus.PARTIAL_SUCCESS, result_summary={"lease_conflict": True})

    assert failed.status == JobStatus.PENDING.value
    assert failed.checkpoint_json == {"cursor": "b"}
    assert paused.status == JobStatus.PENDING.value
    assert paused.checkpoint_json == {"items_seen": 3}
    assert partial.status == JobStatus.PARTIAL_SUCCESS.value
    assert partial.checkpoint_json == {"cursor": "page-2"}


def test_duplicate_ingestion_adds_discovery_without_duplicate_detail_job(db_session):
    job = JobRepository(db_session).create_job(job_type=JobType.FEED_COLLECT, payload={})
    candidate = FeedCandidateInput(
        platform=Platform.XHS,
        platform_content_id="dup-id",
        canonical_url="https://fake.local/dup-id",
        content_type=ContentType.IMAGE_TEXT,
        title_or_summary="SCI论文投稿",
        source_surface=SourceSurface.XHS_HOME_FEED,
        feed_type=FeedType.XHS_HOME_FEED,
        feed_position=1,
        visible_like_count=120,
        discovered_at=datetime.now(timezone.utc),
    )
    repo = ContentRepository(db_session)
    repo.ingest_feed_candidate(job_id=job.id, account_id=None, candidate=candidate)
    candidate.feed_position = 2
    repo.ingest_feed_candidate(job_id=job.id, account_id=None, candidate=candidate)

    assert db_session.scalar(select(func.count()).select_from(ContentDiscoveryEvent)) == 2
    assert db_session.scalar(select(func.count()).select_from(Job).where(Job.job_type == JobType.DETAIL_FETCH.value)) == 1


def test_intelligence_list_uses_latest_candidate_decision_once(db_session):
    job = JobRepository(db_session).create_job(job_type=JobType.FEED_COLLECT, payload={})
    candidate = FeedCandidateInput(
        platform=Platform.XHS,
        platform_content_id="multi-decision-id",
        canonical_url="https://fake.local/multi-decision-id",
        content_type=ContentType.IMAGE_TEXT,
        title_or_summary="SCI论文投稿",
        source_surface=SourceSurface.XHS_HOME_FEED,
        feed_type=FeedType.XHS_HOME_FEED,
        feed_position=1,
        visible_like_count=120,
        discovered_at=datetime.now(timezone.utc),
    )
    repo = ContentRepository(db_session)
    content, *_ = repo.ingest_feed_candidate(job_id=job.id, account_id=None, candidate=candidate)
    snapshot = repo.create_snapshot(
        content_id=content.id,
        account_id=None,
        snapshot=DetailSnapshotInput(title="SCI论文投稿", body_text="第一次评估", like_count=120),
    )
    repo.evaluate_candidate(content_id=content.id, snapshot_id=snapshot.id)
    repo.evaluate_candidate(content_id=content.id, snapshot_id=snapshot.id)

    items, total = repo.list_intelligence_contents(page=1, page_size=20)

    assert total == 1
    assert [item["content_id"] for item in items] == [content.id]
