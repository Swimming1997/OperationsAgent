from __future__ import annotations

from datetime import datetime, timezone

from local_agent_runtime.smoke.contract import map_comment_item, map_detail_payload, map_homefeed_or_search_item, validate_smoke_report
from local_agent_runtime.enums import SourceSurface


def test_contract_maps_homefeed_item():
    mapped = map_homefeed_or_search_item(
        {
            "platform_content_id": "note-1",
            "canonical_url": "https://www.xiaohongshu.com/explore/note-1",
            "title": "SCI",
            "feed_position": 1,
        },
        source_surface=SourceSurface.XHS_HOME_FEED,
    )
    assert mapped.platform_content_id == "note-1"
    assert mapped.title_or_summary == "SCI"


def test_contract_maps_detail_and_comment():
    detail = map_detail_payload(
        {
            "title": "标题",
            "body_text": "正文",
            "author_name": "作者",
            "image_urls": ["https://example.com/a.jpg"],
            "publish_time": datetime.now(timezone.utc).isoformat(),
        }
    )
    assert detail.title == "标题"
    comment = map_comment_item(
        {
            "comment_id": "c1",
            "comment_text": "hello",
            "comment_author": "user",
            "comment_rank": 1,
        }
    )
    assert comment.body_text == "hello"


def test_contract_validation_passes_search_collect():
    report = {
        "capability": "search_collect",
        "item_count": 1,
        "filter_apply_status": "not_implemented",
        "requested_filter_context": {"search_sort": "comprehensive", "note_type": "all", "publish_time": "all"},
        "applied_filter_context": None,
        "items": [
            {
                "platform_content_id": "note-1",
                "canonical_url": "https://www.xiaohongshu.com/explore/note-1",
                "title": "SCI",
                "search_rank": 1,
            }
        ],
    }
    result = validate_smoke_report(report)
    assert result["valid"] is True
    assert result["mapped_count"] == 1


def test_contract_rejects_applied_without_context():
    report = {
        "capability": "search_collect",
        "item_count": 0,
        "filter_apply_status": "applied",
        "requested_filter_context": {"search_sort": "most_liked", "note_type": "all", "publish_time": "all"},
        "applied_filter_context": None,
        "items": [],
    }
    result = validate_smoke_report(report)
    assert result["valid"] is False
    assert any("applied_filter_context" in item for item in result["errors"])
