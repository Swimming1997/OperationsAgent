from datetime import datetime, timezone

from local_agent_runtime.connectors.douyin.normalizer import (
    extract_aweme_list,
    iter_stream_json,
    normalize_douyin_aweme,
    normalize_douyin_comment,
    normalize_douyin_detail,
    normalize_douyin_suggestions,
)
from local_agent_runtime.enums import ContentType, Platform, SourceSurface


def _video_aweme() -> dict:
    return {
        "aweme_id": "7400000000000000001",
        "desc": "考研数学冲刺技巧",
        "create_time": 1717000000,
        "author": {"nickname": "考研老师", "sec_uid": "MS4wLjABAAAA_sec", "uid": "123456"},
        "statistics": {"digg_count": 5200, "comment_count": 310, "share_count": 88, "collect_count": 990},
        "video": {
            "cover": {"url_list": ["https://p.douyinpic.com/cover.jpg"]},
            "play_addr": {"url_list": ["https://v.douyin.com/play.mp4"]},
            "duration": 32000,
        },
    }


def _image_aweme() -> dict:
    return {
        "aweme_id": "7400000000000000002",
        "desc": "图文笔记",
        "author": {"nickname": "作者B", "sec_uid": "MS4wLjABAAAA_b"},
        "statistics": {"digg_count": 12},
        "images": [
            {"url_list": ["https://p.douyinpic.com/img1.jpg"]},
            {"url_list": ["https://p.douyinpic.com/img2.jpg"]},
        ],
    }


def test_normalize_video_aweme_maps_unified_fields():
    candidate = normalize_douyin_aweme(
        _video_aweme(),
        feed_position=3,
        discovered_at=datetime(2026, 6, 13, tzinfo=timezone.utc),
        search_keyword="考研",
    )
    assert candidate is not None
    assert candidate.platform == Platform.DOUYIN
    assert candidate.platform_content_id == "7400000000000000001"
    assert candidate.canonical_url == "https://www.douyin.com/video/7400000000000000001"
    assert candidate.content_type == ContentType.VIDEO
    assert candidate.title_or_summary == "考研数学冲刺技巧"
    assert candidate.author_name == "考研老师"
    assert candidate.author_platform_id == "MS4wLjABAAAA_sec"
    assert candidate.visible_like_count == 5200
    assert candidate.cover_url == "https://p.douyinpic.com/cover.jpg"
    assert candidate.feed_position == 3
    assert candidate.raw_payload["search_keyword"] == "考研"
    assert candidate.platform_context["aweme_id"] == "7400000000000000001"
    assert candidate.platform_context["api_detail_ready"] is True


def test_normalize_image_aweme_is_image_text_with_cover_from_images():
    candidate = normalize_douyin_aweme(_image_aweme(), source_surface=SourceSurface.SEARCH)
    assert candidate is not None
    assert candidate.content_type == ContentType.IMAGE_TEXT
    assert candidate.cover_url == "https://p.douyinpic.com/img1.jpg"
    assert candidate.source_surface == SourceSurface.SEARCH


def test_normalize_aweme_rejects_missing_id_and_non_dict():
    assert normalize_douyin_aweme(None) is None
    assert normalize_douyin_aweme({"desc": "no id"}) is None


def test_normalize_detail_maps_counts_and_publish_time():
    detail = normalize_douyin_detail(_video_aweme())
    assert detail.title == "考研数学冲刺技巧"
    assert detail.like_count == 5200
    assert detail.comment_count == 310
    assert detail.collect_count == 990
    assert detail.share_count == 88
    assert detail.video_url == "https://v.douyin.com/play.mp4"
    assert detail.publish_time is not None
    assert detail.publish_time.tzinfo is not None


def test_normalize_detail_is_defensive_on_empty():
    detail = normalize_douyin_detail(None)
    assert detail.title is None
    assert detail.like_count is None


def test_normalize_comment_maps_fields():
    comment = normalize_douyin_comment(
        {
            "cid": "c-1",
            "text": "讲得很清楚",
            "digg_count": 9,
            "create_time": 1717000123,
            "user": {"nickname": "网友A", "sec_uid": "MS4wLjABAAAA_u"},
        }
    )
    assert comment is not None
    assert comment.platform_comment_id == "c-1"
    assert comment.body_text == "讲得很清楚"
    assert comment.like_count == 9
    assert comment.author_name == "网友A"


def test_normalize_comment_rejects_empty_text_or_id():
    assert normalize_douyin_comment({"cid": "c-1", "text": ""}) is None
    assert normalize_douyin_comment({"cid": "", "text": "hi"}) is None
    assert normalize_douyin_comment(None) is None


def test_iter_stream_json_parses_app_framed_stream():
    # Mimics the real Douyin search response: hex length frames + JSON objects.
    stream = (
        '17fe7\r\n{"status_code":0,"data":[{"type":1,"aweme_info":'
        '{"aweme_id":"111","desc":"a"}}]}\r\n'
        '2a\r\n{"status_code":0,"data":[{"type":1,"aweme_info":'
        '{"aweme_id":"222","desc":"b"}}]}\r\n'
    )
    objs = list(iter_stream_json(stream))
    assert len(objs) == 2
    awemes = []
    for obj in objs:
        awemes.extend(extract_aweme_list(obj))
    assert [a["aweme_id"] for a in awemes] == ["111", "222"]


def test_extract_aweme_list_handles_search_aweme_info_shape():
    data = {"data": [{"type": 1, "aweme_info": {"aweme_id": "999", "desc": "x"}}, {"type": 2}]}
    awemes = extract_aweme_list(data)
    assert len(awemes) == 1
    assert awemes[0]["aweme_id"] == "999"


def test_iter_stream_json_empty_and_garbage_safe():
    assert list(iter_stream_json("")) == []
    assert list(iter_stream_json("17fe7\r\nnotjson\r\n")) == []


def test_normalize_suggestions_orders_by_position_and_drops_seed():
    data = {
        "sug_list": [
            {"content": "SCI论文", "word_record": {"words_position": 0}},  # equals seed → dropped
            {"content": "sci论文怎么写", "word_record": {"group_id": "g2", "words_position": 1, "words_source": "sug"}},
            {"content": "sci论文辅导", "word_record": {"group_id": "g3", "words_position": 2}},
            {"content": "", "word_record": {"words_position": 3}},  # empty → skipped
            {"content": "sci论文怎么写", "word_record": {"words_position": 4}},  # dup → skipped
        ]
    }
    items = normalize_douyin_suggestions(data, core_keyword="SCI论文", fetched_at_iso="2026-06-13T00:00:00+00:00")
    assert [i["suggested_keyword"] for i in items] == ["sci论文怎么写", "sci论文辅导"]
    assert items[0]["suggestion_rank"] == 2  # words_position 1 → rank 2
    assert items[0]["core_keyword"] == "SCI论文"
    assert items[0]["raw_payload"]["group_id"] == "g2"


def test_normalize_suggestions_falls_back_to_order_without_position():
    data = {"sug_list": [{"content": "a"}, {"content": "b"}]}
    items = normalize_douyin_suggestions(data, core_keyword="seed", fetched_at_iso="t")
    assert [i["suggestion_rank"] for i in items] == [1, 2]


def test_normalize_suggestions_defensive():
    assert normalize_douyin_suggestions(None, core_keyword="x", fetched_at_iso="t") == []
    assert normalize_douyin_suggestions({"sug_list": "nope"}, core_keyword="x", fetched_at_iso="t") == []


def test_extract_aweme_list_covers_recommend_feed_containers():
    # jingxuan module/feed responses carry items under several keys; all aweme
    # objects (with an aweme_id) should be pulled regardless of container.
    data = {
        "aweme_list": [{"aweme_id": "1"}],
        "chime_video_list": [{"aweme_id": "2"}],
        "preload_awemes": [{"aweme_id": "3"}, {"no_id": True}],
    }
    ids = [a["aweme_id"] for a in extract_aweme_list(data)]
    assert ids == ["1", "2", "3"]
