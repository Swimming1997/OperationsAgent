from datetime import datetime, timedelta, timezone

from intelligence_engine.db.models import UserIntelligenceScenarioFilter
from intelligence_engine.domain.user_intelligence_scenario_filter_schemas import (
    IntelligenceScenarioFilterRead,
    IntelligenceScenarioFilterUpsertRequest,
    IntelligenceScenarioRollingConfig,
    VALID_INTELLIGENCE_SCENARIOS,
)


def assert_valid_scenario(scenario: str) -> None:
    if scenario not in VALID_INTELLIGENCE_SCENARIOS:
        raise ValueError(f"unsupported scenario: {scenario}")


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
