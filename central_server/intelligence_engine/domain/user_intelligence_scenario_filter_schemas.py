from datetime import datetime
from typing import Any

from pydantic import Field, field_validator

from intelligence_engine.domain.schemas import ApiModel

SYSTEM_INTELLIGENCE_SCENARIOS = frozenset({"pending", "leads", "hot", "watchlater", "all"})
CUSTOM_SCENARIO_PREFIX = "custom-"

ADVANCED_INTELLIGENCE_FILTER_KEYS = frozenset(
    {
        "platform",
        "candidate_bucket",
        "workflow_status",
        "assigned_to_user_id",
        "business_keyword",
        "discovered_after",
        "discovered_before",
        "data_status",
        "tag",
        "platform_tag",
        "manual_tag",
        "search_sort",
        "note_type_filter",
        "publish_time_filter",
        "min_like_count",
        "min_comment_count",
        "min_collect_count",
        "in_reference_library",
        "reference_library_type",
        "selection_source",
        "reference_rating",
    }
)

QUICK_INTELLIGENCE_FILTER_KEYS = frozenset(
    {
        "source_surface",
        "search_keyword",
        "sort_by",
        "sort_order",
        "page",
        "page_size",
    }
)

VALID_ROLLING_KEYS = frozenset({"discovered_after_days"})


class IntelligenceScenarioRollingConfig(ApiModel):
    discovered_after_days: int | None = None
    label: str | None = None

    @field_validator("discovered_after_days")
    @classmethod
    def validate_discovered_after_days(cls, value: int | None) -> int | None:
        if value is not None and value <= 0:
            raise ValueError("discovered_after_days must be positive")
        return value

    @field_validator("label")
    @classmethod
    def validate_label(cls, value: str | None) -> str | None:
        if value is None:
            return None
        text = value.strip()
        if not text:
            return None
        if len(text) > 32:
            raise ValueError("label must be at most 32 characters")
        return text


class IntelligenceScenarioFilterUpsertRequest(ApiModel):
    filters: dict[str, Any] = Field(default_factory=dict)
    rolling: IntelligenceScenarioRollingConfig = Field(default_factory=IntelligenceScenarioRollingConfig)

    @field_validator("filters")
    @classmethod
    def validate_filters(cls, value: dict[str, Any]) -> dict[str, Any]:
        invalid = set(value.keys()) - ADVANCED_INTELLIGENCE_FILTER_KEYS
        if invalid:
            raise ValueError(f"unsupported filter keys: {sorted(invalid)}")
        quick = set(value.keys()) & QUICK_INTELLIGENCE_FILTER_KEYS
        if quick:
            raise ValueError(f"quick filter keys are not persistable: {sorted(quick)}")
        normalized: dict[str, Any] = {}
        for key, raw in value.items():
            if raw is None:
                continue
            text = str(raw).strip()
            if text:
                normalized[key] = text
        return normalized


class IntelligenceScenarioFilterRead(ApiModel):
    scenario: str
    filters: dict[str, Any] = Field(default_factory=dict)
    rolling: IntelligenceScenarioRollingConfig = Field(default_factory=IntelligenceScenarioRollingConfig)
    updated_at: datetime | None = None
    is_user_customized: bool = True


class IntelligenceScenarioFilterListResponse(ApiModel):
    items: list[IntelligenceScenarioFilterRead] = Field(default_factory=list)
