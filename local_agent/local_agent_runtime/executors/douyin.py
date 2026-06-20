from __future__ import annotations

from typing import Any

import httpx

from local_agent_runtime.audit.summary import engine_audit_summary
from local_agent_runtime.connectors.douyin.comment_probe import DouyinCommentProbe
from local_agent_runtime.connectors.douyin.creator_probe import DouyinCreatorProbe
from local_agent_runtime.connectors.douyin.detail_probe import DouyinDetailProbe
from local_agent_runtime.connectors.douyin.feed_probe import DouyinFeedProbe
from local_agent_runtime.connectors.douyin.suggest_probe import DouyinSearchSuggestProbe
from local_agent_runtime.contracts import (
    CommentIngestionRequest,
    CreatorMonitorIngestionRequest,
    DetailIngestionRequest,
    FeedCandidateIngestionRequest,
    FeedCandidateInput,
)
from local_agent_runtime.engine.search_config import SearchQueryConfig
from local_agent_runtime.engine.session import SessionProviderRegistry
from local_agent_runtime.enums import ErrorCode, JobStatus, JobType, Platform, SessionStatus
from local_agent_runtime.sessions.registry import default_session_registry


def _job_execution_result(**kwargs):
    from local_agent_runtime.runtime import JobExecutionResult

    return JobExecutionResult(**kwargs)


def _runtime_failure(*args, **kwargs):
    from local_agent_runtime.runtime import RuntimeFailure

    return RuntimeFailure(*args, **kwargs)


def _session_error_code(status: SessionStatus) -> ErrorCode:
    if status == SessionStatus.AUTH_REQUIRED:
        return ErrorCode.AUTH_REQUIRED
    if status == SessionStatus.MANUAL_VERIFY_REQUIRED:
        return ErrorCode.MANUAL_VERIFY_REQUIRED
    return ErrorCode.SESSION_CONNECT_FAILED


class DouyinJobExecutor:
    """Douyin job executor.

    All read-only collection surfaces use the same unified ingestion contracts
    as XHS. Platform-specific response interception stays inside connectors.
    """

    SEARCH_CAPABILITY_KEY = "douyin.search.videos"
    FEED_CAPABILITY_KEY = "douyin.feed.recommend"

    def __init__(
        self,
        *,
        client: CenterClient,
        config: AgentRuntimeConfig,
        session_registry: SessionProviderRegistry | None = None,
    ):
        self.client = client
        self.config = config
        self.session_registry = session_registry or default_session_registry

    SUPPORTED_JOB_TYPES = (
        JobType.SEARCH_COLLECT.value,
        JobType.SEARCH_SUGGEST.value,
        JobType.FEED_COLLECT.value,
        JobType.DETAIL_FETCH.value,
        JobType.COMMENT_FETCH.value,
        JobType.CREATOR_MONITOR.value,
    )

    async def execute(self, *, agent_id: str, job: ClaimedJobPayload) -> JobExecutionResult:
        if job.job_type not in self.SUPPORTED_JOB_TYPES:
            return _job_execution_result(
                status=JobStatus.PARTIAL_SUCCESS.value,
                result_summary={"unsupported_job_type": job.job_type, "platform": Platform.DOUYIN.value},
            )
        session_meta = await self._session_meta(agent_id=agent_id, account_id=job.account_id)
        session = await self.session_registry.create(Platform.DOUYIN.value).acquire(session_meta=session_meta)
        if session.status != SessionStatus.READY:
            await session.close()
            raise _runtime_failure(
                _session_error_code(session.status),
                session.message or f"session status: {session.status.value}",
                retryable=True,
            )
        try:
            if job.job_type == JobType.SEARCH_SUGGEST.value:
                return await self._run_search_suggest(job, session.page)
            if job.job_type == JobType.FEED_COLLECT.value:
                return await self._run_homefeed(job, session.page)
            if job.job_type == JobType.DETAIL_FETCH.value:
                return await self._run_detail(job, session.page)
            if job.job_type == JobType.COMMENT_FETCH.value:
                return await self._run_comment(job, session.page)
            if job.job_type == JobType.CREATOR_MONITOR.value:
                return await self._run_creator_monitor(job, session.page)
            return await self._run_search_collect(job, session.page)
        finally:
            await session.close()

    async def _session_meta(self, *, agent_id: str, account_id: str | None) -> dict[str, Any]:
        if account_id and account_id in self.config.account_sessions:
            return dict(self.config.account_sessions[account_id])
        if account_id:
            try:
                meta = await self.client.get_ready_session(account_id, agent_id)
                if meta:
                    return dict(meta)
            except httpx.HTTPStatusError:
                pass
        if self.config.cdp_url:
            return {"cdp_url": self.config.cdp_url}
        raise _runtime_failure(ErrorCode.SESSION_CONNECT_FAILED, "no ready account session and no fallback cdp_url", retryable=True)

    async def _run_search_collect(self, job: ClaimedJobPayload, page) -> JobExecutionResult:
        cfg = SearchQueryConfig.from_payload(job.payload)
        per_keyword = max(1, cfg.max_items // max(len(cfg.keywords), 1)) if cfg.keywords else cfg.max_items
        candidates_by_id: dict[str, FeedCandidateInput] = {}
        per_keyword_summary: list[dict[str, Any]] = []
        merged_report: dict[str, Any] = {}
        for keyword in cfg.keywords:
            probe = DouyinFeedProbe(
                keyword=keyword,
                target_count=per_keyword,
                sort=cfg.sort,
                publish_time=cfg.publish_time,
                duration=cfg.duration,
                start_rank=cfg.start_rank,
            )
            items, report = await probe.collect(page)
            merged_report = report
            for candidate in items:
                candidates_by_id.setdefault(candidate.platform_content_id, candidate)
            per_keyword_summary.append({"keyword": keyword, "items_seen": len(items)})
        candidates = list(candidates_by_id.values())[: cfg.max_items]
        ingestion = await self.client.ingest_feed_candidates(
            FeedCandidateIngestionRequest(job_id=job.job_id, account_id=job.account_id, candidates=candidates)
        )
        results = ingestion.get("results") or []
        new_count = sum(1 for item in results if item.get("is_new_content"))
        detail_jobs = sum(1 for item in results if item.get("detail_job_enqueued"))
        ingestion_total = len(results)
        return _job_execution_result(
            status=JobStatus.SUCCESS.value,
            checkpoint={"items_seen": len(candidates), "keywords": cfg.keywords},
            result_summary={
                **merged_report,
                "platform": Platform.DOUYIN.value,
                "keywords": cfg.keywords,
                "sort": cfg.sort,
                "publish_time": cfg.publish_time,
                "duration": cfg.duration,
                "start_rank": cfg.start_rank,
                "per_keyword_summary": per_keyword_summary,
                "normalized_items": len(candidates),
                "ingestion_success_count": ingestion_total,
                "new_content_count": new_count,
                "duplicate_content_count": max(0, ingestion_total - new_count),
                "detail_jobs_enqueued": detail_jobs,
                "runtime": "local_agent_runtime_v1",
                "engine_audit": engine_audit_summary(
                    capability_key=self.SEARCH_CAPABILITY_KEY,
                    surface="search",
                    report=merged_report,
                ),
            },
        )


    async def _run_homefeed(self, job: ClaimedJobPayload, page) -> JobExecutionResult:
        payload = job.payload
        target_count = int(payload.get("max_items") or payload.get("target_count") or 30)
        start_rank = int(payload.get("start_rank") or 0)
        probe = DouyinFeedProbe(
            keyword=None,
            target_count=target_count,
            start_rank=start_rank,
        )
        candidates, report = await probe.collect(page)
        ingestion = await self.client.ingest_feed_candidates(
            FeedCandidateIngestionRequest(job_id=job.job_id, account_id=job.account_id, candidates=candidates)
        )
        results = ingestion.get("results") or []
        new_count = sum(1 for item in results if item.get("is_new_content"))
        detail_jobs = sum(1 for item in results if item.get("detail_job_enqueued"))
        ingestion_total = len(results)
        return _job_execution_result(
            status=JobStatus.SUCCESS.value,
            checkpoint={"items_seen": len(candidates), "start_rank": start_rank},
            result_summary={
                **report,
                "platform": Platform.DOUYIN.value,
                "start_rank": start_rank,
                "normalized_items": len(candidates),
                "ingestion_success_count": ingestion_total,
                "new_content_count": new_count,
                "duplicate_content_count": max(0, ingestion_total - new_count),
                "detail_jobs_enqueued": detail_jobs,
                "runtime": "local_agent_runtime_v1",
                "engine_audit": engine_audit_summary(
                    capability_key=self.FEED_CAPABILITY_KEY,
                    surface="homefeed",
                    report=report,
                ),
            },
        )

    async def _run_search_suggest(self, job: ClaimedJobPayload, page) -> JobExecutionResult:
        payload = job.payload
        core_keyword = str(payload.get("core_keyword") or payload.get("keyword") or "").strip()
        items, report = await DouyinSearchSuggestProbe(core_keyword=core_keyword).collect(page)
        ingestion_status = "skipped"
        if items and hasattr(self.client, "ingest_search_suggestions"):
            try:
                await self.client.ingest_search_suggestions(
                    {
                        "job_id": job.job_id,
                        "account_id": job.account_id,
                        "platform": Platform.DOUYIN.value,
                        "core_keyword": core_keyword,
                        "items": items,
                    }
                )
                ingestion_status = "ok"
            except Exception:
                # Central endpoint may not be deployed yet; keep the words in the
                # result summary so the run is not lost, and report degraded.
                ingestion_status = "failed"
        return _job_execution_result(
            status=JobStatus.SUCCESS.value,
            checkpoint={"suggestion_count": len(items)},
            result_summary={
                **report,
                "platform": Platform.DOUYIN.value,
                "core_keyword": core_keyword,
                "suggestion_count": len(items),
                "ingestion_status": ingestion_status,
                "items": items,
                "runtime": "local_agent_runtime_v1",
            },
        )

    async def _run_detail(self, job: ClaimedJobPayload, page) -> JobExecutionResult:
        payload = job.payload
        snapshot = await DouyinDetailProbe().fetch_detail(
            page,
            platform_content_id=payload.get("platform_content_id"),
            canonical_url=payload.get("canonical_url"),
            platform_context=payload.get("platform_context") or {},
        )
        ingestion = await self.client.ingest_detail(
            DetailIngestionRequest(
                job_id=job.job_id,
                content_id=payload["content_id"],
                snapshot=snapshot,
            )
        )
        diagnostics = (snapshot.raw_payload or {}).get("diagnostics") or {}
        return _job_execution_result(
            status=JobStatus.SUCCESS.value,
            checkpoint={"snapshot_id": ingestion.get("snapshot_id")},
            result_summary={
                "snapshot_id": ingestion.get("snapshot_id"),
                "comment_job_enqueued": ingestion.get("comment_job_enqueued"),
                "platform": Platform.DOUYIN.value,
                "runtime": "local_agent_runtime_v1",
                "engine_audit": engine_audit_summary(
                    capability_key="douyin.note.detail",
                    surface="detail",
                    report=diagnostics,
                ),
            },
        )

    async def _run_comment(self, job: ClaimedJobPayload, page) -> JobExecutionResult:
        payload = job.payload
        result = await DouyinCommentProbe().fetch_comments_result(
            page,
            platform_content_id=payload.get("platform_content_id"),
            canonical_url=payload.get("canonical_url"),
            limit=int(payload.get("max_comments") or 20),
        )
        if result.surface_status == "comment_surface_unavailable":
            return _job_execution_result(
                status=JobStatus.PARTIAL_SUCCESS.value,
                result_summary={
                    "error_code": ErrorCode.COMMENT_SURFACE_UNAVAILABLE.value,
                    "surface_status": result.surface_status,
                    "message": result.message,
                    "diagnostics": result.diagnostics,
                    "platform": Platform.DOUYIN.value,
                    "runtime": "local_agent_runtime_v1",
                },
            )
        ingestion = await self.client.ingest_comments(
            CommentIngestionRequest(
                job_id=job.job_id,
                content_id=payload["content_id"],
                comments=result.comments,
            )
        )
        return _job_execution_result(
            status=JobStatus.SUCCESS.value,
            checkpoint={"comments_seen": len(result.comments)},
            result_summary={
                "comments_inserted": ingestion.get("inserted"),
                "comments_updated": ingestion.get("updated"),
                "lead_keyword_hits": ingestion.get("lead_keyword_hits"),
                "surface_status": result.surface_status,
                "platform": Platform.DOUYIN.value,
                "runtime": "local_agent_runtime_v1",
            },
        )

    async def _run_creator_monitor(self, job: ClaimedJobPayload, page) -> JobExecutionResult:
        payload = job.payload
        try:
            result = await DouyinCreatorProbe().fetch_latest(
                page,
                creator_profile_url=payload.get("creator_profile_url"),
                creator_platform_id=payload.get("creator_platform_id"),
                limit=int(payload.get("max_latest_items") or 20),
            )
        except ValueError as exc:
            raise _runtime_failure(
                ErrorCode.NON_RETRYABLE_PLATFORM_ERROR,
                str(exc),
                raw_context={
                    "creator_profile_url": payload.get("creator_profile_url"),
                    "creator_platform_id": payload.get("creator_platform_id"),
                },
            ) from exc
        ingestion = await self.client.ingest_creator_monitor_items(
            CreatorMonitorIngestionRequest(
                job_id=job.job_id,
                account_id=job.account_id,
                creator_monitor_id=payload["creator_monitor_id"],
                creator_display_name=result.creator_display_name,
                items=result.items,
                raw_payload=result.raw_payload,
            )
        )
        return _job_execution_result(
            status=JobStatus.SUCCESS.value,
            checkpoint={
                "items_seen": ingestion.get("items_seen"),
                "creator_platform_id": result.creator_platform_id,
            },
            result_summary={
                **ingestion,
                "creator_platform_id": result.creator_platform_id,
                "creator_display_name": result.creator_display_name,
                "profile": result.profile,
                "platform": Platform.DOUYIN.value,
                "runtime": "local_agent_runtime_v1",
            },
        )


