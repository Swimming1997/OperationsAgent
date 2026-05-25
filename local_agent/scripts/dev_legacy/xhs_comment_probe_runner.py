# legacy DB-coupled smoke tool; not part of the formal Local Agent Runtime.
import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from local_agent_runtime.connectors.xhs.comment_normalizer import comment_field_report, comment_keyword_hits
from local_agent_runtime.connectors.xhs.comment_probe import XhsCommentProbe
from intelligence_engine.db.models import CommentSnapshot, ContentIdentity, Job
from local_agent_runtime.enums import ErrorCode, JobStatus, JobType, SessionStatus
from local_agent_runtime.contracts import CommentIngestionRequest
from local_agent_runtime.sessions.xhs_browser_session import XhsBrowserSessionProvider
from intelligence_engine.storage.repositories.job_repository import JobRepository


class XhsCommentProbeRunner:
    def __init__(self, *, db: Session, center_base_url: str = "http://127.0.0.1:8000"):
        self.db = db
        self.center_base_url = center_base_url.rstrip("/")

    def select_comment_jobs(self, *, limit: int = 5) -> list[Job]:
        running_jobs = list(
            self.db.scalars(
                select(Job)
                .where(Job.job_type == JobType.COMMENT_FETCH.value)
                .where(Job.status == JobStatus.RUNNING.value)
                .where(Job.claimed_by_agent_id == "xhs-comment-probe-runner")
                .order_by(Job.created_at.asc())
                .limit(limit)
            )
        )
        if len(running_jobs) >= limit:
            return running_jobs
        claimed = JobRepository(self.db).claim_jobs_for_agent(
            agent_id="xhs-comment-probe-runner",
            supported_job_types=[JobType.COMMENT_FETCH],
            max_jobs=limit - len(running_jobs),
            ttl_seconds=300,
        )
        return running_jobs + claimed

    async def run(self, *, session_meta: dict, limit: int = 5, max_comments: int = 20, post_ingestion: bool = True) -> dict:
        jobs = self.select_comment_jobs(limit=limit)
        if post_ingestion:
            self.db.commit()
        session = await XhsBrowserSessionProvider().acquire(session_meta=session_meta)
        if session.status != SessionStatus.READY:
            await session.close()
            return {
                "session_status": session.status.value,
                "session_message": session.message,
                "selected_job_count": len(jobs),
                "success_count": 0,
                "failed_count": len(jobs),
                "failures": [{"job_id": job.id, "error": session.message} for job in jobs],
            }

        successes = []
        failures = []
        all_comments = []
        hit_keywords: list[str] = []
        hit_content_ids: set[str] = set()
        empty_comment_content_ids: list[str] = []
        surface_unavailable_content_ids: list[str] = []
        surface_unavailable_urls: list[str] = []
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
                        comments = fetch_result.comments
                        if fetch_result.surface_status == "missing_xsec_context":
                            if post_ingestion:
                                if job.status != JobStatus.RUNNING.value:
                                    start_response = await client.post(
                                        f"{self.center_base_url}/api/jobs/{job.id}/start",
                                        json={"agent_id": "xhs-comment-probe-runner"},
                                    )
                                    start_response.raise_for_status()
                                fail_response = await client.post(
                                    f"{self.center_base_url}/api/jobs/{job.id}/fail",
                                    json={
                                        "agent_id": "xhs-comment-probe-runner",
                                        "error": {
                                            "code": ErrorCode.MISSING_XSEC_CONTEXT.value,
                                            "message": fetch_result.message or "missing xsec context",
                                            "retryable": False,
                                            "raw_context": fetch_result.diagnostics,
                                        },
                                        "checkpoint": job.checkpoint_json,
                                    },
                                )
                                fail_response.raise_for_status()
                            failures.append(
                                {
                                    "job_id": job.id,
                                    "content_id": content.id,
                                    "error_code": ErrorCode.MISSING_XSEC_CONTEXT.value,
                                    "surface_status": fetch_result.surface_status,
                                    "message": fetch_result.message,
                                }
                            )
                            continue
                        if fetch_result.surface_status == "comment_surface_unavailable":
                            surface_unavailable_content_ids.append(content.id)
                            surface_unavailable_urls.append(canonical_url)
                            if post_ingestion:
                                if job.status != JobStatus.RUNNING.value:
                                    start_response = await client.post(
                                        f"{self.center_base_url}/api/jobs/{job.id}/start",
                                        json={"agent_id": "xhs-comment-probe-runner"},
                                    )
                                    start_response.raise_for_status()
                                complete_response = await client.post(
                                    f"{self.center_base_url}/api/jobs/{job.id}/complete",
                                    json={
                                        "agent_id": "xhs-comment-probe-runner",
                                        "status": "partial_success",
                                        "result_summary": {
                                            "error_code": ErrorCode.COMMENT_SURFACE_UNAVAILABLE.value,
                                            "surface_status": fetch_result.surface_status,
                                            "message": fetch_result.message,
                                            "comments_inserted": 0,
                                            "comments_updated": 0,
                                            "probe": "xhs_comment",
                                            "diagnostics": fetch_result.diagnostics,
                                        },
                                    },
                                )
                                complete_response.raise_for_status()
                            failures.append(
                                {
                                    "job_id": job.id,
                                    "content_id": content.id,
                                    "error_code": ErrorCode.COMMENT_SURFACE_UNAVAILABLE.value,
                                    "surface_status": fetch_result.surface_status,
                                    "message": fetch_result.message,
                                }
                            )
                            continue
                        if fetch_result.surface_status in {"manual_verify_required", "login_required"}:
                            error_code = fetch_result.error_code or ErrorCode.SESSION_EXPIRED.value
                            if post_ingestion:
                                if job.status != JobStatus.RUNNING.value:
                                    start_response = await client.post(
                                        f"{self.center_base_url}/api/jobs/{job.id}/start",
                                        json={"agent_id": "xhs-comment-probe-runner"},
                                    )
                                    start_response.raise_for_status()
                                fail_response = await client.post(
                                    f"{self.center_base_url}/api/jobs/{job.id}/fail",
                                    json={
                                        "agent_id": "xhs-comment-probe-runner",
                                        "error": {
                                            "code": error_code,
                                            "message": fetch_result.message or fetch_result.surface_status,
                                            "retryable": False,
                                            "raw_context": fetch_result.diagnostics,
                                        },
                                        "checkpoint": job.checkpoint_json,
                                    },
                                )
                                fail_response.raise_for_status()
                            failures.append(
                                {
                                    "job_id": job.id,
                                    "content_id": content.id,
                                    "error_code": error_code,
                                    "surface_status": fetch_result.surface_status,
                                    "message": fetch_result.message,
                                }
                            )
                            continue
                        all_comments.extend(comments)
                        if not comments:
                            empty_comment_content_ids.append(content.id)
                        hits = comment_keyword_hits(comments)
                        for hit in hits:
                            if hit not in hit_keywords:
                                hit_keywords.append(hit)
                        if hits:
                            hit_content_ids.add(content.id)
                        ingestion = None
                        if post_ingestion:
                            if job.status != JobStatus.RUNNING.value:
                                start_response = await client.post(
                                    f"{self.center_base_url}/api/jobs/{job.id}/start",
                                    json={"agent_id": "xhs-comment-probe-runner"},
                                )
                                start_response.raise_for_status()
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
                                    "agent_id": "xhs-comment-probe-runner",
                                    "status": "success",
                                    "result_summary": {
                                        "comments_inserted": ingestion.get("inserted"),
                                        "comments_updated": ingestion.get("updated"),
                                        "lead_keyword_hits": ingestion.get("lead_keyword_hits"),
                                        "probe": "xhs_comment",
                                    },
                                },
                            )
                            complete_response.raise_for_status()
                        successes.append(
                            {
                                "job_id": job.id,
                                "content_id": content.id,
                                "platform_content_id": platform_content_id,
                                "comment_count": len(comments),
                                "surface_status": fetch_result.surface_status,
                                "keyword_hits": hits,
                                "ingested": bool(ingestion),
                            }
                        )
                    except Exception as exc:
                        failures.append({"job_id": job.id, "content_id": content.id, "error": str(exc)})

            content_ids = [item["content_id"] for item in successes]
            snapshot_count = 0
            if content_ids:
                snapshot_count = self.db.scalar(select(func.count(CommentSnapshot.id)).where(CommentSnapshot.content_id.in_(content_ids))) or 0
            return {
                "session_status": session.status.value,
                "session_message": session.message,
                "selected_job_count": len(jobs),
                "success_count": len(successes),
                "failed_count": len(failures),
                "comment_snapshot_count": snapshot_count,
                "field_report": comment_field_report(all_comments),
                "keyword_hits": hit_keywords,
                "keyword_hit_content_count": len(hit_content_ids),
                "empty_comment_content_ids": empty_comment_content_ids,
                "comment_surface_unavailable_content_ids": surface_unavailable_content_ids,
                "comment_surface_unavailable_urls": surface_unavailable_urls,
                "successes": successes,
                "failures": failures,
                "field_notes": {
                    "stable": ["body_text"],
                    "usually_available": ["author_name", "platform_comment_id"],
                    "conditional": ["author_platform_id", "like_count", "created_time"],
                    "not_implemented": ["sub_comments"],
                    "main_failure_points": [
                        "comment DOM class names are unstable",
                        "comments may lazy-load only after scroll",
                        "some notes have closed or empty comments",
                        "runtime state may omit comments until interaction",
                    ],
                },
            }
        finally:
            await session.close()
