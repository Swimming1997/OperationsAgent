import time
from datetime import datetime, timezone

from local_agent_runtime.audit.perf import PerfTimer, merge_surface_perf
from local_agent_runtime.audit.xhs_engine_audit import pick_fresh_note
from local_agent_runtime.connectors.xhs.api_client import extract_self_info_fields
from local_agent_runtime.contracts import FeedCandidateInput
from local_agent_runtime.enums import ContentType, FeedType, Platform, SourceSurface


def test_extract_self_info_fields_from_basic_info():
    data = {"basic_info": {"nickname": "测试用户", "red_id": "abc123", "share_link": "https://x.test/u"}}
    fields = extract_self_info_fields(data)
    assert fields["nickname"] == "测试用户"
    assert fields["red_id"] == "abc123"
    assert fields["user_id"] is None
    assert fields["home_url"] == "https://x.test/u"


def test_pick_fresh_note_prefers_xsec_context():
    with_xsec = FeedCandidateInput(
        platform=Platform.XHS,
        platform_content_id="note_with_xsec",
        canonical_url="https://www.xiaohongshu.com/explore/note_with_xsec?xsec_token=abcd1234efgh5678&xsec_source=pc_search",
        content_type=ContentType.IMAGE_TEXT,
        source_surface=SourceSurface.SEARCH,
        feed_type=FeedType.XHS_HOME_FEED,
        feed_position=1,
        discovered_at=datetime.now(timezone.utc),
        platform_context={"note_id": "note_with_xsec", "xsec_token": "abcd1234efgh5678", "xsec_source": "pc_search", "api_detail_ready": True},
    )
    without_xsec = FeedCandidateInput(
        platform=Platform.XHS,
        platform_content_id="note_plain",
        canonical_url="https://www.xiaohongshu.com/explore/note_plain",
        content_type=ContentType.IMAGE_TEXT,
        source_surface=SourceSurface.SEARCH,
        feed_type=FeedType.XHS_HOME_FEED,
        feed_position=2,
        discovered_at=datetime.now(timezone.utc),
        platform_context={"note_id": "note_plain", "api_detail_ready": False},
    )
    picked = pick_fresh_note([without_xsec, with_xsec])
    assert picked is not None
    url, note_id, context = picked
    assert note_id == "note_with_xsec"
    assert context.get("api_detail_ready") is True
    assert "xsec_token" in url


def test_merge_surface_perf_keeps_wall_clock_total():
    timer = PerfTimer()
    with timer.stage("api"):
        time.sleep(0.2)
    probe_perf = {"dom_extract_ms": 50.0, "scroll_ms": 1200.0, "total_ms": 23.0, "items_per_second": 999.0}
    perf = merge_surface_perf(timer, probe_perf, item_count=1)
    assert perf["dom_extract_ms"] == 50.0
    assert perf["scroll_ms"] == 1200.0
    assert perf["total_ms"] >= 0.0
    assert perf["total_ms"] != 23.0 or perf["total_ms"] == 0.0
    if perf["total_ms"] > 0:
        assert perf["items_per_second"] <= 10.0
