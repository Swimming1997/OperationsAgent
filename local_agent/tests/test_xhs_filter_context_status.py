from __future__ import annotations

import pytest

from local_agent_runtime.smoke.contract import validate_smoke_report
from local_agent_runtime.smoke.search_filter_applicator import filters_are_default


def test_default_filters_are_not_applicable():
    requested = {"search_sort": "comprehensive", "note_type": "all", "publish_time": "all", "search_scope": "all", "location_filter": "all"}
    assert filters_are_default(requested) is True


def test_non_default_filters_not_default():
    requested = {"search_sort": "most_liked", "note_type": "all", "publish_time": "all"}
    assert filters_are_default(requested) is False


def test_filter_apply_status_cannot_mark_applied_without_context():
    report = {
        "capability": "search_collect",
        "filter_apply_status": "applied",
        "requested_filter_context": {"search_sort": "most_commented", "note_type": "image_text", "publish_time": "half_year"},
        "applied_filter_context": None,
        "items": [],
        "item_count": 0,
    }
    result = validate_smoke_report(report)
    assert result["valid"] is False


@pytest.mark.parametrize(
    "status,applied,requested_sort",
    [
        ("not_implemented", None, "most_liked"),
        ("partial", {"search_sort": "most_liked", "note_type": "all", "publish_time": "all"}, "most_liked"),
        ("failed", None, "most_commented"),
    ],
)
def test_requested_not_equal_applied_is_allowed_when_not_applied(status, applied, requested_sort):
    report = {
        "capability": "search_collect",
        "filter_apply_status": status,
        "requested_filter_context": {"search_sort": requested_sort, "note_type": "all", "publish_time": "all"},
        "applied_filter_context": applied,
        "items": [
            {
                "platform_content_id": "n1",
                "canonical_url": "https://www.xiaohongshu.com/explore/n1",
                "title": "t",
                "search_rank": 1,
            }
        ],
        "item_count": 1,
    }
    result = validate_smoke_report(report)
    assert result["valid"] is True
