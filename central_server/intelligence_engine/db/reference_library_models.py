from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, select, text
from sqlalchemy.orm import Mapped, mapped_column, object_session

from intelligence_engine.db.base import Base
from intelligence_engine.db.model_base import JsonType, TimestampMixin, new_uuid, utcnow


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
