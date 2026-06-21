from local_agent_runtime.connectors.xhs.normalizer import normalize_xhs_search_card


def test_xhs_search_suggest_probe_collects_ranked_keywords():
    from local_agent_runtime.connectors.xhs.search_suggest_probe import XhsSearchSuggestProbe

    probe = XhsSearchSuggestProbe(core_keyword="SCI")
    assert probe.core_keyword == "SCI"


def test_merge_candidates_filters_nav_and_keeps_long_tail():
    from local_agent_runtime.connectors.xhs.search_suggest_probe import XhsSearchSuggestProbe

    probe = XhsSearchSuggestProbe(core_keyword="高考加油")
    dropdown = [
        "首页",
        "直播",
        "高考加油图片",
        "高考加油的文案",
        "高考加油",  # the core keyword itself is dropped
        "通知",
        "我",
    ]
    payloads = [{"data": {"sug_items": [{"text": "高考加油壁纸"}, {"text": "发布"}]}}]

    merged = probe._merge_candidates(dropdown, payloads)

    # Authoritative recommend sug_items rank first, then the visible 相关搜索 chips.
    assert merged == ["高考加油壁纸", "高考加油图片", "高考加油的文案"]


def test_merge_candidates_dedupes_across_sources():
    from local_agent_runtime.connectors.xhs.search_suggest_probe import XhsSearchSuggestProbe

    probe = XhsSearchSuggestProbe(core_keyword="考研")
    merged = probe._merge_candidates(
        ["考研英语", "考研数学"],
        [{"data": {"sug_items": [{"text": "考研政治"}, {"text": "考研英语"}]}}],
    )
    # sug_items first (考研政治, 考研英语), then remaining dropdown (考研数学).
    assert merged == ["考研政治", "考研英语", "考研数学"]


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
