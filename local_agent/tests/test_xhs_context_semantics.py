from local_agent_runtime.connectors.xhs.context import (
    build_xhs_note_url,
    enrich_xhs_platform_context,
    infer_xsec_source,
    is_suspect_detail_author_name,
    merge_xhs_context,
)
from local_agent_runtime.connectors.xhs.normalizer import normalize_search_api_items


def test_infer_xsec_source_for_homefeed_without_explicit_source():
    effective, status, inferred = infer_xsec_source(xsec_source="", source_surface="homefeed")
    assert effective == "pc_feed"
    assert status == "inferred_from_homefeed"
    assert inferred is True


def test_api_detail_ready_requires_note_id_and_token_only():
    context = enrich_xhs_platform_context(
        {"note_id": "note001", "xsec_token": "token123", "xsec_source": ""},
        source_surface="homefeed",
    )
    assert context["api_detail_ready"] is True
    assert context["api_comment_ready"] is True
    assert context["xsec_source_effective"] == "pc_feed"


def test_build_xhs_note_url_backfills_pc_feed():
    url = build_xhs_note_url(
        {"note_id": "note001", "xsec_token": "token123", "xsec_source": ""},
        source_surface="homefeed",
    )
    assert url is not None
    assert "xsec_source=pc_feed" in url


def test_is_suspect_detail_author_name():
    assert is_suspect_detail_author_name("我") is True
    assert is_suspect_detail_author_name("小八", upstream_author_name="作者A") is True
    assert is_suspect_detail_author_name("小八", upstream_author_name="小八") is False


def test_normalize_search_api_items_extracts_context_fields():
    data = {
        "items": [
            {
                "id": "note001",
                "xsec_token": "token123",
                "xsec_source": "pc_search",
                "note_card": {
                    "display_title": "SCI投稿经验",
                    "user": {"nickname": "作者A", "user_id": "uid001"},
                },
            }
        ]
    }
    items = normalize_search_api_items(data, keyword="SCI投稿", limit=5)
    assert len(items) == 1
    assert items[0]["platform_content_id"] == "note001"
    assert items[0]["xsec_token"] == "token123"
    assert items[0]["api_detail_ready"] is True
    assert "xsec_source=pc_search" in (items[0]["canonical_url"] or "")


def test_merge_xhs_context_keeps_latest_token():
    merged = merge_xhs_context(
        {"note_id": "note001", "xsec_token": "old"},
        {"xsec_token": "new", "xsec_source": "pc_search"},
        source_surface="search",
    )
    assert merged["xsec_token"] == "new"
    assert merged["xsec_source"] == "pc_search"
    assert merged["api_detail_ready"] is True
