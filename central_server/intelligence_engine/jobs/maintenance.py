from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from intelligence_engine.config import get_settings
from intelligence_engine.services.account_login_service import AccountLoginService
from intelligence_engine.services.task_materialization import TaskMaterializationService
from intelligence_engine.storage.repositories.job_repository import JobRepository


@dataclass(frozen=True)
class MaintenanceResult:
    expired_claim_count: int
    stale_running_failed_count: int
    stale_running_requeued_count: int
    expired_login_session_count: int
    task_run_refreshed_count: int
    dry_run: bool = False

    def as_dict(self) -> dict[str, int | bool]:
        return {
            "dry_run": self.dry_run,
            "expired_claim_count": self.expired_claim_count,
            "stale_running_failed_count": self.stale_running_failed_count,
            "stale_running_requeued_count": self.stale_running_requeued_count,
            "expired_login_session_count": self.expired_login_session_count,
            "task_run_refreshed_count": self.task_run_refreshed_count,
        }


class JobMaintenanceService:
    def __init__(self, db: Session):
        self.db = db

    def run_once(self, *, dry_run: bool = False) -> MaintenanceResult:
        if dry_run:
            return MaintenanceResult(
                expired_claim_count=0,
                stale_running_failed_count=0,
                stale_running_requeued_count=0,
                expired_login_session_count=0,
                task_run_refreshed_count=0,
                dry_run=True,
            )
        settings = get_settings()
        job_repo = JobRepository(self.db)
        expired_claims = job_repo.requeue_expired_claims()
        stale_running, stale_requeued = job_repo.recover_stale_running_jobs(
            max_running_seconds=settings.job_running_timeout_seconds
        )
        expired_login_sessions = AccountLoginService(self.db).expire_stale_sessions()
        refreshed_runs = TaskMaterializationService(self.db).refresh_active_task_runs()
        self.db.flush()
        return MaintenanceResult(
            expired_claim_count=expired_claims,
            stale_running_failed_count=stale_running,
            stale_running_requeued_count=stale_requeued,
            expired_login_session_count=expired_login_sessions,
            task_run_refreshed_count=refreshed_runs,
        )
