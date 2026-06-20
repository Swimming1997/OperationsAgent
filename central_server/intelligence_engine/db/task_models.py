from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, select, text
from sqlalchemy.orm import Mapped, mapped_column, object_session

from intelligence_engine.db.base import Base
from intelligence_engine.db.model_base import JsonType, TimestampMixin, new_uuid, utcnow


class TaskTemplate(Base, TimestampMixin):
    __tablename__ = "task_templates"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    template_type: Mapped[str] = mapped_column(String(64), nullable=False)
    platform: Mapped[str | None] = mapped_column(String(32))
    account_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("platform_accounts.id"))
    business_account_type_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("business_account_types.id"))
    created_by_user_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"))
    config_json: Mapped[dict] = mapped_column(JsonType, default=dict, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class TaskSchedule(Base, TimestampMixin):
    __tablename__ = "task_schedules"
    __table_args__ = (Index("idx_task_schedules_enabled_next_run", "enabled", "next_run_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    task_template_id: Mapped[str] = mapped_column(String(36), ForeignKey("task_templates.id"), nullable=False)
    executor_account_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("platform_accounts.id"))
    created_by_user_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"))
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
