import asyncio
import json
from pathlib import Path

from local_agent_runtime.connectors.xhs.comment_normalizer import comment_field_report, comment_keyword_hits, normalize_xhs_comments
from local_agent_runtime.connectors.xhs.comment_probe import XhsCommentProbe, detect_comment_surface_status
from local_agent_runtime.connectors.xhs.creator import normalize_xhs_creator_item, parse_user_posted_response, parse_xhs_creator_context
from local_agent_runtime.connectors.xhs.detail_normalizer import detail_field_report, normalize_xhs_detail_payload


def test_xhs_detail_normalizer_extracts_fixture_fields():
    raw_payload = json.loads(Path("tests/fixtures/xhs_detail_payload.json").read_text(encoding="utf-8"))
    snapshot = normalize_xhs_detail_payload(raw_payload, platform_content_id="65abc123def4560001")

    assert snapshot.title == "SCI投稿经验：如何选择期刊"
    assert snapshot.author_platform_id == "user001"
    assert snapshot.like_count == 12000
    assert len(snapshot.image_urls) == 2
    assert detail_field_report([snapshot])["field_success"]["title"]["rate"] == 1.0


def test_xhs_comment_normalizer_and_status_helpers():
    raw_payload = json.loads(Path("tests/fixtures/xhs_comments_payload.json").read_text(encoding="utf-8"))
    comments = normalize_xhs_comments(raw_payload, limit=20)
    assert len(comments) == 2
    assert comments[0].body_text == "求推荐，怎么联系？"
    assert comment_field_report(comments)["field_success"]["body_text"]["rate"] == 1.0
    comments[0].body_text = "请私信咨询"
    assert "私信" in comment_keyword_hits(comments)
    assert detect_comment_surface_status(url="https://www.xiaohongshu.com/login", body_text="手机号登录", comment_node_count=0)[0] == "login_required"


def test_xhs_comment_probe_missing_xsec_context_is_explicit():
    result = asyncio.run(
        XhsCommentProbe().fetch_comments_result(
            None,
            canonical_url="https://www.xiaohongshu.com/explore/69f5b80a000000003701d4a1",
            platform_content_id="69f5b80a000000003701d4a1",
            platform_context={},
            limit=20,
        )
    )
    assert result.surface_status == "missing_xsec_context"


def test_xhs_creator_helpers():
    creator_context = parse_xhs_creator_context(
        "https://www.xiaohongshu.com/user/profile/5eb8e1d400000000010075ae?xsec_token=CREATOR_TOKEN&xsec_source=pc_feed"
    )
    assert creator_context.creator_platform_id == "5eb8e1d400000000010075ae"
    item = normalize_xhs_creator_item({"note_id": "66fad51c000000001b0224b8", "display_title": "SCI 投稿经验", "xsec_token": "NOTE_TOKEN"})
    assert item is not None
    assert item.platform_context["xsec_token"] == "NOTE_TOKEN"
    notes, meta = parse_user_posted_response({"success": True, "data": {"notes": [{"note_id": "n1"}], "cursor": "c"}})
    assert notes[0]["note_id"] == "n1"
    assert meta["has_notes"] is True
