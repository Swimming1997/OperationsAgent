# legacy DB-coupled smoke tool; not part of the formal Local Agent Runtime.
import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from intelligence_engine.connectors.xhs.detail_normalizer import detail_field_report
from intelligence_engine.connectors.xhs.detail_probe import XhsDetailProbe
from intelligence_engine.db.models import ContentIdentity, ContentSnapshot, Job
from intelligence_engine.domain.enums import JobStatus, JobType, SessionStatus
from intelligence_engine.domain.schemas import DetailIngestionRequest
from intelligence_engine.sessions.xhs_browser_session import XhsBrowserSessionProvider


class XhsDetailProbeRunner:
    def __init__(self, *, db: Session, center_base_url: str = "http://127.0.0.1:8000"):
        self.db = db
        self.center_base_url = center_base_url.rstrip("/")

    def select_detail_jobs(self, *, limit: int = 5) -> list[Job]:
        return list(
            self.db.scalars(
                select(Job)
                .where(Job.job_type == JobType.DETAIL_FETCH.value)
                .where(Job.status == JobStatus.PENDING.value)
                .order_by(Job.created_at.asc())
                .limit(limit)
            )
        )

    async def run(self, *, session_meta: dict, limit: int = 5, post_ingestion: bool = True) -> dict:
        jobs = self.select_detail_jobs(limit=limit)
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
        snapshots = []
        successes = []
        failures = []
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
                        snapshots.append(snapshot)
                        ingestion = None
                        if post_ingestion:
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
                                    "agent_id": "xhs-detail-probe-runner",
                                    "status": "success",
                                    "result_summary": {
                                        "snapshot_id": ingestion.get("snapshot_id"),
                                        "comment_job_enqueued": ingestion.get("comment_job_enqueued"),
                                        "probe": "xhs_detail",
                                    },
                                },
                            )
                            complete_response.raise_for_status()
                        successes.append(
                            {
                                "job_id": job.id,
                                "content_id": content.id,
                                "platform_content_id": platform_content_id,
                                "snapshot_ingested": bool(ingestion),
                                "comment_job_enqueued": bool(ingestion and ingestion.get("comment_job_enqueued")),
                            }
                        )
                    except Exception as exc:
                        failures.append({"job_id": job.id, "content_id": content.id, "error": str(exc)})
            content_ids = [item["content_id"] for item in successes]
            snapshot_count = 0
            if content_ids:
                snapshot_count = self.db.scalar(select(func.count(ContentSnapshot.id)).where(ContentSnapshot.content_id.in_(content_ids))) or 0
            return {
                "session_status": session.status.value,
                "session_message": session.message,
                "selected_job_count": len(jobs),
                "success_count": len(successes),
                "failed_count": len(failures),
                "field_report": detail_field_report(snapshots),
                "snapshot_count_for_successes": snapshot_count,
                "comment_job_enqueue_count": sum(1 for item in successes if item["comment_job_enqueued"]),
                "successes": successes,
                "failures": failures,
                "field_notes": {
                    "stable_on_detail_page": ["title", "body_text", "author_name", "image_urls", "cover_url"],
                    "often_available_from_state": ["author_platform_id", "like_count", "comment_count", "collect_count", "publish_time"],
                    "conditional": ["author_avatar_url", "share_count", "video_url"],
                    "main_failure_points": [
                        "login or manual verification overlay",
                        "XHS runtime state shape changes",
                        "detail page blocked or note unavailable",
                        "video source hidden behind runtime player state",
                    ],
                },
            }
        finally:
            await session.close()
