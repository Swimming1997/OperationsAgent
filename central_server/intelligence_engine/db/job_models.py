from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, select, text
from sqlalchemy.orm import Mapped, mapped_column, object_session

from intelligence_engine.db.base import Base
from intelligence_engine.db.model_base import JsonType, TimestampMixin, new_uuid, utcnow


class Job(Base, TimestampMixin):
    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    task_run_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("task_runs.id"))
    job_type: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(64), default="pending", nullable=False)
    priority: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    account_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("platform_accounts.id"))
    local_agent_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("local_agents.id"))
    creator_monitor_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("creator_monitors.id"))
    payload_json: Mapped[dict] = mapped_column(JsonType, default=dict, nullable=False)
    checkpoint_json: Mapped[dict] = mapped_column(JsonType, default=dict, nullable=False)
    result_summary_json: Mapped[dict] = mapped_column(JsonType, default=dict, nullable=False)
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_retries: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    last_error_code: Mapped[str | None] = mapped_column(String(128))
    last_error_message: Mapped[str | None] = mapped_column(Text)
    claimed_by_agent_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("local_agents.id"))
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    claim_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class TaskRun(Base, TimestampMixin):
    __tablename__ = "task_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    task_template_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("task_templates.id"), nullable=True)
    trigger_type: Mapped[str] = mapped_column(String(32), nullable=False)
    requested_by_user_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"))
    executor_account_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("platform_accounts.id"))
    task_schedule_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("task_schedules.id"))
    status: Mapped[str] = mapped_column(String(64), default="materialized", nullable=False)
    jobs_total: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    jobs_pending: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    jobs_running: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    jobs_success: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    jobs_failed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    result_summary_json: Mapped[dict] = mapped_column(JsonType, default=dict, nullable=False)
    error_summary_json: Mapped[dict] = mapped_column(JsonType, default=dict, nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class JobEvent(Base):
    __tablename__ = "job_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    job_id: Mapped[str] = mapped_column(String(36), ForeignKey("jobs.id"), nullable=False)
    event_type: Mapped[str] = mapped_column(String(128), nullable=False)
    event_payload_json: Mapped[dict] = mapped_column(JsonType, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class FetchLease(Base):
    __tablename__ = "fetch_leases"
    __table_args__ = (
        Index(
            "uq_fetch_leases_active_resource",
            "resource_type",
            "resource_key",
            unique=True,
            sqlite_where=text("status = 'active'"),
            postgresql_where=text("status = 'active'"),
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    resource_type: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_key: Mapped[str] = mapped_column(String(255), nullable=False)
    owner_job_id: Mapped[str] = mapped_column(String(36), ForeignKey("jobs.id"), nullable=False)
    acquired_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(32), default="active", nullable=False)
