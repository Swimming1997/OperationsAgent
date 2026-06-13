from local_agent_runtime.engine.search_config import SearchQueryConfig


def test_from_payload_unified_keys():
    cfg = SearchQueryConfig.from_payload(
        {
            "keywords": [" SCI论文 ", ""],
            "sort": "most_liked",
            "content_form": "video",
            "publish_time": "one_week",
            "duration": "1m_to_5m",
            "max_items": 30,
            "start_rank": 10,
        }
    )
    assert cfg.keywords == ["SCI论文"]
    assert cfg.sort == "most_liked"
    assert cfg.content_form == "video"
    assert cfg.publish_time == "one_week"
    assert cfg.duration == "1m_to_5m"
    assert cfg.max_items == 30
    assert cfg.start_rank == 10
    assert cfg.has_non_default_filters() is True


def test_from_payload_accepts_legacy_xhs_keys():
    cfg = SearchQueryConfig.from_payload({"keyword": "考研", "search_sort": "latest", "note_type": "image_text"})
    assert cfg.keywords == ["考研"]
    assert cfg.sort == "latest"
    assert cfg.content_form == "image_text"


def test_from_payload_invalid_values_fall_back_to_defaults():
    cfg = SearchQueryConfig.from_payload({"sort": "bogus", "publish_time": "yesterday", "max_items": "x", "start_rank": -5})
    assert cfg.sort == "comprehensive"
    assert cfg.publish_time == "all"
    assert cfg.max_items == 40
    assert cfg.start_rank == 0
    assert cfg.has_non_default_filters() is False


def test_requested_filter_context_shape():
    cfg = SearchQueryConfig.from_payload({"sort": "most_liked"})
    assert cfg.requested_filter_context() == {
        "sort": "most_liked",
        "content_form": "all",
        "publish_time": "all",
        "duration": "all",
    }
