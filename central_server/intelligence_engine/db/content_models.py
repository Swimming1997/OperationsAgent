from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, select, text
from sqlalchemy.orm import Mapped, mapped_column, object_session

from intelligence_engine.db.base import Base
from intelligence_engine.db.model_base import JsonType, TimestampMixin, new_uuid, utcnow


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
    stored_cover_path: Mapped[str | None] = mapped_column(Text)
    cover_media_status: Mapped[str | None] = mapped_column(String(32))
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


class UserIntelligenceScenarioFilter(Base, TimestampMixin):
    __tablename__ = "user_intelligence_scenario_filters"
    __table_args__ = (
        UniqueConstraint("user_id", "scenario", name="uq_user_intelligence_scenario_filters_user_scenario"),
        Index("idx_user_intelligence_scenario_filters_user_id", "user_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False)
    scenario: Mapped[str] = mapped_column(String(32), nullable=False)
    filters_json: Mapped[dict] = mapped_column(JsonType, default=dict, nullable=False)
    rolling_json: Mapped[dict] = mapped_column(JsonType, default=dict, nullable=False)


class ManualTag(Base, TimestampMixin):
    __tablename__ = "manual_tags"
    __table_args__ = (
        UniqueConstraint("name", name="uq_manual_tags_name"),
        Index("idx_manual_tags_status", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="active", nullable=False)
    is_system: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_by_user_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"))
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    archived_by_user_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"))


class ContentManualTag(Base):
    __tablename__ = "content_manual_tags"
    __table_args__ = (
        UniqueConstraint("content_id", "tag_id", name="uq_content_manual_tags_content_tag"),
        Index("idx_content_manual_tags_content_id", "content_id"),
        Index("idx_content_manual_tags_tag_id", "tag_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    content_id: Mapped[str] = mapped_column(String(36), ForeignKey("content_identity.id"), nullable=False)
    tag_id: Mapped[str] = mapped_column(String(36), ForeignKey("manual_tags.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
