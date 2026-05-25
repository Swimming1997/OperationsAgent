# legacy DB-coupled smoke tool; not part of the formal Local Agent Runtime.
from sqlalchemy import func, select

from intelligence_engine.db.models import (
    CandidateDecision,
    CommentSnapshot,
    ContentDiscoveryEvent,
    ContentIdentity,
    ContentSnapshot,
    CreatorMonitorEvent,
    FetchLease,
    Job,
)
from intelligence_engine.domain.enums import FeedType, JobStatus, JobType, LeaseResourceType, Platform
from intelligence_engine.local_agent.fake_runner import FakeAgentRunner
from intelligence_engine.storage.repositories.account_repository import AccountRepository
from intelligence_engine.storage.repositories.creator_repository import CreatorMonitorRepository
from intelligence_engine.storage.repositories.job_repository import JobRepository
from intelligence_engine.storage.repositories.lease_repository import LeaseRepository


def test_fake_feed_to_detail_comment_decision_e2e(db_session):
    account_repo = AccountRepository(db_session)
    agent = account_repo.register_agent(
        employee_id=None,
        device_name="fake-agent",
        machine_fingerprint="fake-agent-fp",
        agent_version="0.1.0",
        capabilities={"platforms": ["xhs", "douyin"]},
    )
    account = account_repo.create_account(
        employee_id=None,
        platform=Platform.XHS.value,
        display_name="小红书假账号",
        external_account_id=None,
        business_account_type="A",
        default_agent_id=agent.id,
        metadata={},
    )
    JobRepository(db_session).create_job(
        job_type=JobType.FEED_COLLECT,
        account_id=account.id,
        local_agent_id=agent.id,
        payload={
            "platform": Platform.XHS.value,
            "account_id": account.id,
            "feed_type": FeedType.XHS_HOME_FEED.value,
            "target_count": 50,
            "refresh_rounds": 2,
            "per_round_scroll_target": 50,
        },
        priority=100,
    )

    handled = FakeAgentRunner(db_session, agent_id=agent.id).run_until_idle()
    db_session.commit()

    assert handled == 101
    assert db_session.scalar(select(func.count(ContentIdentity.id))) == 50
    assert db_session.scalar(select(func.count(ContentSnapshot.id))) == 50
    assert db_session.scalar(select(func.count(CommentSnapshot.id))) == 1000
    assert db_session.scalar(select(func.count(CandidateDecision.id))) >= 50
    assert db_session.scalar(select(func.count(Job.id)).where(Job.job_type == JobType.DETAIL_FETCH.value)) == 50
    assert db_session.scalar(select(func.count(Job.id)).where(Job.job_type == JobType.COMMENT_FETCH.value)) == 50


def test_fake_creator_monitor_discovers_new_content_and_enqueues_detail(db_session):
    agent = AccountRepository(db_session).register_agent(
        employee_id=None,
        device_name="fake-agent",
        machine_fingerprint="creator-agent-fp",
        agent_version="0.1.0",
        capabilities={"platforms": ["xhs"]},
    )
    creator_repo = CreatorMonitorRepository(db_session)
    monitor = creator_repo.create_monitor(
        platform=Platform.XHS.value,
        creator_platform_id="creator-001",
        creator_display_name="对标账号001",
        monitor_group_key="A类账号对标",
        mapped_business_account_type="A",
        check_interval_seconds=900,
    )
    creator_repo.enqueue_monitor_job(monitor=monitor, priority=100)

    handled = FakeAgentRunner(db_session, agent_id=agent.id).run_until_idle(max_iterations=1)
    db_session.commit()

    assert handled == 1
    assert db_session.scalar(select(func.count(ContentIdentity.id))) == 20
    assert db_session.scalar(select(func.count(ContentDiscoveryEvent.id))) == 20
    assert db_session.scalar(select(func.count(CreatorMonitorEvent.id)).where(CreatorMonitorEvent.event_type == "new_content_detected")) == 20
    assert db_session.scalar(select(func.count(CreatorMonitorEvent.id)).where(CreatorMonitorEvent.event_type == "monitor_run_success")) == 1
    assert db_session.scalar(select(func.count(Job.id)).where(Job.job_type == JobType.DETAIL_FETCH.value)) == 20


def test_creator_monitor_lease_conflict_skips_duplicate_execution(db_session):
    agent = AccountRepository(db_session).register_agent(
        employee_id=None,
        device_name="fake-agent",
        machine_fingerprint="creator-lease-agent-fp",
        agent_version="0.1.0",
        capabilities={"platforms": ["xhs"]},
    )
    creator_repo = CreatorMonitorRepository(db_session)
    monitor = creator_repo.create_monitor(
        platform=Platform.XHS.value,
        creator_platform_id="creator-lease",
        creator_display_name="对标账号lease",
        monitor_group_key=None,
        mapped_business_account_type=None,
        check_interval_seconds=900,
    )
    job = creator_repo.enqueue_monitor_job(monitor=monitor, priority=100)
    LeaseRepository(db_session).try_acquire(
        resource_type=LeaseResourceType.CREATOR_MONITOR,
        resource_key=f"creator_monitor:{monitor.id}",
        owner_job_id=job.id,
        ttl_seconds=600,
    )

    FakeAgentRunner(db_session, agent_id=agent.id).run_until_idle(max_iterations=1)

    assert job.status == JobStatus.PARTIAL_SUCCESS.value
    assert job.result_summary_json == {"lease_conflict": True}
    assert db_session.scalar(select(func.count(ContentIdentity.id))) == 0
    assert db_session.scalar(select(func.count(CreatorMonitorEvent.id))) == 0


def test_detail_and_comment_lease_conflicts_skip_duplicate_execution(db_session):
    account_repo = AccountRepository(db_session)
    agent = account_repo.register_agent(
        employee_id=None,
        device_name="fake-agent",
        machine_fingerprint="detail-comment-lease-agent-fp",
        agent_version="0.1.0",
        capabilities={"platforms": ["xhs"]},
    )
    account = account_repo.create_account(
        employee_id=None,
        platform=Platform.XHS.value,
        display_name="小红书假账号",
        external_account_id=None,
        business_account_type="A",
        default_agent_id=agent.id,
        metadata={},
    )
    feed_job = JobRepository(db_session).create_job(
        job_type=JobType.FEED_COLLECT,
        account_id=account.id,
        local_agent_id=agent.id,
        payload={
            "platform": Platform.XHS.value,
            "account_id": account.id,
            "feed_type": FeedType.XHS_HOME_FEED.value,
            "target_count": 1,
        },
        priority=100,
    )
    FakeAgentRunner(db_session, agent_id=agent.id).run_job(feed_job)
    content = db_session.scalar(select(ContentIdentity))
    detail_job = db_session.scalar(select(Job).where(Job.job_type == JobType.DETAIL_FETCH.value))
    LeaseRepository(db_session).try_acquire(
        resource_type=LeaseResourceType.DETAIL_FETCH,
        resource_key=f"detail:{content.platform}:{content.id}",
        owner_job_id=detail_job.id,
        ttl_seconds=600,
    )

    FakeAgentRunner(db_session, agent_id=agent.id).run_job(detail_job)

    assert detail_job.status == JobStatus.PARTIAL_SUCCESS.value
    assert detail_job.result_summary_json == {"lease_conflict": True}
    assert db_session.scalar(select(func.count(ContentSnapshot.id))) == 0

    released_lease = db_session.scalar(select(FetchLease).where(FetchLease.resource_type == LeaseResourceType.DETAIL_FETCH.value))
    LeaseRepository(db_session).release(released_lease)
    retry_detail_job = JobRepository(db_session).create_job(
        job_type=JobType.DETAIL_FETCH,
        account_id=account.id,
        payload={
            "content_id": content.id,
            "platform": content.platform,
            "platform_content_id": content.platform_content_id,
        },
        priority=80,
    )
    FakeAgentRunner(db_session, agent_id=agent.id).run_job(retry_detail_job)
    comment_job = db_session.scalar(select(Job).where(Job.job_type == JobType.COMMENT_FETCH.value))
    LeaseRepository(db_session).try_acquire(
        resource_type=LeaseResourceType.COMMENT_FETCH,
        resource_key=f"comments:{content.platform}:{content.id}",
        owner_job_id=comment_job.id,
        ttl_seconds=600,
    )

    FakeAgentRunner(db_session, agent_id=agent.id).run_job(comment_job)

    assert comment_job.status == JobStatus.PARTIAL_SUCCESS.value
    assert comment_job.result_summary_json == {"lease_conflict": True}
    assert db_session.scalar(select(func.count(CommentSnapshot.id))) == 0
