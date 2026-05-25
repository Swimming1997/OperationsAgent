from sqlalchemy import func, select
from sqlalchemy.orm import Session

from intelligence_engine.db.models import (
    CandidateDecision,
    CommentSnapshot,
    ContentDiscoveryEvent,
    ContentIdentity,
    ContentSnapshot,
    utcnow,
)
from intelligence_engine.config import get_settings
from intelligence_engine.domain.enums import CandidateBucket, JobType, Platform
from intelligence_engine.domain.schemas import CommentSnapshotInput, DetailSnapshotInput, FeedCandidateInput
from intelligence_engine.db.models import Job
from intelligence_engine.filtering.candidate_classifier import (
    CandidateDecisionResult,
    classify_candidate,
    classify_feed_prelim,
    classify_intelligence_v1,
)
from intelligence_engine.domain.xhs_context import merge_xhs_context, prefer_richer_xhs_url
from intelligence_engine.domain.intelligence_pool import build_discovery_meta_from_candidate
from intelligence_engine.services.enrichment_policy import should_enqueue_detail_fetch
from intelligence_engine.storage.repositories.job_repository import JobRepository
from intelligence_engine.storage.repositories.workflow_repository import WorkflowRepository


def enum_value(value):
    return getattr(value, "value", value)


def xhs_platform_context(*contexts: dict | None) -> dict:
    return merge_xhs_context(*contexts)


INVALID_FEED_AUTHOR_NAMES = frozenset({"我", "我的", "首页", "发现", "推荐", "关注", "消息", "搜索", "登录", "发布"})


def sanitize_feed_author_name(value: str | None) -> str | None:
    if not value:
        return None
    cleaned = value.strip()
    if len(cleaned) <= 1 or cleaned in INVALID_FEED_AUTHOR_NAMES:
        return None
    if cleaned.endswith("的") and len(cleaned) <= 3:
        return None
    return cleaned


class ContentRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_platform_identity(self, *, platform: str, platform_content_id: str) -> ContentIdentity | None:
        return self.db.scalar(
            select(ContentIdentity).where(
                ContentIdentity.platform == platform,
                ContentIdentity.platform_content_id == platform_content_id,
            )
        )

    def upsert_identity_from_candidate(self, candidate: FeedCandidateInput) -> tuple[ContentIdentity, bool]:
        now = candidate.discovered_at
        content = self.get_by_platform_identity(
            platform=enum_value(candidate.platform),
            platform_content_id=candidate.platform_content_id,
        )
        if content:
            content.last_seen_at = now
            content.canonical_url = prefer_richer_xhs_url(content.canonical_url, candidate.canonical_url)
            metadata = dict(content.metadata_json or {})
            metadata["feed_title_or_summary"] = metadata.get("feed_title_or_summary") or candidate.title_or_summary
            metadata["cover_url"] = metadata.get("cover_url") or candidate.cover_url
            metadata["author_platform_id"] = metadata.get("author_platform_id") or candidate.author_platform_id
            incoming_author = sanitize_feed_author_name(candidate.author_name)
            existing_author = sanitize_feed_author_name(metadata.get("author_name"))
            metadata["author_name"] = incoming_author or existing_author
            metadata["visible_like_count"] = candidate.visible_like_count if candidate.visible_like_count is not None else metadata.get("visible_like_count")
            existing_context = metadata.get("platform_context") if isinstance(metadata.get("platform_context"), dict) else {}
            metadata["platform_context"] = (
                merge_xhs_context(existing_context, candidate.platform_context)
                if enum_value(candidate.platform) == Platform.XHS.value
                else (candidate.platform_context or existing_context)
            )
            content.metadata_json = metadata
            return content, False
        content = ContentIdentity(
            platform=enum_value(candidate.platform),
            platform_content_id=candidate.platform_content_id,
            canonical_url=candidate.canonical_url,
            content_type=enum_value(candidate.content_type),
            first_seen_at=now,
            last_seen_at=now,
            metadata_json={
                "feed_title_or_summary": candidate.title_or_summary,
                "cover_url": candidate.cover_url,
                "author_platform_id": candidate.author_platform_id,
                "author_name": sanitize_feed_author_name(candidate.author_name),
                "visible_like_count": candidate.visible_like_count,
                "platform_context": (
                    merge_xhs_context(candidate.platform_context)
                    if enum_value(candidate.platform) == Platform.XHS.value
                    else candidate.platform_context
                ),
            },
        )
        self.db.add(content)
        self.db.flush()
        return content, True

    def insert_discovery_event(self, *, content: ContentIdentity, job_id: str, account_id: str | None, candidate: FeedCandidateInput) -> ContentDiscoveryEvent:
        event = ContentDiscoveryEvent(
            content_id=content.id,
            job_id=job_id,
            account_id=account_id,
            platform=enum_value(candidate.platform),
            source_surface=enum_value(candidate.source_surface),
            feed_type=enum_value(candidate.feed_type) if candidate.feed_type else None,
            feed_position=candidate.feed_position,
            discovered_at=candidate.discovered_at,
            discovery_meta_json=build_discovery_meta_from_candidate(
                candidate.raw_payload,
                feed_position=candidate.feed_position,
            ),
        )
        self.db.add(event)
        self.db.flush()
        return event

    def ingest_feed_candidate(
        self,
        *,
        job_id: str,
        account_id: str | None,
        candidate: FeedCandidateInput,
        enqueue_detail_job: bool | None = None,
    ) -> tuple[ContentIdentity, bool, ContentDiscoveryEvent, bool, bool | None]:
        content, is_new = self.upsert_identity_from_candidate(candidate)
        WorkflowRepository(self.db).ensure_state(content.id)
        event = self.insert_discovery_event(content=content, job_id=job_id, account_id=account_id, candidate=candidate)
        detail_job_enqueued = False
        feed_prelim_pass: bool | None = None
        parent_job = self.db.get(Job, job_id)
        task_run_id = parent_job.task_run_id if parent_job else None
        should_apply_feed_prelim = bool(
            parent_job
            and parent_job.job_type == JobType.FEED_COLLECT.value
            and (parent_job.payload_json or {}).get("materialized_from_task")
        )
        detail_priority = 80
        if should_apply_feed_prelim:
            prelim = classify_feed_prelim(
                title_or_summary=candidate.title_or_summary,
                visible_like_count=candidate.visible_like_count,
            )
            self.create_decision(content_id=content.id, snapshot_id=None, result=prelim)
            feed_prelim_pass = prelim.candidate_bucket != CandidateBucket.DISCARD.value
            # Prelim is advisory only: never block detail_fetch before the detail page is seen.
            # Higher-priority (lower number) jobs are claimed first when the agent is busy.
            detail_priority = 72 if feed_prelim_pass else 88
        parent_job_type = parent_job.job_type if parent_job else None
        should_enqueue = enqueue_detail_job
        if should_enqueue is None:
            should_enqueue = should_enqueue_detail_fetch(
                candidate=candidate,
                is_new=is_new,
                feed_prelim_pass=feed_prelim_pass,
                parent_job_type=parent_job_type,
            )
        if is_new and should_enqueue:
            metadata_context = (content.metadata_json or {}).get("platform_context", {})
            platform_context = (
                xhs_platform_context(metadata_context, candidate.platform_context)
                if content.platform == Platform.XHS.value
                else (candidate.platform_context or metadata_context)
            )
            JobRepository(self.db).create_job(
                job_type=JobType.DETAIL_FETCH,
                account_id=account_id,
                task_run_id=task_run_id,
                payload={
                    "content_id": content.id,
                    "platform": content.platform,
                    "platform_content_id": content.platform_content_id,
                    "canonical_url": content.canonical_url,
                    "platform_context": platform_context,
                    "preferred_fetch_mode": "request_first_with_browser_fallback",
                    "parent_feed_job_id": job_id,
                },
                priority=detail_priority,
            )
            detail_job_enqueued = True
        return content, is_new, event, detail_job_enqueued, feed_prelim_pass

    def create_decision(
        self,
        *,
        content_id: str,
        snapshot_id: str | None,
        result: CandidateDecisionResult,
    ) -> CandidateDecision:
        row = CandidateDecision(
            content_id=content_id,
            snapshot_id=snapshot_id,
            business_keyword_hits_json=result.business_keyword_hits,
            lead_keyword_hits_json=result.lead_keyword_hits,
            comment_keyword_hits_json=result.comment_keyword_hits,
            like_threshold_hit=result.like_threshold_hit,
            comment_threshold_hit=result.comment_threshold_hit,
            candidate_bucket=result.candidate_bucket.value,
            decision_reason_json=result.reason,
            evaluated_at=utcnow(),
        )
        self.db.add(row)
        self.db.flush()
        return row

    def create_snapshot(self, *, content_id: str, account_id: str | None, snapshot: DetailSnapshotInput) -> ContentSnapshot:
        row = ContentSnapshot(
            content_id=content_id,
            title=snapshot.title,
            body_text=snapshot.body_text,
            author_platform_id=snapshot.author_platform_id,
            author_name=snapshot.author_name,
            author_avatar_url=snapshot.author_avatar_url,
            cover_url=snapshot.cover_url,
            image_urls_json=snapshot.image_urls,
            video_url=snapshot.video_url,
            like_count=snapshot.like_count,
            comment_count=snapshot.comment_count,
            collect_count=snapshot.collect_count,
            share_count=snapshot.share_count,
            publish_time=snapshot.publish_time,
            fetch_source_account_id=account_id,
            raw_payload_json=snapshot.raw_payload,
            fetched_at=utcnow(),
        )
        self.db.add(row)
        self.db.flush()
        content = self.db.get(ContentIdentity, content_id)
        if content:
            content.latest_snapshot_id = row.id
        return row

    def create_or_update_comments(self, *, content_id: str, comments: list[CommentSnapshotInput]) -> tuple[int, int, list[str]]:
        inserted = 0
        updated = 0
        now = utcnow()
        texts: list[str] = []
        for comment in comments:
            texts.append(comment.body_text)
            existing = self.db.scalar(
                select(CommentSnapshot).where(
                    CommentSnapshot.content_id == content_id,
                    CommentSnapshot.platform_comment_id == comment.platform_comment_id,
                )
            )
            if existing:
                existing.body_text = comment.body_text
                existing.like_count = comment.like_count
                existing.raw_payload_json = comment.raw_payload
                existing.fetched_at = now
                updated += 1
            else:
                self.db.add(
                    CommentSnapshot(
                        content_id=content_id,
                        platform_comment_id=comment.platform_comment_id,
                        parent_platform_comment_id=comment.parent_platform_comment_id,
                        author_platform_id=comment.author_platform_id,
                        author_name=comment.author_name,
                        body_text=comment.body_text,
                        like_count=comment.like_count,
                        created_time=comment.created_time,
                        raw_payload_json=comment.raw_payload,
                        fetched_at=now,
                    )
                )
                inserted += 1
        self.db.flush()
        decision = classify_candidate(title=None, body_text=None, comments=texts)
        return inserted, updated, decision.comment_keyword_hits

    def evaluate_candidate(self, *, content_id: str, snapshot_id: str) -> CandidateDecision:
        content = self.db.get(ContentIdentity, content_id)
        snapshot = self.db.get(ContentSnapshot, snapshot_id)
        comments = list(
            self.db.scalars(
                select(CommentSnapshot.body_text).where(CommentSnapshot.content_id == content_id).order_by(CommentSnapshot.created_at.desc()).limit(20)
            )
        )
        metadata = (content.metadata_json or {}) if content else {}
        visible_like = metadata.get("visible_like_count")
        result = classify_intelligence_v1(
            title=snapshot.title if snapshot else None,
            body_text=snapshot.body_text if snapshot else None,
            comments=comments,
            visible_like_count=visible_like if isinstance(visible_like, int) else None,
            detail_like_count=snapshot.like_count if snapshot else None,
        )
        return self.create_decision(content_id=content_id, snapshot_id=snapshot_id, result=result)

    def list_intelligence_contents(self, *, page: int, page_size: int) -> tuple[list[dict], int]:
        total = self.db.scalar(select(func.count(ContentIdentity.id))) or 0
        rows = list(
            self.db.execute(
                select(ContentIdentity, ContentSnapshot, CandidateDecision, func.max(ContentDiscoveryEvent.discovered_at))
                .join(ContentDiscoveryEvent, ContentDiscoveryEvent.content_id == ContentIdentity.id, isouter=True)
                .join(ContentSnapshot, ContentSnapshot.id == ContentIdentity.latest_snapshot_id, isouter=True)
                .join(CandidateDecision, CandidateDecision.snapshot_id == ContentSnapshot.id, isouter=True)
                .group_by(ContentIdentity.id, ContentSnapshot.id, CandidateDecision.id)
                .order_by(func.max(ContentDiscoveryEvent.discovered_at).desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        )
        items = []
        for content, snapshot, decision, latest_discovered_at in rows:
            items.append(
                {
                    "content_id": content.id,
                    "platform": content.platform,
                    "content_type": content.content_type,
                    "title": snapshot.title if snapshot else content.metadata_json.get("feed_title_or_summary"),
                    "author_name": snapshot.author_name if snapshot else content.metadata_json.get("author_name"),
                    "cover_url": snapshot.cover_url if snapshot else content.metadata_json.get("cover_url"),
                    "like_count": snapshot.like_count if snapshot else content.metadata_json.get("visible_like_count"),
                    "comment_count": snapshot.comment_count if snapshot else None,
                    "candidate_bucket": decision.candidate_bucket if decision else CandidateBucket.PENDING_ENRICHMENT.value,
                    "latest_discovered_at": latest_discovered_at,
                }
            )
        return items, total

    def enqueue_detail_fetch(self, *, content_id: str, account_id: str | None = None) -> Job:
        content = self.db.get(ContentIdentity, content_id)
        if not content:
            raise ValueError("content not found")
        metadata_context = (content.metadata_json or {}).get("platform_context", {})
        if not isinstance(metadata_context, dict):
            metadata_context = {}
        job = JobRepository(self.db).create_job(
            job_type=JobType.DETAIL_FETCH,
            account_id=account_id,
            payload={
                "content_id": content.id,
                "platform": content.platform,
                "platform_content_id": content.platform_content_id,
                "canonical_url": content.canonical_url,
                "platform_context": metadata_context,
                "preferred_fetch_mode": "request_first_with_browser_fallback",
                "manual_enqueue": True,
            },
            priority=60,
        )
        return job

    def enqueue_comment_fetch(self, *, content_id: str, account_id: str | None = None) -> Job:
        content = self.db.get(ContentIdentity, content_id)
        if not content:
            raise ValueError("content not found")
        metadata = content.metadata_json or {}
        platform_context = metadata.get("platform_context") if isinstance(metadata.get("platform_context"), dict) else {}
        job = JobRepository(self.db).create_job(
            job_type=JobType.COMMENT_FETCH,
            account_id=account_id,
            payload={
                "content_id": content.id,
                "platform": content.platform,
                "platform_content_id": content.platform_content_id,
                "canonical_url": content.canonical_url,
                "platform_context": platform_context,
                "max_comments": get_settings().default_comment_limit,
                "include_sub_comments": False,
                "manual_enqueue": True,
            },
            priority=70,
        )
        return job
