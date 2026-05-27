import json
from datetime import datetime, timezone
from pathlib import Path

from local_agent_runtime.connectors.xhs.normalizer import (
    candidate_field_report,
    extract_xhs_content_id,
    normalize_xhs_card,
    parse_visible_count,
)
from local_agent_runtime.enums import ContentType, SessionStatus
from local_agent_runtime.sessions.xhs_browser_session import evaluate_xhs_selfinfo_payload, evaluate_xhs_session_state


def test_xhs_normalizer_extracts_card_fields_from_fixture():
    raw_cards = json.loads(Path("tests/fixtures/xhs_homefeed_cards.json").read_text(encoding="utf-8"))
    candidates = [
        candidate
        for index, raw in enumerate(raw_cards, start=1)
        if (candidate := normalize_xhs_card(raw, feed_position=index, discovered_at=datetime.now(timezone.utc)))
    ]

    assert len(candidates) == 2
    assert candidates[0].platform_content_id == "65abc123def4560001"
    assert candidates[0].canonical_url == "https://www.xiaohongshu.com/explore/65abc123def4560001"
    assert candidates[0].title_or_summary == "SCI投稿经验：如何选择期刊"
    assert candidates[0].visible_like_count == 12000
    assert candidates[1].content_type == ContentType.VIDEO.value
    assert candidates[1].visible_like_count == 345


def test_xhs_field_report_counts_parse_success():
    raw_cards = json.loads(Path("tests/fixtures/xhs_homefeed_cards.json").read_text(encoding="utf-8"))
    candidates = [
        candidate
        for index, raw in enumerate(raw_cards, start=1)
        if (candidate := normalize_xhs_card(raw, feed_position=index, discovered_at=datetime.now(timezone.utc)))
    ]
    report = candidate_field_report(candidates, target_count=50)

    assert report["target_count"] == 50
    assert report["actual_count"] == 2
    assert report["field_success"]["platform_content_id"]["rate"] == 1.0
    assert report["field_success"]["author_platform_id"]["count"] == 1


def test_xhs_session_state_branches():
    guest_feed = evaluate_xhs_session_state(url="https://www.xiaohongshu.com/explore", visible_text="推荐 发现")
    ready = evaluate_xhs_session_state(url="https://www.xiaohongshu.com/explore", visible_text="推荐 发现 发布 消息 退出登录")
    need_login = evaluate_xhs_session_state(url="https://www.xiaohongshu.com/login", visible_text="手机号登录 验证码")
    manual_verify = evaluate_xhs_session_state(url="https://www.xiaohongshu.com/explore", visible_text="安全验证 请拖动滑块")

    assert guest_feed[0] == SessionStatus.EXPIRED
    assert ready[0] == SessionStatus.READY
    assert need_login[0] == SessionStatus.EXPIRED
    assert manual_verify[0] == SessionStatus.MANUAL_VERIFY_REQUIRED


def test_xhs_session_state_ready_even_if_login_word_present():
    # 已登录页面中可能出现“登录”字样，不应直接判定过期。
    ready = evaluate_xhs_session_state(
        url="https://www.xiaohongshu.com/user/profile/abc",
        visible_text="个人主页 首页 发现 关注 消息 登录查看更多内容",
    )
    assert ready[0] == SessionStatus.READY


def test_xhs_session_state_guest_navigation_not_treated_as_ready():
    guest = evaluate_xhs_session_state(
        url="https://www.xiaohongshu.com/explore",
        visible_text="首页 发现 关注 发布 消息 登录查看更多内容",
    )
    assert guest[0] == SessionStatus.EXPIRED


def test_xhs_selfinfo_payload_detects_ready_and_expired():
    ready = evaluate_xhs_selfinfo_payload({"success": True, "data": {"basic_info": {"nickname": "demo"}}})
    expired = evaluate_xhs_selfinfo_payload({"success": False, "msg": "未登录"})
    assert ready[0] == SessionStatus.READY
    assert expired[0] == SessionStatus.EXPIRED


def test_xhs_helpers_parse_ids_and_counts():
    assert extract_xhs_content_id("https://www.xiaohongshu.com/explore/65abc123") == "65abc123"
    assert parse_visible_count("1.5万") == 15000
    assert parse_visible_count("2k") == 2000
    assert parse_visible_count("赞") is None


def test_homefeed_normalizer_defaults_blank_xsec_source_to_pc_feed():
    candidate = normalize_xhs_card(
        {
            "href": "/explore/65abc123def4560001?xsec_token=TOKEN&xsec_source=",
            "title": "带 token 的推荐卡片",
        },
        feed_position=1,
        discovered_at=datetime.now(timezone.utc),
    )

    assert candidate is not None
    assert candidate.platform_context["xsec_token"] == "TOKEN"
    assert candidate.platform_context["xsec_source"] == ""
    assert candidate.platform_context["xsec_source_effective"] == "pc_feed"
    assert candidate.platform_context["api_detail_ready"] is True
    assert "xsec_source=pc_feed" in (candidate.canonical_url or "")
