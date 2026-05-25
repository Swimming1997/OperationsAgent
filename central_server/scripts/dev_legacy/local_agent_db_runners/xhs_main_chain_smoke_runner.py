# legacy DB-coupled smoke tool; not part of the formal Local Agent Runtime.
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from intelligence_engine.connectors.xhs.comment_normalizer import comment_keyword_hits
from intelligence_engine.connectors.xhs.comment_probe import XhsCommentProbe
from intelligence_engine.connectors.xhs.detail_probe import XhsDetailProbe
from intelligence_engine.db.models import CommentSnapshot, ContentIdentity, ContentSnapshot, Job, JobEvent, utcnow
from intelligence_engine.domain.enums import ErrorCode, JobStatus, JobType, SessionStatus
from intelligence_engine.domain.schemas import CommentIngestionRequest, DetailIngestionRequest, ErrorPayload, JobFailRequest
from intelligence_engine.local_agent.xhs_probe_runner import XhsProbeRunner
from intelligence_engine.sessions.xhs_browser_session import XhsBrowserSessionProvider


SMOKE_AGENT_ID = "xhs-main-chain-smoke-runner"


def has_xhs_xsec_context(payload: dict[str, Any] | None) -> bool:
    context = (payload or {}).get("platform_context") or {}
    return bool(context.get("xsec_token") and context.get("xsec_source"))


def context_loss_layers(
    *,
    homefeed_sample_count: int,
    homefeed_with_xsec_context_count: int,
    detail_selected_count: int,
    detail_with_xsec_context_count: int,
    comment_selected_count: int,
    comment_with_xsec_context_count: int,
) -> list[str]:
    layers: list[str] = []
    if homefeed_sample_count and homefeed_with_xsec_context_count < homefeed_sample_count:
        layers.append("homefeed_candidate")
    if detail_selected_count and detail_with_xsec_context_count < detail_selected_count:
        layers.append("detail_job_payload")
    if comment_selected_count and comment_with_xsec_context_count < comment_selected_count:
        layers.append("comment_job_payload")
    return layers


class XhsMainChainSmokeRunner:
    def __init__(self, *, db: Session, center_base_url: str = "http://127.0.0.1:8000"):
        self.db = db
        self.center_base_url = center_base_url.rstrip("/")

    async def run(
        self,
        *,
        job_id: str,
        account_id: str,
        session_meta: dict[str, Any],
        homefeed_target_count: int = 10,
        detail_limit: int = 5,
        comment_limit: int = 5,
        max_comments: int = 20,
        post_ingestion: bool = True,
    ) -> dict[str, Any]:
        await self._assert_center_ready()
        run_started_at = utcnow()
        homefeed_result = await XhsProbeRunner(center_base_url=self.center_base_url).run(
            job_id=job_id,
            account_id=account_id,
            session_meta=session_meta,
            target_count=homefeed_target_count,
            post_ingestion=post_ingestion,
        )
        homefeed_report = homefeed_result.get("report") or {}
        ingestion = homefeed_result.get("ingestion") or {}
        ingestion_results = ingestion.get("results") or []
        content_ids = [item["content_id"] for item in ingestion_results if item.get("detail_job_enqueued")]

        self.db.expire_all()
        detail_jobs = self._select_jobs_for_contents(
            job_type=JobType.DETAIL_FETCH,
            content_ids=content_ids,
            created_after=run_started_at,
            limit=detail_limit,
        )
        detail_with_context = sum(1 for job in detail_jobs if has_xhs_xsec_context(job.payload_json))
        detail_result = await self._run_detail_jobs(
            jobs=detail_jobs,
            session_meta=session_meta,
            post_ingestion=post_ingestion,
        )

        self.db.expire_all()
        successful_detail_content_ids = [item["content_id"] for item in detail_result["successes"]]
        comment_jobs = self._select_jobs_for_contents(
            job_type=JobType.COMMENT_FETCH,
            content_ids=successful_detail_content_ids,
            created_after=run_started_at,
            limit=comment_limit,
        )
        comment_with_context = sum(1 for job in comment_jobs if has_xhs_xsec_context(job.payload_json))
        comment_result = await self._run_comment_jobs(
            jobs=comment_jobs,
            session_meta=session_meta,
            max_comments=max_comments,
            post_ingestion=post_ingestion,
        )

        homefeed_with_xsec = int((homefeed_report.get("xhs_context_success") or {}).get("count") or 0)
        missing_xsec_count = comment_result["missing_xsec_context_count"]
        surface_unavailable_count = comment_result["comment_surface_unavailable_count"]
        homefeed_sample_count = int(homefeed_report.get("actual_count", 0) or 0)
        loss_layers = context_loss_layers(
            homefeed_sample_count=homefeed_sample_count,
            homefeed_with_xsec_context_count=homefeed_with_xsec,
            detail_selected_count=len(detail_jobs),
            detail_with_xsec_context_count=detail_with_context,
            comment_selected_count=len(comment_jobs),
            comment_with_xsec_context_count=comment_with_context,
        )
        main_chain_established = (
            homefeed_sample_count >= homefeed_target_count
            and homefeed_with_xsec == homefeed_sample_count
            and len(detail_jobs) > 0
            and detail_result["success_count"] == len(detail_jobs)
            and len(comment_jobs) > 0
            and comment_result["success_count"] > 0
            and missing_xsec_count == 0
            and not loss_layers
        )

        return {
            "account_id": account_id,
            "feed_job_id": job_id,
            "session_status": homefeed_result.get("session_status"),
            "session_message": homefeed_result.get("session_message"),
            "homefeed_sample_count": homefeed_sample_count,
            "homefeed_with_xsec_context_count": homefeed_with_xsec,
            "homefeed_ingestion_success_count": len(ingestion_results),
            "homefeed_detail_job_enqueue_count": sum(1 for item in ingestion_results if item.get("detail_job_enqueued")),
            "detail_selected_count": len(detail_jobs),
            "detail_job_with_xsec_context_count": detail_with_context,
            "detail_success_count": detail_result["success_count"],
            "detail_failed_count": detail_result["failed_count"],
            "detail_snapshot_count": detail_result["snapshot_count"],
            "comment_selected_count": len(comment_jobs),
            "comment_job_with_xsec_context_count": comment_with_context,
            "comment_success_count": comment_result["success_count"],
            "comment_failed_count": comment_result["failed_count"],
            "comment_snapshot_count": comment_result["comment_snapshot_count"],
            "missing_xsec_context_count": missing_xsec_count,
            "comment_surface_unavailable_count": surface_unavailable_count,
            "keyword_hits": comment_result["keyword_hits"],
            "context_loss_layers": loss_layers,
            "context_assertions": {
                "homefeed_all_selected_have_xsec_context": homefeed_sample_count > 0 and homefeed_with_xsec == homefeed_sample_count,
                "detail_jobs_all_have_xsec_context": len(detail_jobs) > 0 and detail_with_context == len(detail_jobs),
                "comment_jobs_all_have_xsec_context": len(comment_jobs) > 0 and comment_with_context == len(comment_jobs),
                "missing_xsec_context_count_is_zero": missing_xsec_count == 0,
            },
            "xhs_main_chain_established": main_chain_established,
            "detail_failures": detail_result["failures"],
            "comment_failures": comment_result["failures"],
        }

    async def _assert_center_ready(self) -> None:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(f"{self.center_base_url}/api/health")
            response.raise_for_status()

    def _select_jobs_for_contents(
        self,
        *,
        job_type: JobType,
        content_ids: list[str],
        created_after: datetime,
        limit: int,
    ) -> list[Job]:
        if not content_ids:
            return []
        stmt = (
            select(Job)
            .where(Job.job_type == job_type.value)
            .where(Job.payload_json["content_id"].as_string().in_(content_ids))
            .where(Job.created_at >= created_after)
            .where(Job.status.in_([JobStatus.PENDING.value, JobStatus.CLAIMED.value, JobStatus.RUNNING.value]))
            .order_by(Job.created_at.asc())
            .limit(limit)
        )
        return list(self.db.scalars(stmt))

    def _prepare_job_for_start(self, job: Job, *, agent_id: str) -> None:
        if job.status == JobStatus.PENDING.value:
            job.status = JobStatus.CLAIMED.value
            job.claimed_by_agent_id = agent_id
            job.claimed_at = utcnow()
            job.claim_expires_at = None
            job.updated_at = job.claimed_at
            self.db.add(JobEvent(job_id=job.id, event_type="job_claimed", event_payload_json={"agent_id": agent_id, "source": "xhs_smoke"}))
            self.db.commit()

    async def _run_detail_jobs(self, *, jobs: list[Job], session_meta: dict[str, Any], post_ingestion: bool) -> dict[str, Any]:
        if not jobs:
            return {"success_count": 0, "failed_count": 0, "snapshot_count": 0, "successes": [], "failures": []}
        session = await XhsBrowserSessionProvider().acquire(session_meta=session_meta)
        if session.status != SessionStatus.READY:
            await session.close()
            return {
                "success_count": 0,
                "failed_count": len(jobs),
                "snapshot_count": 0,
                "successes": [],
                "failures": [{"job_id": job.id, "error": session.message} for job in jobs],
            }
        successes: list[dict[str, Any]] = []
        failures: list[dict[str, Any]] = []
        try:
            probe = XhsDetailProbe()
            async with httpx.AsyncClient(timeout=30) as client:
                for job in jobs:
                    content = self.db.get(ContentIdentity, job.payload_json.get("content_id"))
                    canonical_url = job.payload_json.get("canonical_url") or (content.canonical_url if content else None)
                    platform_content_id = job.payload_json.get("platform_content_id") or (content.platform_content_id if content else None)
                    platform_context = job.payload_json.get("platform_context") or ((content.metadata_json or {}).get("platform_context") if content else {}) or {}
                    if not content or not canonical_url or not platform_content_id:
                        failures.append({"job_id": job.id, "error": "missing content/canonical_url/platform_content_id"})
                        continue
                    try:
                        snapshot = await probe.fetch_detail(
                            session.page,
                            canonical_url=canonical_url,
                            platform_content_id=platform_content_id,
                            platform_context=platform_context,
                        )
                        ingestion = None
                        if post_ingestion:
                            await self._ensure_job_running(client, job)
                            payload = DetailIngestionRequest(job_id=job.id, content_id=content.id, snapshot=snapshot)
                            response = await client.post(
                                f"{self.center_base_url}/api/ingestion/content-detail",
                                json=payload.model_dump(mode="json"),
                            )
                            response.raise_for_status()
                            ingestion = response.json()
                            complete_response = await client.post(
                                f"{self.center_base_url}/api/jobs/{job.id}/complete",
                                json={
                                    "agent_id": SMOKE_AGENT_ID,
                                    "status": "success",
                                    "result_summary": {
                                        "snapshot_id": ingestion.get("snapshot_id"),
                                        "comment_job_enqueued": ingestion.get("comment_job_enqueued"),
                                        "probe": "xhs_main_chain_smoke_detail",
                                    },
                                },
                            )
                            complete_response.raise_for_status()
                        successes.append({"job_id": job.id, "content_id": content.id, "snapshot_ingested": bool(ingestion)})
                    except Exception as exc:
                        failures.append({"job_id": job.id, "content_id": content.id if content else None, "error": str(exc)})
            content_ids = [item["content_id"] for item in successes]
            snapshot_count = 0
            if content_ids:
                snapshot_count = self.db.scalar(select(func.count(ContentSnapshot.id)).where(ContentSnapshot.content_id.in_(content_ids))) or 0
            return {
                "success_count": len(successes),
                "failed_count": len(failures),
                "snapshot_count": snapshot_count,
                "successes": successes,
                "failures": failures,
            }
        finally:
            await session.close()

    async def _run_comment_jobs(
        self,
        *,
        jobs: list[Job],
        session_meta: dict[str, Any],
        max_comments: int,
        post_ingestion: bool,
    ) -> dict[str, Any]:
        if not jobs:
            return {
                "success_count": 0,
                "failed_count": 0,
                "comment_snapshot_count": 0,
                "missing_xsec_context_count": 0,
                "comment_surface_unavailable_count": 0,
                "keyword_hits": [],
                "successes": [],
                "failures": [],
            }
        session = await XhsBrowserSessionProvider().acquire(session_meta=session_meta)
        if session.status != SessionStatus.READY:
            await session.close()
            return {
                "success_count": 0,
                "failed_count": len(jobs),
                "comment_snapshot_count": 0,
                "missing_xsec_context_count": 0,
                "comment_surface_unavailable_count": 0,
                "keyword_hits": [],
                "successes": [],
                "failures": [{"job_id": job.id, "error": session.message} for job in jobs],
            }
        successes: list[dict[str, Any]] = []
        failures: list[dict[str, Any]] = []
        hit_keywords: list[str] = []
        missing_xsec_count = 0
        surface_unavailable_count = 0
        try:
            probe = XhsCommentProbe()
            async with httpx.AsyncClient(timeout=30) as client:
                for job in jobs:
                    content = self.db.get(ContentIdentity, job.payload_json.get("content_id"))
                    canonical_url = job.payload_json.get("canonical_url") or (content.canonical_url if content else None)
                    platform_content_id = job.payload_json.get("platform_content_id") or (content.platform_content_id if content else None)
                    platform_context = job.payload_json.get("platform_context") or ((content.metadata_json or {}).get("platform_context") if content else {}) or {}
                    if not content or not canonical_url or not platform_content_id:
                        failures.append({"job_id": job.id, "error": "missing content/canonical_url/platform_content_id"})
                        continue
                    try:
                        fetch_result = await probe.fetch_comments_result(
                            session.page,
                            canonical_url=canonical_url,
                            platform_content_id=platform_content_id,
                            platform_context=platform_context,
                            limit=int(job.payload_json.get("max_comments") or max_comments),
                        )
                        if post_ingestion:
                            await self._ensure_job_running(client, job)
                        if fetch_result.surface_status == "missing_xsec_context":
                            missing_xsec_count += 1
                            if post_ingestion:
                                await self._post_job_fail(client, job, ErrorCode.MISSING_XSEC_CONTEXT.value, fetch_result.message or "missing xsec context", fetch_result.diagnostics)
                            failures.append({"job_id": job.id, "content_id": content.id, "surface_status": fetch_result.surface_status, "error_code": ErrorCode.MISSING_XSEC_CONTEXT.value})
                            continue
                        if fetch_result.surface_status == "comment_surface_unavailable":
                            surface_unavailable_count += 1
                            if post_ingestion:
                                await self._post_job_partial_success(client, job, ErrorCode.COMMENT_SURFACE_UNAVAILABLE.value, fetch_result.message or "comment surface unavailable", fetch_result.diagnostics)
                            failures.append({"job_id": job.id, "content_id": content.id, "surface_status": fetch_result.surface_status, "error_code": ErrorCode.COMMENT_SURFACE_UNAVAILABLE.value})
                            continue
                        if fetch_result.surface_status in {"manual_verify_required", "login_required"}:
                            error_code = fetch_result.error_code or ErrorCode.SESSION_EXPIRED.value
                            if post_ingestion:
                                await self._post_job_fail(client, job, error_code, fetch_result.message or fetch_result.surface_status, fetch_result.diagnostics)
                            failures.append({"job_id": job.id, "content_id": content.id, "surface_status": fetch_result.surface_status, "error_code": error_code})
                            continue

                        comments = fetch_result.comments
                        hits = comment_keyword_hits(comments)
                        for hit in hits:
                            if hit not in hit_keywords:
                                hit_keywords.append(hit)
                        ingestion = None
                        if post_ingestion:
                            payload = CommentIngestionRequest(job_id=job.id, content_id=content.id, comments=comments)
                            response = await client.post(
                                f"{self.center_base_url}/api/ingestion/comments",
                                json=payload.model_dump(mode="json"),
                            )
                            response.raise_for_status()
                            ingestion = response.json()
                            complete_response = await client.post(
                                f"{self.center_base_url}/api/jobs/{job.id}/complete",
                                json={
                                    "agent_id": SMOKE_AGENT_ID,
                                    "status": "success",
                                    "result_summary": {
                                        "comments_inserted": ingestion.get("inserted"),
                                        "comments_updated": ingestion.get("updated"),
                                        "lead_keyword_hits": ingestion.get("lead_keyword_hits"),
                                        "probe": "xhs_main_chain_smoke_comment",
                                    },
                                },
                            )
                            complete_response.raise_for_status()
                        successes.append({"job_id": job.id, "content_id": content.id, "comment_count": len(comments), "keyword_hits": hits})
                    except Exception as exc:
                        failures.append({"job_id": job.id, "content_id": content.id if content else None, "error": str(exc)})
            content_ids = [item["content_id"] for item in successes]
            snapshot_count = 0
            if content_ids:
                snapshot_count = self.db.scalar(select(func.count(CommentSnapshot.id)).where(CommentSnapshot.content_id.in_(content_ids))) or 0
            return {
                "success_count": len(successes),
                "failed_count": len(failures),
                "comment_snapshot_count": snapshot_count,
                "missing_xsec_context_count": missing_xsec_count,
                "comment_surface_unavailable_count": surface_unavailable_count,
                "keyword_hits": hit_keywords,
                "successes": successes,
                "failures": failures,
            }
        finally:
            await session.close()

    async def _ensure_job_running(self, client: httpx.AsyncClient, job: Job) -> None:
        self._prepare_job_for_start(job, agent_id=SMOKE_AGENT_ID)
        if job.status == JobStatus.RUNNING.value:
            return
        response = await client.post(f"{self.center_base_url}/api/jobs/{job.id}/start", json={"agent_id": SMOKE_AGENT_ID})
        response.raise_for_status()

    async def _post_job_fail(self, client: httpx.AsyncClient, job: Job, error_code: str, message: str, diagnostics: dict[str, Any]) -> None:
        payload = JobFailRequest(
            agent_id=SMOKE_AGENT_ID,
            error=ErrorPayload(code=error_code, message=message, retryable=False, raw_context=diagnostics),
            checkpoint=job.checkpoint_json,
        ).model_dump(mode="json")
        response = await client.post(
            f"{self.center_base_url}/api/jobs/{job.id}/fail",
            json=payload,
        )
        if response.status_code == 422:
            raise RuntimeError(f"fail API returned 422: body={response.text}; payload={payload}")
        response.raise_for_status()

    async def _post_job_partial_success(self, client: httpx.AsyncClient, job: Job, error_code: str, message: str, diagnostics: dict[str, Any]) -> None:
        response = await client.post(
            f"{self.center_base_url}/api/jobs/{job.id}/complete",
            json={
                "agent_id": SMOKE_AGENT_ID,
                "status": "partial_success",
                "result_summary": {
                    "error_code": error_code,
                    "surface_status": error_code,
                    "message": message,
                    "comments_inserted": 0,
                    "comments_updated": 0,
                    "probe": "xhs_main_chain_smoke_comment",
                    "diagnostics": diagnostics,
                },
            },
        )
        response.raise_for_status()
