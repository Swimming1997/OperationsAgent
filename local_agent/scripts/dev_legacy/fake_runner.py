# legacy DB-coupled smoke tool; not part of the formal Local Agent Runtime.
from sqlalchemy import select
from sqlalchemy.orm import Session

from local_agent_runtime.connectors.fake.connector import FakeConnector
from intelligence_engine.db.models import ContentIdentity, CreatorMonitor, Job
from local_agent_runtime.enums import FeedType, JobStatus, JobType, Platform
from local_agent_runtime.enums import LeaseResourceType
from local_agent_runtime.contracts import (
    CommentSnapshotInput,
    DetailSnapshotInput,
    FeedCandidateInput,
)
from intelligence_engine.storage.repositories.content_repository import ContentRepository
from intelligence_engine.storage.repositories.creator_repository import CreatorMonitorRepository
from intelligence_engine.storage.repositories.job_repository import JobRepository
from intelligence_engine.storage.repositories.lease_repository import LeaseRepository


class FakeAgentRunner:
    def __init__(self, db: Session, *, agent_id: str):
        self.db = db
        self.agent_id = agent_id
        self.connector = FakeConnector()

    def run_until_idle(self, *, max_iterations: int = 500) -> int:
        handled = 0
        for _ in range(max_iterations):
            job = self.db.scalar(
                select(Job).where(Job.status == JobStatus.PENDING.value).order_by(Job.priority.asc(), Job.created_at.asc())
            )
            if not job:
                break
            self.run_job(job)
            handled += 1
        return handled

    def run_job(self, job: Job) -> None:
        repo = JobRepository(self.db)
        job.status = JobStatus.CLAIMED.value
        repo.mark_started(job, agent_id=self.agent_id)
        if job.job_type == JobType.FEED_COLLECT.value:
            self._run_feed(job)
        elif job.job_type == JobType.DETAIL_FETCH.value:
            self._run_detail(job)
        elif job.job_type == JobType.COMMENT_FETCH.value:
            self._run_comments(job)
        elif job.job_type == JobType.CREATOR_MONITOR.value:
            self._run_creator_monitor(job)
        else:
            repo.mark_success(job, status=JobStatus.PARTIAL_SUCCESS, result_summary={"skipped": True})
            return
        self.db.flush()

    def _run_feed(self, job: Job) -> None:
        payload = job.payload_json
        platform = Platform(payload["platform"])
        feed_type = FeedType(payload["feed_type"])
        target_count = int(payload.get("target_count", 50))
        candidates = self.connector.collect_feed(platform=platform, feed_type=feed_type, target_count=target_count)
        content_repo = ContentRepository(self.db)
        unique_count = 0
        duplicate_count = 0
        detail_jobs = 0
        for candidate in candidates:
            content, is_new, _event, detail_job, _prelim = content_repo.ingest_feed_candidate(
                job_id=job.id,
                account_id=job.account_id,
                candidate=FeedCandidateInput(**candidate.model_dump()),
            )
            unique_count += 1 if is_new else 0
            duplicate_count += 0 if is_new else 1
            detail_jobs += 1 if detail_job else 0
        JobRepository(self.db).update_checkpoint(job, checkpoint={"items_seen": len(candidates), "unique_items_emitted": unique_count})
        JobRepository(self.db).mark_success(
            job,
            status=JobStatus.SUCCESS,
            result_summary={
                "raw_items_seen": len(candidates),
                "normalized_items": len(candidates),
                "unique_contents_inserted": unique_count,
                "duplicate_contents": duplicate_count,
                "detail_jobs_enqueued": detail_jobs,
                "failed_items": 0,
            },
        )

    def _run_detail(self, job: Job) -> None:
        payload = job.payload_json
        content = self.db.get(ContentIdentity, payload["content_id"])
        lease = LeaseRepository(self.db).try_acquire(
            resource_type=LeaseResourceType.DETAIL_FETCH,
            resource_key=f"detail:{content.platform}:{content.id}",
            owner_job_id=job.id,
            ttl_seconds=300,
        )
        if lease is None:
            JobRepository(self.db).mark_success(job, status=JobStatus.PARTIAL_SUCCESS, result_summary={"lease_conflict": True})
            return
        detail = self.connector.fetch_detail(platform=Platform(payload["platform"]), platform_content_id=payload["platform_content_id"])
        snapshot = ContentRepository(self.db).create_snapshot(
            content_id=content.id,
            account_id=job.account_id,
            snapshot=DetailSnapshotInput(**detail.model_dump()),
        )
        ContentRepository(self.db).evaluate_candidate(content_id=content.id, snapshot_id=snapshot.id)
        JobRepository(self.db).create_job(
            job_type=JobType.COMMENT_FETCH,
            account_id=job.account_id,
            payload={
                "content_id": content.id,
                "platform": content.platform,
                "platform_content_id": content.platform_content_id,
                "max_comments": 20,
                "include_sub_comments": False,
            },
            priority=90,
        )
        JobRepository(self.db).mark_success(
            job,
            status=JobStatus.SUCCESS,
            result_summary={"snapshot_id": snapshot.id, "comment_job_enqueued": True, "candidate_decision_enqueued": True},
        )
        LeaseRepository(self.db).release(lease)

    def _run_comments(self, job: Job) -> None:
        payload = job.payload_json
        content = self.db.get(ContentIdentity, payload["content_id"])
        lease = LeaseRepository(self.db).try_acquire(
            resource_type=LeaseResourceType.COMMENT_FETCH,
            resource_key=f"comments:{content.platform}:{content.id}",
            owner_job_id=job.id,
            ttl_seconds=600,
        )
        if lease is None:
            JobRepository(self.db).mark_success(job, status=JobStatus.PARTIAL_SUCCESS, result_summary={"lease_conflict": True})
            return
        comments = self.connector.fetch_comments(
            platform_content_id=payload["platform_content_id"],
            limit=int(payload.get("max_comments", 20)),
        )
        inserted, updated, hits = ContentRepository(self.db).create_or_update_comments(
            content_id=payload["content_id"],
            comments=[CommentSnapshotInput(**comment.model_dump()) for comment in comments],
        )
        if content and content.latest_snapshot_id:
            ContentRepository(self.db).evaluate_candidate(content_id=content.id, snapshot_id=content.latest_snapshot_id)
        JobRepository(self.db).mark_success(
            job,
            status=JobStatus.SUCCESS,
            result_summary={"comments_inserted": inserted, "comments_updated": updated, "lead_keyword_hits": hits},
        )
        LeaseRepository(self.db).release(lease)

    def _run_creator_monitor(self, job: Job) -> None:
        monitor_id = job.creator_monitor_id or job.payload_json.get("creator_monitor_id")
        monitor = self.db.get(CreatorMonitor, monitor_id)
        lease = LeaseRepository(self.db).try_acquire(
            resource_type=LeaseResourceType.CREATOR_MONITOR,
            resource_key=f"creator_monitor:{monitor_id}",
            owner_job_id=job.id,
            ttl_seconds=600,
        )
        if lease is None:
            JobRepository(self.db).mark_success(job, status=JobStatus.PARTIAL_SUCCESS, result_summary={"lease_conflict": True})
            return
        if monitor is None:
            JobRepository(self.db).mark_success(job, status=JobStatus.PARTIAL_SUCCESS, result_summary={"monitor_missing": True})
            LeaseRepository(self.db).release(lease)
            return

        candidates = self.connector.fetch_creator_latest(
            platform=Platform(monitor.platform),
            creator_platform_id=monitor.creator_platform_id,
            max_items=int(job.payload_json.get("max_latest_items", 3)),
        )
        content_repo = ContentRepository(self.db)
        creator_repo = CreatorMonitorRepository(self.db)
        new_content_ids: list[str] = []
        for candidate in candidates:
            content, is_new, _event, _detail_job, _prelim = content_repo.ingest_feed_candidate(
                job_id=job.id,
                account_id=job.account_id,
                candidate=FeedCandidateInput(**candidate.model_dump()),
            )
            if is_new:
                new_content_ids.append(content.id)
                creator_repo.add_event(
                    monitor_id=monitor.id,
                    content_id=content.id,
                    event_type="new_content_detected",
                    payload={"platform_content_id": content.platform_content_id},
                )
        creator_repo.add_event(
            monitor_id=monitor.id,
            event_type="monitor_run_success",
            payload={"items_seen": len(candidates), "new_contents_detected": len(new_content_ids)},
        )
        monitor.last_cursor_json = {"last_seen_platform_content_ids": [candidate.platform_content_id for candidate in candidates]}
        JobRepository(self.db).mark_success(
            job,
            status=JobStatus.SUCCESS,
            result_summary={
                "items_seen": len(candidates),
                "new_contents_detected": len(new_content_ids),
                "new_content_ids": new_content_ids,
            },
        )
        LeaseRepository(self.db).release(lease)
