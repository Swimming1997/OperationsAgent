from datetime import datetime, timedelta, timezone

from intelligence_engine.db.models import UserIntelligenceScenarioFilter
import re

from intelligence_engine.domain.user_intelligence_scenario_filter_schemas import (
    CUSTOM_SCENARIO_PREFIX,
    IntelligenceScenarioFilterRead,
    IntelligenceScenarioFilterUpsertRequest,
    IntelligenceScenarioRollingConfig,
    SYSTEM_INTELLIGENCE_SCENARIOS,
)

_CUSTOM_SCENARIO_PATTERN = re.compile(r"^custom-[a-z0-9]{4,24}$")


def is_custom_scenario(scenario: str) -> bool:
    return bool(_CUSTOM_SCENARIO_PATTERN.match(scenario))


def assert_valid_scenario(scenario: str) -> None:
    if scenario in SYSTEM_INTELLIGENCE_SCENARIOS:
        return
    if is_custom_scenario(scenario):
        return
    raise ValueError(f"unsupported scenario: {scenario}")


def assert_custom_scenario_create(scenario: str, rolling: IntelligenceScenarioRollingConfig) -> None:
    assert_valid_scenario(scenario)
    if not is_custom_scenario(scenario):
        return
    if not rolling.label:
        raise ValueError("custom scenario requires label")


def rolling_config_from_dict(raw: dict | None) -> IntelligenceScenarioRollingConfig:
    if not raw:
        return IntelligenceScenarioRollingConfig()
    return IntelligenceScenarioRollingConfig.model_validate(raw)


def resolve_discovered_after(filters: dict, rolling: IntelligenceScenarioRollingConfig) -> dict:
    resolved = dict(filters)
    if resolved.get("discovered_after"):
        return resolved
    days = rolling.discovered_after_days
    if days is None:
        return resolved
    resolved["discovered_after"] = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    return resolved


def split_filters_for_save(filters: dict) -> tuple[dict, IntelligenceScenarioRollingConfig]:
    stored = dict(filters)
    rolling = IntelligenceScenarioRollingConfig()
    discovered_after = stored.pop("discovered_after", None)
    if discovered_after:
        stored["discovered_after"] = discovered_after
    return stored, rolling


def filter_read_from_row(row: UserIntelligenceScenarioFilter) -> IntelligenceScenarioFilterRead:
    return IntelligenceScenarioFilterRead(
        scenario=row.scenario,
        filters=row.filters_json or {},
        rolling=rolling_config_from_dict(row.rolling_json),
        updated_at=row.updated_at,
        is_user_customized=True,
    )


def normalize_upsert_request(request: IntelligenceScenarioFilterUpsertRequest) -> tuple[dict, dict]:
    filters = dict(request.filters)
    rolling = request.rolling.model_dump(exclude_none=True)
    if filters.get("discovered_after"):
        rolling.pop("discovered_after_days", None)
    elif rolling.get("discovered_after_days") is not None:
        filters.pop("discovered_after", None)
    return filters, rolling
