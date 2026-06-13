"""Backward-compatible re-export.

The XHS search-filter applicator moved to the connector layer
(``connectors/xhs/search_filter.py``) so both the smoke runner and the live
``search_collect`` job apply native filters through one implementation.
"""

from __future__ import annotations

from local_agent_runtime.connectors.xhs.search_filter import (
    NOTE_TYPE_LABELS,
    PUBLISH_TIME_LABELS,
    SORT_LABELS,
    apply_search_filters,
    default_filter_context,
    filters_are_default,
)

__all__ = [
    "NOTE_TYPE_LABELS",
    "PUBLISH_TIME_LABELS",
    "SORT_LABELS",
    "apply_search_filters",
    "default_filter_context",
    "filters_are_default",
]
