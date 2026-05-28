import asyncio
import json
from pathlib import Path

from local_agent_runtime.connectors.xhs.comment_normalizer import comment_field_report, comment_keyword_hits, normalize_xhs_comments
from local_agent_runtime.connectors.xhs.comment_probe import XhsCommentProbe, detect_comment_surface_status
from local_agent_runtime.connectors.xhs.creator import (
    _build_user_posted_fetch_error,
    _candidate_to_creator_context,
    _choose_profile_candidate,
    _dom_card_to_creator_note,
    normalize_xhs_creator_item,
    parse_user_posted_response,
    parse_xhs_creator_context,
)
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


def test_xhs_creator_context_accepts_red_id_as_public_identifier():
    creator_context = parse_xhs_creator_context("1479543583")

    assert creator_context.creator_platform_id == "1479543583"
    assert creator_context.public_identifier == "1479543583"
    assert creator_context.resolve_source == "xhs_public_identifier"


def test_xhs_creator_profile_candidate_resolves_internal_user_id():
    candidates = [
        {"href": "https://www.xiaohongshu.com/user/profile/5eb8e1d400000000010075ae?xsec_token=T&xsec_source=pc_search", "text": "小红书号：1479543583"},
    ]

    chosen = _choose_profile_candidate(candidates, "1479543583")
    resolved = _candidate_to_creator_context(chosen or {})

    assert resolved is not None
    assert resolved["creator_platform_id"] == "5eb8e1d400000000010075ae"
    assert resolved["xsec_token"] == "T"


def test_xhs_creator_dom_card_fallback_builds_note_payload():
    note = _dom_card_to_creator_note(
        {
            "href": "https://www.xiaohongshu.com/explore/66fad51c000000001b0224b8?xsec_token=NOTE_TOKEN&xsec_source=pc_feed",
            "title": "SCI 投稿经验",
            "cover_url": "https://sns-img.example/cover.jpg",
        },
        fallback_xsec_source="pc_feed",
    )

    assert note is not None
    assert note["note_id"] == "66fad51c000000001b0224b8"
    assert note["display_title"] == "SCI 投稿经验"
    assert note["xsec_token"] == "NOTE_TOKEN"
    assert note["source_path"] == "creator_profile_dom_fallback"


def test_xhs_creator_user_posted_gateway_error_is_retryable():
    payload = {
        "http_status": 500,
        "parse_error": 'SyntaxError: Unexpected token "c"',
        "raw_text": "create invoker failed, service: jarvis-gateway-default",
    }

    notes, meta = parse_user_posted_response(payload)
    error = _build_user_posted_fetch_error(payload, meta)

    assert notes == []
    assert meta["has_notes"] is False
    assert meta["parse_error"]
    assert "jarvis-gateway" in (meta["raw_text_prefix"] or "")
    assert error.error_code == "retryable_network_error"
    assert error.retryable is True
    assert "这不是对标账号没有笔记" in str(error)
