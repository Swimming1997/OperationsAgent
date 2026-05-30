from __future__ import annotations

import json
from typing import Any

from intelligence_engine.domain.enums import FeedType, Platform, TaskTemplateType

LEGACY_TEMPLATE_DEFAULTS: dict[str, dict[str, Any]] = {
    TaskTemplateType.RECOMMENDATION_FEED_TASK.value: {
        "feed_type": FeedType.XHS_HOME_FEED.value,
        "target_count": 50,
        "refresh_rounds": 2,
        "per_round_scroll_target": 50,
    },
    TaskTemplateType.CREATOR_MONITOR_TASK.value: {
        "auto_detail_fetch": True,
        "max_latest_items": 20,
    },
    TaskTemplateType.KEYWORD_SEARCH_TASK.value: {
        "platform": Platform.XHS.value,
        "keywords": [],
        "max_items": 50,
    },
}


def parse_template_config_dict(config: Any) -> dict[str, Any]:
    if config is None:
        return {}
    if isinstance(config, str):
        try:
            parsed = json.loads(config)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    if isinstance(config, dict):
        return dict(config)
    return {}


def strip_legacy_template_config_keys(config: dict[str, Any]) -> dict[str, Any]:
    cleaned = dict(config)
    for key in ("executor_account_id", "account_id"):
        cleaned.pop(key, None)
    return cleaned
