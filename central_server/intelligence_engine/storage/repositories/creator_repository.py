from sqlalchemy import select
from sqlalchemy.orm import Session

from intelligence_engine.db.models import CreatorMonitor, CreatorMonitorEvent, utcnow
from intelligence_engine.domain.enums import JobType
from intelligence_engine.storage.repositories.job_repository import JobRepository


class CreatorMonitorRepository:
    def __init__(self, db: Session):
        self.db = db

    def create_monitor(
        self,
        *,
        platform: str,
        creator_platform_id: str,
        creator_display_name: str | None,
        monitor_group_key: str | None,
        mapped_business_account_type: str | None,
        check_interval_seconds: int,
    ) -> CreatorMonitor:
        monitor = CreatorMonitor(
            platform=platform,
            creator_platform_id=creator_platform_id,
            creator_display_name=creator_display_name,
            monitor_group_key=monitor_group_key,
            mapped_business_account_type=mapped_business_account_type,
            check_interval_seconds=check_interval_seconds,
        )
        self.db.add(monitor)
        self.db.flush()
        return monitor

    def list_monitors(self) -> list[CreatorMonitor]:
        return list(self.db.scalars(select(CreatorMonitor).order_by(CreatorMonitor.created_at.desc())))

    def enqueue_monitor_job(self, *, monitor: CreatorMonitor, priority: int = 100):
        return JobRepository(self.db).create_job(
            job_type=JobType.CREATOR_MONITOR,
            creator_monitor_id=monitor.id,
            payload={
                "creator_monitor_id": monitor.id,
                "platform": monitor.platform,
                "creator_platform_id": monitor.creator_platform_id,
                "creator_profile_url": (monitor.metadata_json or {}).get("creator_profile_url") or (monitor.metadata_json or {}).get("profile_url"),
                "platform_context": (monitor.metadata_json or {}).get("platform_context", {}),
                "max_latest_items": 20,
            },
            priority=priority,
        )

    def add_event(self, *, monitor_id: str, event_type: str, content_id: str | None = None, payload: dict | None = None) -> CreatorMonitorEvent:
        event = CreatorMonitorEvent(
            creator_monitor_id=monitor_id,
            content_id=content_id,
            event_type=event_type,
            event_payload_json=payload or {},
            created_at=utcnow(),
        )
        self.db.add(event)
        self.db.flush()
        return event
