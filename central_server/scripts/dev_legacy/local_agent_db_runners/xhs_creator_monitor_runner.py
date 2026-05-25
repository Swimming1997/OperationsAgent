# legacy DB-coupled smoke tool; not part of the formal Local Agent Runtime.
from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from intelligence_engine.connectors.xhs.creator import XhsCreatorConnector, parse_xhs_creator_context
from intelligence_engine.db.models import CreatorMonitor
from intelligence_engine.domain.enums import JobType, Platform, SessionStatus
from intelligence_engine.sessions.xhs_browser_session import XhsBrowserSessionProvider
from intelligence_engine.storage.repositories.content_repository import ContentRepository
from intelligence_engine.storage.repositories.creator_repository import CreatorMonitorRepository
from intelligence_engine.storage.repositories.job_repository import JobRepository


class XhsCreatorMonitorRunner:
    def __init__(self, *, db: Session):
        self.db = db

    def ensure_monitor_from_url(self, creator_url: str) -> CreatorMonitor:
        context = parse_xhs_creator_context(creator_url)
        monitor = self.db.scalar(
            select(CreatorMonitor).where(
                CreatorMonitor.platform == Platform.XHS.value,
                CreatorMonitor.creator_platform_id == context.creator_platform_id,
            )
        )
        metadata = {"profile_url": creator_url, "platform_context": context.to_payload()}
        if monitor:
            existing = dict(monitor.metadata_json or {})
            existing.update(metadata)
            monitor.metadata_json = existing
            return monitor
        monitor = CreatorMonitorRepository(self.db).create_monitor(
            platform=Platform.XHS.value,
            creator_platform_id=context.creator_platform_id,
            creator_display_name=None,
            monitor_group_key="xhs_probe",
            mapped_business_account_type=None,
            check_interval_seconds=900,
        )
        monitor.metadata_json = metadata
        return monitor

    async def run_urls(self, *, creator_urls: list[str], session_meta: dict[str, Any], limit_per_creator: int = 20) -> dict[str, Any]:
        monitors = [self.ensure_monitor_from_url(url) for url in creator_urls]
        self.db.commit()
        results = []
        for monitor in monitors:
            results.append(await self.run_monitor(monitor=monitor, session_meta=session_meta, limit=limit_per_creator))
        return self._summarize(results)

    async def run_monitor(self, *, monitor: CreatorMonitor, session_meta: dict[str, Any], limit: int = 20) -> dict[str, Any]:
        profile_url = (monitor.metadata_json or {}).get("profile_url") or monitor.creator_platform_id
        session = await XhsBrowserSessionProvider().acquire(session_meta=session_meta)
        if session.status != SessionStatus.READY:
            await session.close()
            return {
                "creator_platform_id": monitor.creator_platform_id,
                "success": False,
                "error": session.message,
                "items_seen": 0,
                "new_content_count": 0,
                "duplicate_content_count": 0,
                "detail_job_enqueue_count": 0,
                "xsec_context_success_count": 0,
                "items": [],
            }
        try:
            fetch_result = await XhsCreatorConnector().fetch_latest(
                session.page,
                creator_profile_url=profile_url,
                limit=limit,
            )
            monitor_job = JobRepository(self.db).create_job(
                job_type=JobType.CREATOR_MONITOR,
                creator_monitor_id=monitor.id,
                payload={"creator_monitor_id": monitor.id, "platform": monitor.platform, "source": "xhs_creator_monitor_probe"},
                priority=70,
            )
            if fetch_result.creator_display_name:
                monitor.creator_display_name = fetch_result.creator_display_name
            creator_repo = CreatorMonitorRepository(self.db)
            content_repo = ContentRepository(self.db)
            new_count = 0
            duplicate_count = 0
            detail_jobs = 0
            items_summary = []
            for index, item in enumerate(fetch_result.items, start=1):
                candidate = item.to_candidate(feed_position=index)
                content, is_new, _event, detail_enqueued, _prelim = content_repo.ingest_feed_candidate(
                    job_id=monitor_job.id,
                    account_id=None,
                    candidate=candidate,
                    enqueue_detail_job=True,
                )
                if is_new:
                    new_count += 1
                    creator_repo.add_event(
                        monitor_id=monitor.id,
                        content_id=content.id,
                        event_type="new_content_detected",
                        payload={
                            "platform_content_id": content.platform_content_id,
                            "canonical_url": content.canonical_url,
                            "platform_context": item.platform_context,
                        },
                    )
                else:
                    duplicate_count += 1
                if detail_enqueued:
                    detail_jobs += 1
                items_summary.append(
                    {
                        "content_id": content.id,
                        "platform_content_id": item.platform_content_id,
                        "title_or_summary": item.title_or_summary,
                        "canonical_url": item.canonical_url,
                        "cover_url": item.cover_url,
                        "publish_time": item.publish_time.isoformat() if item.publish_time else None,
                        "has_xsec_context": item.platform_context.get("has_xsec_context", False),
                    }
                )
            creator_repo.add_event(
                monitor_id=monitor.id,
                event_type="monitor_run_success",
                payload={"items_seen": len(fetch_result.items), "new_contents_detected": new_count},
            )
            monitor.last_cursor_json = {"last_seen_platform_content_ids": [item.platform_content_id for item in fetch_result.items]}
            self.db.commit()
            return {
                "creator_platform_id": monitor.creator_platform_id,
                "creator_display_name": monitor.creator_display_name,
                "success": True,
                "items_seen": len(fetch_result.items),
                "new_content_count": new_count,
                "duplicate_content_count": duplicate_count,
                "detail_job_enqueue_count": detail_jobs,
                "xsec_context_success_count": sum(1 for item in fetch_result.items if item.platform_context.get("has_xsec_context")),
                "items": items_summary,
            }
        except Exception as exc:
            self.db.rollback()
            return {
                "creator_platform_id": monitor.creator_platform_id,
                "success": False,
                "error": str(exc),
                "items_seen": 0,
                "new_content_count": 0,
                "duplicate_content_count": 0,
                "detail_job_enqueue_count": 0,
                "xsec_context_success_count": 0,
                "items": [],
            }
        finally:
            await session.close()

    def _summarize(self, results: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "selected_creator_count": len(results),
            "success_count": sum(1 for result in results if result.get("success")),
            "failed_count": sum(1 for result in results if not result.get("success")),
            "creator_items_seen": sum(int(result.get("items_seen", 0)) for result in results),
            "new_content_count": sum(int(result.get("new_content_count", 0)) for result in results),
            "duplicate_content_count": sum(int(result.get("duplicate_content_count", 0)) for result in results),
            "detail_job_enqueue_count": sum(int(result.get("detail_job_enqueue_count", 0)) for result in results),
            "xsec_context_success_count": sum(int(result.get("xsec_context_success_count", 0)) for result in results),
            "creators": results,
        }
