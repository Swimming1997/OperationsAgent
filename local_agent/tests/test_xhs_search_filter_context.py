from local_agent_runtime.connectors.xhs.search_probe import XhsSearchProbe


def test_search_probe_accepts_xhs_filter_context():
    probe = XhsSearchProbe(
        keywords=["SCI"],
        max_items=10,
        search_sort="most_liked",
        note_type="image_text",
        publish_time="half_year",
        search_scope="followed",
        location_filter="nearby",
    )
    assert probe.search_sort == "most_liked"
    assert probe.location_filter == "nearby"


def test_search_card_exposes_filter_apply_status():
    from local_agent_runtime.connectors.xhs.normalizer import normalize_xhs_search_card

    candidate = normalize_xhs_search_card(
        {"href": "https://www.xiaohongshu.com/explore/note-x", "title": "SCI"},
        search_keyword="SCI",
        rank_position=1,
        search_sort="most_liked",
    )
    assert candidate.raw_payload["filter_apply_status"] == "not_implemented"
    assert candidate.raw_payload["requested_filter_context"]["search_sort"] == "most_liked"
