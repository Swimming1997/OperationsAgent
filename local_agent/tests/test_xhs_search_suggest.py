from local_agent_runtime.connectors.xhs.normalizer import normalize_xhs_search_card


def test_xhs_search_suggest_probe_collects_ranked_keywords():
    from local_agent_runtime.connectors.xhs.search_suggest_probe import XhsSearchSuggestProbe

    probe = XhsSearchSuggestProbe(core_keyword="SCI")
    assert probe.core_keyword == "SCI"


def test_search_card_carries_filter_context():
    candidate = normalize_xhs_search_card(
        {"href": "https://www.xiaohongshu.com/explore/note-1", "title": "SCI投稿"},
        search_keyword="SCI",
        rank_position=3,
        search_sort="latest",
        note_type="video",
        publish_time="one_week",
        search_scope="unviewed",
        location_filter="same_city",
    )
    assert candidate is not None
    assert candidate.raw_payload["search_rank"] == 3
    assert candidate.raw_payload["search_sort"] == "latest"
    assert candidate.raw_payload["note_type"] == "video"
