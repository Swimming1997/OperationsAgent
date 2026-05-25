# legacy DB-coupled smoke tool; not part of the formal Local Agent Runtime.
import httpx

from intelligence_engine.domain.enums import SessionStatus
from intelligence_engine.domain.schemas import FeedCandidateIngestionRequest
from intelligence_engine.connectors.xhs.homefeed_probe import XhsHomeFeedProbe
from intelligence_engine.sessions.xhs_browser_session import XhsBrowserSessionProvider


class XhsProbeRunner:
    def __init__(self, *, center_base_url: str = "http://127.0.0.1:8000"):
        self.center_base_url = center_base_url.rstrip("/")

    async def run(
        self,
        *,
        job_id: str,
        account_id: str,
        session_meta: dict,
        target_count: int = 50,
        post_ingestion: bool = True,
    ) -> dict:
        session = await XhsBrowserSessionProvider().acquire(session_meta=session_meta)
        if session.status != SessionStatus.READY:
            await session.close()
            return {"session_status": session.status.value, "session_message": session.message, "ingestion": None}
        try:
            candidates, report = await XhsHomeFeedProbe(target_count=target_count).collect(session.page)
            ingestion = None
            if post_ingestion and candidates:
                payload = FeedCandidateIngestionRequest(job_id=job_id, account_id=account_id, candidates=candidates)
                async with httpx.AsyncClient(timeout=30) as client:
                    response = await client.post(
                        f"{self.center_base_url}/api/ingestion/feed-candidates",
                        json=payload.model_dump(mode="json"),
                    )
                    response.raise_for_status()
                    ingestion = response.json()
                report["ingestion_unique_count"] = sum(1 for item in ingestion["results"] if item["is_new_content"])
                report["ingestion_detail_jobs_enqueued"] = sum(1 for item in ingestion["results"] if item["detail_job_enqueued"])
            return {
                "session_status": session.status.value,
                "session_message": session.message,
                "report": report,
                "ingestion": ingestion,
            }
        finally:
            await session.close()
