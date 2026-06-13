from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, select, text
from sqlalchemy.orm import Mapped, mapped_column, object_session

from intelligence_engine.db.base import Base
from intelligence_engine.db.model_base import JsonType, TimestampMixin, new_uuid, utcnow


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
    created_by_user_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"))
    created_by_employee_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("employees.id"))


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
