# legacy DB-coupled smoke tool; not part of the formal Local Agent Runtime.
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from intelligence_engine.connectors.xhs.homefeed_probe import XhsHomeFeedProbe
from intelligence_engine.db.models import CandidateDecision, CommentSnapshot, ContentIdentity, ContentSnapshot, Job, utcnow
from intelligence_engine.domain.enums import CandidateBucket, JobType, Platform, SessionStatus
from intelligence_engine.filtering.candidate_classifier import (
    DEFAULT_FILTER_V1_CONFIG,
    IntelligenceFilterConfig,
    classify_feed_prelim,
    classify_intelligence_v1,
)
from intelligence_engine.local_agent.xhs_main_chain_smoke_runner import XhsMainChainSmokeRunner
from intelligence_engine.sessions.xhs_browser_session import XhsBrowserSessionProvider
from intelligence_engine.storage.repositories.content_repository import ContentRepository
from intelligence_engine.storage.repositories.job_repository import JobRepository


class XhsIntelligenceLoopRunner:
    def __init__(self, *, db: Session, center_base_url: str = "http://127.0.0.1:8000", config: IntelligenceFilterConfig = DEFAULT_FILTER_V1_CONFIG):
        self.db = db
        self.center_base_url = center_base_url.rstrip("/")
        self.config = config

    async def run(
        self,
        *,
        feed_job_id: str,
        account_id: str,
        session_meta: dict[str, Any],
        target_count: int = 50,
        max_comments: int = 20,
    ) -> dict[str, Any]:
        run_started_at = utcnow()
        homefeed = await self._collect_homefeed(session_meta=session_meta, target_count=target_count)
        if homefeed["session_status"] != SessionStatus.READY.value:
            return {
                "session_status": homefeed["session_status"],
                "session_message": homefeed["session_message"],
                "homefeed_sample_count": 0,
                "feed_prelim_candidate_count": 0,
                "detail_fetch_count": 0,
                "detail_success_count": 0,
                "comment_fetch_count": 0,
                "comment_success_count": 0,
                "lead_candidate_count": 0,
                "content_candidate_count": 0,
                "discard_count": 0,
                "pending_enrichment_count": 0,
                "candidates": [],
            }

        repo = ContentRepository(self.db)
        feed_rows: list[dict[str, Any]] = []
        prelim_content_ids: list[str] = []
        for candidate in homefeed["candidates"]:
            content, _is_new, _event, _detail_enqueued, _prelim = repo.ingest_feed_candidate(
                job_id=feed_job_id,
                account_id=account_id,
                candidate=candidate,
                enqueue_detail_job=False,
            )
            prelim = classify_feed_prelim(
                title_or_summary=candidate.title_or_summary,
                visible_like_count=candidate.visible_like_count,
                config=self.config,
            )
            repo.create_decision(content_id=content.id, snapshot_id=None, result=prelim)
            if prelim.candidate_bucket != CandidateBucket.DISCARD:
                prelim_content_ids.append(content.id)
                self._enqueue_detail_job(account_id=account_id, content=content)
            feed_rows.append(
                {
                    "content_id": content.id,
                    "platform_content_id": content.platform_content_id,
                    "title": candidate.title_or_summary,
                    "visible_like_count": candidate.visible_like_count,
                    "feed_prelim_bucket": prelim.candidate_bucket.value,
                    "feed_business_hits": prelim.business_keyword_hits,
                }
            )
        self.db.commit()

        smoke = XhsMainChainSmokeRunner(db=self.db, center_base_url=self.center_base_url)
        detail_jobs = self._select_jobs_for_contents(JobType.DETAIL_FETCH, prelim_content_ids, run_started_at, len(prelim_content_ids))
        detail_result = await smoke._run_detail_jobs(jobs=detail_jobs, session_meta=session_meta, post_ingestion=True)
        self.db.expire_all()

        detail_kept_content_ids = self._detail_kept_content_ids(prelim_content_ids)
        comment_jobs = self._select_jobs_for_contents(JobType.COMMENT_FETCH, detail_kept_content_ids, run_started_at, len(detail_kept_content_ids))
        comment_result = await smoke._run_comment_jobs(jobs=comment_jobs, session_meta=session_meta, max_comments=max_comments, post_ingestion=True)
        self.db.expire_all()

        final_candidates = self._write_final_decisions(feed_rows)
        counts = self._bucket_counts(final_candidates)
        return {
            "session_status": homefeed["session_status"],
            "session_message": homefeed["session_message"],
            "homefeed_sample_count": len(homefeed["candidates"]),
            "feed_prelim_candidate_count": len(prelim_content_ids),
            "detail_fetch_count": len(detail_jobs),
            "detail_success_count": detail_result["success_count"],
            "comment_fetch_count": len(comment_jobs),
            "comment_success_count": comment_result["success_count"],
            "lead_candidate_count": counts[CandidateBucket.LEAD_CANDIDATE.value],
            "content_candidate_count": counts[CandidateBucket.CONTENT_CANDIDATE.value],
            "discard_count": counts[CandidateBucket.DISCARD.value],
            "pending_enrichment_count": counts[CandidateBucket.PENDING_ENRICHMENT.value],
            "rule_config": {
                "business_keywords": self.config.business_keywords,
                "lead_intent_keywords": self.config.lead_intent_keywords,
                "visible_like_threshold": self.config.visible_like_threshold,
            },
            "candidates": final_candidates,
            "detail_failures": detail_result["failures"],
            "comment_failures": comment_result["failures"],
        }

    async def _collect_homefeed(self, *, session_meta: dict[str, Any], target_count: int) -> dict[str, Any]:
        session = await XhsBrowserSessionProvider().acquire(session_meta=session_meta)
        if session.status != SessionStatus.READY:
            await session.close()
            return {"session_status": session.status.value, "session_message": session.message, "candidates": []}
        try:
            candidates, report = await XhsHomeFeedProbe(target_count=target_count).collect(session.page)
            return {
                "session_status": session.status.value,
                "session_message": session.message,
                "candidates": candidates,
                "report": report,
            }
        finally:
            await session.close()

    def _enqueue_detail_job(self, *, account_id: str, content: ContentIdentity) -> Job:
        return JobRepository(self.db).create_job(
            job_type=JobType.DETAIL_FETCH,
            account_id=account_id,
            payload={
                "content_id": content.id,
                "platform": content.platform,
                "platform_content_id": content.platform_content_id,
                "canonical_url": content.canonical_url,
                "platform_context": (content.metadata_json or {}).get("platform_context", {}),
                "preferred_fetch_mode": "request_first_with_browser_fallback",
                "source": "xhs_intelligence_loop_v1",
            },
            priority=70,
        )

    def _select_jobs_for_contents(self, job_type: JobType, content_ids: list[str], created_after: datetime, limit: int) -> list[Job]:
        if not content_ids or limit <= 0:
            return []
        return list(
            self.db.scalars(
                select(Job)
                .where(Job.job_type == job_type.value)
                .where(Job.payload_json["content_id"].as_string().in_(content_ids))
                .where(Job.created_at >= created_after)
                .order_by(Job.created_at.asc())
                .limit(limit)
            )
        )

    def _detail_kept_content_ids(self, content_ids: list[str]) -> list[str]:
        kept: list[str] = []
        for content_id in content_ids:
            content = self.db.get(ContentIdentity, content_id)
            snapshot = self.db.get(ContentSnapshot, content.latest_snapshot_id) if content and content.latest_snapshot_id else None
            if not content or not snapshot:
                continue
            visible_like_count = (content.metadata_json or {}).get("visible_like_count")
            result = classify_intelligence_v1(
                title=snapshot.title,
                body_text=snapshot.body_text,
                visible_like_count=visible_like_count,
                detail_like_count=snapshot.like_count,
                config=self.config,
            )
            if result.candidate_bucket != CandidateBucket.DISCARD:
                kept.append(content_id)
        return kept

    def _write_final_decisions(self, feed_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        by_content_id = {row["content_id"]: row for row in feed_rows}
        final_rows: list[dict[str, Any]] = []
        repo = ContentRepository(self.db)
        for content_id, feed_row in by_content_id.items():
            content = self.db.get(ContentIdentity, content_id)
            snapshot = self.db.get(ContentSnapshot, content.latest_snapshot_id) if content and content.latest_snapshot_id else None
            comments = list(
                self.db.scalars(
                    select(CommentSnapshot.body_text).where(CommentSnapshot.content_id == content_id).order_by(CommentSnapshot.created_at.desc()).limit(20)
                )
            )
            visible_like_count = (content.metadata_json or {}).get("visible_like_count") if content else feed_row.get("visible_like_count")
            if snapshot:
                result = classify_intelligence_v1(
                    title=snapshot.title,
                    body_text=snapshot.body_text,
                    comments=comments,
                    visible_like_count=visible_like_count,
                    detail_like_count=snapshot.like_count,
                    config=self.config,
                )
                snapshot_id = snapshot.id
                title = snapshot.title or feed_row.get("title")
            else:
                result = classify_feed_prelim(
                    title_or_summary=feed_row.get("title"),
                    visible_like_count=visible_like_count,
                    config=self.config,
                )
                snapshot_id = None
                title = feed_row.get("title")
            decision = repo.create_decision(content_id=content_id, snapshot_id=snapshot_id, result=result)
            final_rows.append(
                {
                    "content_id": content_id,
                    "title": title,
                    "visible_like_count": visible_like_count,
                    "matched_business_keywords": decision.business_keyword_hits_json,
                    "matched_lead_keywords": decision.lead_keyword_hits_json,
                    "matched_comment_keywords": decision.comment_keyword_hits_json,
                    "final_bucket": decision.candidate_bucket,
                }
            )
        self.db.commit()
        return final_rows

    def _bucket_counts(self, rows: list[dict[str, Any]]) -> dict[str, int]:
        counts = {
            CandidateBucket.LEAD_CANDIDATE.value: 0,
            CandidateBucket.CONTENT_CANDIDATE.value: 0,
            CandidateBucket.DISCARD.value: 0,
            CandidateBucket.PENDING_ENRICHMENT.value: 0,
        }
        for row in rows:
            counts[row["final_bucket"]] += 1
        return counts
