from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON
from sqlalchemy.dialects.postgresql import JSONB

from intelligence_engine.db.base import Base

JsonType = JSON().with_variant(JSONB, "postgresql")


def new_uuid() -> str:
    return str(uuid4())


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        onupdate=utcnow,
        nullable=False,
    )


class User(Base, TimestampMixin):
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("username", name="uq_users_username"),
        Index(
            "uq_users_email_not_null",
            "email",
            unique=True,
            sqlite_where=text("email IS NOT NULL"),
            postgresql_where=text("email IS NOT NULL"),
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    username: Mapped[str] = mapped_column(String(128), nullable=False)
    display_name: Mapped[str] = mapped_column(String(128), nullable=False)
    email: Mapped[str | None] = mapped_column(String(255))
    password_hash: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(32), default="active", nullable=False)
    metadata_json: Mapped[dict] = mapped_column(JsonType, default=dict, nullable=False)


class Role(Base, TimestampMixin):
    __tablename__ = "roles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    name: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)


class UserRole(Base):
    __tablename__ = "user_roles"
    __table_args__ = (UniqueConstraint("user_id", "role_id", name="uq_user_roles_user_role"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False)
    role_id: Mapped[str] = mapped_column(String(36), ForeignKey("roles.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class Employee(Base, TimestampMixin):
    __tablename__ = "employees"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    user_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), unique=True)
    display_name: Mapped[str] = mapped_column(String(128), nullable=False)
    email: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(32), default="active", nullable=False)


class BusinessAccountType(Base, TimestampMixin):
    __tablename__ = "business_account_types"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    name: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class LocalAgent(Base, TimestampMixin):
    __tablename__ = "local_agents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    employee_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("employees.id"))
    device_name: Mapped[str | None] = mapped_column(String(255))
    machine_fingerprint: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(32), default="offline", nullable=False)
    agent_version: Mapped[str | None] = mapped_column(String(64))
    capabilities_json: Mapped[dict] = mapped_column(JsonType, default=dict, nullable=False)
    last_heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PlatformAccount(Base, TimestampMixin):
    __tablename__ = "platform_accounts"
    __table_args__ = (
        Index(
            "uq_platform_accounts_unique_external",
            "platform",
            "external_account_id",
            unique=True,
            sqlite_where=text("external_account_id IS NOT NULL"),
            postgresql_where=text("external_account_id IS NOT NULL"),
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    employee_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("employees.id"))
    platform: Mapped[str] = mapped_column(String(32), nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    external_account_id: Mapped[str | None] = mapped_column(String(255))
    business_account_type: Mapped[str | None] = mapped_column(String(128))
    business_account_type_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("business_account_types.id"))
    status: Mapped[str] = mapped_column(String(64), default="active", nullable=False)
    metadata_json: Mapped[dict] = mapped_column(JsonType, default=dict, nullable=False)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_failure_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    auth_status: Mapped[str] = mapped_column(String(32), default="not_logged_in", nullable=False)
    account_role: Mapped[str] = mapped_column(String(64), default="intelligence_collector", nullable=False)
    health_status: Mapped[str] = mapped_column(String(64), default="healthy", nullable=False)
    profile_key: Mapped[str | None] = mapped_column(String(255))
    platform_nickname: Mapped[str | None] = mapped_column(String(255))
    platform_home_url: Mapped[str | None] = mapped_column(String(512))
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    login_cdp_port: Mapped[int | None] = mapped_column(Integer)


class AccountLoginSession(Base, TimestampMixin):
    __tablename__ = "account_login_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    platform_account_id: Mapped[str] = mapped_column(String(36), ForeignKey("platform_accounts.id"), nullable=False)
    agent_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("local_agents.id"))
    status: Mapped[str] = mapped_column(String(64), default="created", nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text)
    profile_key: Mapped[str] = mapped_column(String(255), nullable=False)
    cdp_port: Mapped[int | None] = mapped_column(Integer)
    claimed_by_agent_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("local_agents.id"))
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AccountSession(Base, TimestampMixin):
    __tablename__ = "account_sessions"
    __table_args__ = (UniqueConstraint("account_id", "local_agent_id", "session_type", name="uq_account_session_per_agent_type"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    account_id: Mapped[str] = mapped_column(String(36), ForeignKey("platform_accounts.id"), nullable=False)
    local_agent_id: Mapped[str] = mapped_column(String(36), ForeignKey("local_agents.id"), nullable=False)
    platform: Mapped[str] = mapped_column(String(32), nullable=False)
    session_type: Mapped[str] = mapped_column(String(32), nullable=False)
    profile_ref: Mapped[str | None] = mapped_column(String(255))
    cookie_ref: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(64), default="unavailable", nullable=False)
    session_meta_json: Mapped[dict] = mapped_column(JsonType, default=dict, nullable=False)
    last_validated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AccountAgentBinding(Base, TimestampMixin):
    __tablename__ = "account_agent_bindings"
    __table_args__ = (UniqueConstraint("account_id", "agent_id", name="uq_account_agent_binding"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    account_id: Mapped[str] = mapped_column(String(36), ForeignKey("platform_accounts.id"), nullable=False)
    agent_id: Mapped[str] = mapped_column(String(36), ForeignKey("local_agents.id"), nullable=False)
    employee_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("employees.id"))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


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
    task_template_id: Mapped[str] = mapped_column(String(36), ForeignKey("task_templates.id"), nullable=False)
    trigger_type: Mapped[str] = mapped_column(String(32), nullable=False)
    requested_by_user_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"))
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


class ContentIdentity(Base, TimestampMixin):
    __tablename__ = "content_identity"
    __table_args__ = (UniqueConstraint("platform", "platform_content_id", name="uq_content_identity_platform_content"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    platform: Mapped[str] = mapped_column(String(32), nullable=False)
    platform_content_id: Mapped[str] = mapped_column(String(255), nullable=False)
    canonical_url: Mapped[str | None] = mapped_column(Text)
    content_type: Mapped[str] = mapped_column(String(64), default="unknown", nullable=False)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    latest_snapshot_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("content_snapshots.id"))
    metadata_json: Mapped[dict] = mapped_column(JsonType, default=dict, nullable=False)


class ContentDiscoveryEvent(Base):
    __tablename__ = "content_discovery_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    content_id: Mapped[str] = mapped_column(String(36), ForeignKey("content_identity.id"), nullable=False)
    job_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("jobs.id"))
    account_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("platform_accounts.id"))
    platform: Mapped[str] = mapped_column(String(32), nullable=False)
    source_surface: Mapped[str] = mapped_column(String(64), nullable=False)
    feed_type: Mapped[str | None] = mapped_column(String(64))
    feed_position: Mapped[int | None] = mapped_column(Integer)
    discovered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    discovery_meta_json: Mapped[dict] = mapped_column(JsonType, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class ContentSnapshot(Base):
    __tablename__ = "content_snapshots"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    content_id: Mapped[str] = mapped_column(String(36), ForeignKey("content_identity.id"), nullable=False)
    title: Mapped[str | None] = mapped_column(Text)
    body_text: Mapped[str | None] = mapped_column(Text)
    author_platform_id: Mapped[str | None] = mapped_column(String(255))
    author_name: Mapped[str | None] = mapped_column(String(255))
    author_avatar_url: Mapped[str | None] = mapped_column(Text)
    cover_url: Mapped[str | None] = mapped_column(Text)
    image_urls_json: Mapped[list] = mapped_column(JsonType, default=list, nullable=False)
    video_url: Mapped[str | None] = mapped_column(Text)
    like_count: Mapped[int | None] = mapped_column(Integer)
    comment_count: Mapped[int | None] = mapped_column(Integer)
    collect_count: Mapped[int | None] = mapped_column(Integer)
    share_count: Mapped[int | None] = mapped_column(Integer)
    publish_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    fetch_source_account_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("platform_accounts.id"))
    raw_payload_json: Mapped[dict] = mapped_column(JsonType, default=dict, nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class CommentSnapshot(Base):
    __tablename__ = "comment_snapshots"
    __table_args__ = (UniqueConstraint("content_id", "platform_comment_id", name="uq_comment_per_content_platform_comment"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    content_id: Mapped[str] = mapped_column(String(36), ForeignKey("content_identity.id"), nullable=False)
    platform_comment_id: Mapped[str] = mapped_column(String(255), nullable=False)
    parent_platform_comment_id: Mapped[str | None] = mapped_column(String(255))
    author_platform_id: Mapped[str | None] = mapped_column(String(255))
    author_name: Mapped[str | None] = mapped_column(String(255))
    author_avatar_url: Mapped[str | None] = mapped_column(Text)
    body_text: Mapped[str] = mapped_column(Text, nullable=False)
    like_count: Mapped[int | None] = mapped_column(Integer)
    created_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    raw_payload_json: Mapped[dict] = mapped_column(JsonType, default=dict, nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class CandidateDecision(Base):
    __tablename__ = "candidate_decisions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    content_id: Mapped[str] = mapped_column(String(36), ForeignKey("content_identity.id"), nullable=False)
    snapshot_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("content_snapshots.id"))
    business_keyword_hits_json: Mapped[list] = mapped_column(JsonType, default=list, nullable=False)
    lead_keyword_hits_json: Mapped[list] = mapped_column(JsonType, default=list, nullable=False)
    comment_keyword_hits_json: Mapped[list] = mapped_column(JsonType, default=list, nullable=False)
    like_threshold_hit: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    comment_threshold_hit: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    candidate_bucket: Mapped[str] = mapped_column(String(64), nullable=False)
    decision_reason_json: Mapped[dict] = mapped_column(JsonType, default=dict, nullable=False)
    evaluated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class CreatorMonitor(Base, TimestampMixin):
    __tablename__ = "creator_monitors"
    __table_args__ = (UniqueConstraint("platform", "creator_platform_id", name="uq_creator_monitor_platform_creator"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    platform: Mapped[str] = mapped_column(String(32), nullable=False)
    creator_platform_id: Mapped[str] = mapped_column(String(255), nullable=False)
    creator_display_name: Mapped[str | None] = mapped_column(String(255))
    monitor_group_key: Mapped[str | None] = mapped_column(String(128))
    mapped_business_account_type: Mapped[str | None] = mapped_column(String(128))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    check_interval_seconds: Mapped[int] = mapped_column(Integer, default=900, nullable=False)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error_code: Mapped[str | None] = mapped_column(String(128))
    last_error_message: Mapped[str | None] = mapped_column(Text)
    last_cursor_json: Mapped[dict] = mapped_column(JsonType, default=dict, nullable=False)
    metadata_json: Mapped[dict] = mapped_column(JsonType, default=dict, nullable=False)


class CreatorMonitorEvent(Base):
    __tablename__ = "creator_monitor_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    creator_monitor_id: Mapped[str] = mapped_column(String(36), ForeignKey("creator_monitors.id"), nullable=False)
    content_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("content_identity.id"))
    event_type: Mapped[str] = mapped_column(String(128), nullable=False)
    event_payload_json: Mapped[dict] = mapped_column(JsonType, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class BenchmarkGroup(Base, TimestampMixin):
    __tablename__ = "benchmark_groups"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    owner_employee_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("employees.id"))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    metadata_json: Mapped[dict] = mapped_column(JsonType, default=dict, nullable=False)


class BenchmarkGroupMember(Base, TimestampMixin):
    __tablename__ = "benchmark_group_members"
    __table_args__ = (
        Index(
            "uq_benchmark_group_creator",
            "benchmark_group_id",
            "platform",
            "creator_platform_id",
            unique=True,
            sqlite_where=text("creator_platform_id IS NOT NULL"),
            postgresql_where=text("creator_platform_id IS NOT NULL"),
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    benchmark_group_id: Mapped[str] = mapped_column(String(36), ForeignKey("benchmark_groups.id"), nullable=False)
    creator_monitor_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("creator_monitors.id"))
    platform: Mapped[str] = mapped_column(String(32), nullable=False)
    creator_platform_id: Mapped[str | None] = mapped_column(String(255))
    creator_profile_url: Mapped[str | None] = mapped_column(Text)
    display_name: Mapped[str | None] = mapped_column(String(255))
    platform_context_json: Mapped[dict] = mapped_column(JsonType, default=dict, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class BusinessAccountTypeBenchmarkGroup(Base):
    __tablename__ = "business_account_type_benchmark_groups"
    __table_args__ = (UniqueConstraint("business_account_type_id", "benchmark_group_id", name="uq_bat_benchmark_group"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    business_account_type_id: Mapped[str] = mapped_column(String(36), ForeignKey("business_account_types.id"), nullable=False)
    benchmark_group_id: Mapped[str] = mapped_column(String(36), ForeignKey("benchmark_groups.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class TaskTemplate(Base, TimestampMixin):
    __tablename__ = "task_templates"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    template_type: Mapped[str] = mapped_column(String(64), nullable=False)
    platform: Mapped[str | None] = mapped_column(String(32))
    account_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("platform_accounts.id"))
    business_account_type_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("business_account_types.id"))
    config_json: Mapped[dict] = mapped_column(JsonType, default=dict, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class TaskSchedule(Base, TimestampMixin):
    __tablename__ = "task_schedules"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    task_template_id: Mapped[str] = mapped_column(String(36), ForeignKey("task_templates.id"), nullable=False)
    schedule_type: Mapped[str] = mapped_column(String(64), nullable=False)
    interval_seconds: Mapped[int | None] = mapped_column(Integer)
    daily_time_window_json: Mapped[dict] = mapped_column(JsonType, default=dict, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_materialized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class BehaviorProfile(Base, TimestampMixin):
    __tablename__ = "behavior_profiles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    name: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    config_json: Mapped[dict] = mapped_column(JsonType, default=dict, nullable=False)


class NetworkEgressProfile(Base, TimestampMixin):
    __tablename__ = "network_egress_profiles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    name: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    strategy: Mapped[str] = mapped_column(String(64), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    config_json: Mapped[dict] = mapped_column(JsonType, default=dict, nullable=False)


class RiskPolicy(Base, TimestampMixin):
    __tablename__ = "risk_policies"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    name: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    behavior_profile_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("behavior_profiles.id"))
    network_egress_profile_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("network_egress_profiles.id"))
    config_json: Mapped[dict] = mapped_column(JsonType, default=dict, nullable=False)


class ContentWorkflowState(Base, TimestampMixin):
    __tablename__ = "content_workflow_states"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    content_id: Mapped[str] = mapped_column(String(36), ForeignKey("content_identity.id"), unique=True, nullable=False)
    workflow_status: Mapped[str] = mapped_column(String(64), default="pending_review", nullable=False)
    assigned_to_user_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"))
    assigned_by_user_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"))
    assigned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    selected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    discarded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    latest_operator_note: Mapped[str | None] = mapped_column(Text)


class ContentAssignment(Base):
    __tablename__ = "content_assignments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    content_id: Mapped[str] = mapped_column(String(36), ForeignKey("content_identity.id"), nullable=False)
    assigned_to_user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False)
    assigned_by_user_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"))
    assigned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    status: Mapped[str] = mapped_column(String(64), default="assigned", nullable=False)
    remark: Mapped[str | None] = mapped_column(Text)


class ContentOperatorNote(Base):
    __tablename__ = "content_operator_notes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    content_id: Mapped[str] = mapped_column(String(36), ForeignKey("content_identity.id"), nullable=False)
    user_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"))
    note: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class BusinessAccountTypeRuleSet(Base):
    __tablename__ = "business_account_type_rule_sets"
    __table_args__ = (UniqueConstraint("business_account_type_id", "rule_set_id", name="uq_bat_rule_set"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    business_account_type_id: Mapped[str] = mapped_column(String(36), ForeignKey("business_account_types.id"), nullable=False)
    rule_set_id: Mapped[str] = mapped_column(String(36), ForeignKey("keyword_rule_sets.id"), nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class KeywordRuleSet(Base, TimestampMixin):
    __tablename__ = "keyword_rule_sets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    rule_scope: Mapped[str] = mapped_column(String(64), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    config_json: Mapped[dict] = mapped_column(JsonType, default=dict, nullable=False)


class KeywordRule(Base, TimestampMixin):
    __tablename__ = "keyword_rules"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    rule_set_id: Mapped[str] = mapped_column(String(36), ForeignKey("keyword_rule_sets.id"), nullable=False)
    keyword: Mapped[str] = mapped_column(String(255), nullable=False)
    normalized_keyword: Mapped[str | None] = mapped_column(String(255))
    match_mode: Mapped[str] = mapped_column(String(64), default="contains", nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    weight: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


class XhsSearchSuggestion(Base):
    __tablename__ = "xhs_search_suggestions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    platform: Mapped[str] = mapped_column(String(32), default="xhs", nullable=False)
    core_keyword: Mapped[str] = mapped_column(String(255), nullable=False)
    suggested_keyword: Mapped[str] = mapped_column(String(255), nullable=False)
    suggestion_rank: Mapped[int | None] = mapped_column(Integer)
    source_account_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("platform_accounts.id"))
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    raw_payload_json: Mapped[dict] = mapped_column(JsonType, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class ReferenceLibraryItem(Base, TimestampMixin):
    __tablename__ = "reference_library_items"
    __table_args__ = (
        Index(
            "uq_reference_library_active_content",
            "content_id",
            unique=True,
            sqlite_where=text("status = 'active'"),
            postgresql_where=text("status = 'active'"),
        ),
        Index("idx_reference_library_selected_at", "selected_at"),
        Index("idx_reference_library_type_status", "library_type", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    content_id: Mapped[str] = mapped_column(String(36), ForeignKey("content_identity.id"), nullable=False)
    library_type: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="active", nullable=False)
    created_by_user_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"))
    created_by_employee_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("employees.id"))
    selected_reason: Mapped[str | None] = mapped_column(Text)
    rating: Mapped[str | None] = mapped_column(String(8))
    selection_sources_json: Mapped[list] = mapped_column(JsonType, default=list, nullable=False)
    matched_keywords_json: Mapped[list] = mapped_column(JsonType, default=list, nullable=False)
    selected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    manual_tags_json: Mapped[list] = mapped_column(JsonType, default=list, nullable=False)
    material_tags_json: Mapped[list] = mapped_column(JsonType, default=list, nullable=False)
    usage_status: Mapped[str] = mapped_column(String(32), default="unused", nullable=False)
    note: Mapped[str | None] = mapped_column(Text)
    metadata_json: Mapped[dict] = mapped_column(JsonType, default=dict, nullable=False)


class ReferenceLibraryEvent(Base):
    __tablename__ = "reference_library_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    library_item_id: Mapped[str] = mapped_column(String(36), ForeignKey("reference_library_items.id"), nullable=False)
    content_id: Mapped[str] = mapped_column(String(36), ForeignKey("content_identity.id"), nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    user_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"))
    employee_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("employees.id"))
    event_payload_json: Mapped[dict] = mapped_column(JsonType, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class OperationRule(Base, TimestampMixin):
    __tablename__ = "operation_rules"
    __table_args__ = (
        Index("idx_operation_rules_type_platform", "rule_type", "platform"),
        Index("idx_operation_rules_enabled", "enabled"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    rule_type: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    platform: Mapped[str | None] = mapped_column(String(32))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_by_user_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"))


class RuleProfile(Base, TimestampMixin):
    __tablename__ = "rule_profiles"
    __table_args__ = (
        Index(
            "uq_rule_profile_enabled_scope",
            "platform",
            "library_type",
            unique=True,
            sqlite_where=text("enabled = 1"),
            postgresql_where=text("enabled = true"),
        ),
        Index("idx_rule_profiles_scope", "platform", "library_type", "enabled"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    platform: Mapped[str] = mapped_column(String(32), nullable=False)
    library_type: Mapped[str] = mapped_column(String(64), nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    config_json: Mapped[dict] = mapped_column(JsonType, default=dict, nullable=False)
    created_by_user_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"))


Index("idx_jobs_status_priority", Job.status, Job.priority, Job.scheduled_at)
Index("idx_jobs_task_run_id", Job.task_run_id)
Index("idx_jobs_account_id", Job.account_id)
Index("idx_jobs_agent_id", Job.local_agent_id)
Index("idx_jobs_claim_expiry", Job.claim_expires_at)
Index("idx_jobs_job_type", Job.job_type)
Index("idx_job_events_job_id_created", JobEvent.job_id, JobEvent.created_at)
Index("idx_content_identity_last_seen", ContentIdentity.last_seen_at)
Index("idx_content_identity_platform", ContentIdentity.platform)
Index("idx_content_identity_content_type", ContentIdentity.content_type)
Index("idx_discovery_content_id", ContentDiscoveryEvent.content_id)
Index("idx_discovery_account_id", ContentDiscoveryEvent.account_id)
Index("idx_discovery_job_id", ContentDiscoveryEvent.job_id)
Index("idx_discovery_discovered_at", ContentDiscoveryEvent.discovered_at)
Index("idx_discovery_content_discovered_at", ContentDiscoveryEvent.content_id, ContentDiscoveryEvent.discovered_at)
Index("idx_discovery_surface", ContentDiscoveryEvent.source_surface)
Index("idx_reference_library_content_status", ReferenceLibraryItem.content_id, ReferenceLibraryItem.status)
Index("idx_content_snapshots_content_id", ContentSnapshot.content_id, ContentSnapshot.fetched_at.desc())
Index("idx_content_snapshots_publish_time", ContentSnapshot.publish_time)
Index("idx_comments_content_id", CommentSnapshot.content_id)
Index("idx_comments_fetched_at", CommentSnapshot.fetched_at)
Index("idx_candidate_decisions_content_id", CandidateDecision.content_id, CandidateDecision.evaluated_at.desc())
Index("idx_candidate_decisions_bucket", CandidateDecision.candidate_bucket)
Index("idx_creator_monitors_enabled", CreatorMonitor.enabled)
Index("idx_creator_monitors_group_key", CreatorMonitor.monitor_group_key)
Index("idx_users_status", User.status)
Index("idx_employees_user_id", Employee.user_id)
Index("idx_agents_employee_id", LocalAgent.employee_id)
Index("idx_platform_accounts_employee_id", PlatformAccount.employee_id)
Index("idx_platform_accounts_business_type_id", PlatformAccount.business_account_type_id)
Index("idx_account_agent_bindings_account", AccountAgentBinding.account_id)
Index("idx_account_agent_bindings_agent", AccountAgentBinding.agent_id)
Index("idx_account_agent_bindings_employee", AccountAgentBinding.employee_id)
Index("idx_benchmark_groups_enabled", BenchmarkGroup.enabled)
Index("idx_benchmark_members_group_id", BenchmarkGroupMember.benchmark_group_id)
Index("idx_task_templates_type_enabled", TaskTemplate.template_type, TaskTemplate.enabled)
Index("idx_task_runs_template_created", TaskRun.task_template_id, TaskRun.created_at.desc())
Index("idx_task_runs_status", TaskRun.status)
Index("idx_task_schedules_template_id", TaskSchedule.task_template_id)
Index("idx_task_schedules_enabled", TaskSchedule.enabled)
Index("idx_risk_policies_enabled", RiskPolicy.enabled)
Index("idx_content_workflow_status", ContentWorkflowState.workflow_status)
Index("idx_content_workflow_assignee", ContentWorkflowState.assigned_to_user_id)
Index("idx_content_assignments_content_id", ContentAssignment.content_id)
Index("idx_content_notes_content_id", ContentOperatorNote.content_id)
