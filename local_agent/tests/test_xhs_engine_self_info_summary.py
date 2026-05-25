import json
from pathlib import Path

from local_agent_runtime.audit.levels import AuditSeverity
from local_agent_runtime.audit.logger import EngineAuditLogger
from local_agent_runtime.audit.models import EngineAuditRecord, EngineAuditRunSummary
from local_agent_runtime.connectors.xhs.api_client import (
    build_self_info_account_summary,
    classify_self_info_severity,
    extract_self_info_fields,
    extract_self_info_result,
    format_self_info_terminal_lines,
    sanitize_self_info_raw_fields,
    write_self_info_raw_fields_debug,
)


def test_extract_self_info_fields_includes_user_id_from_basic_info():
    data = {
        "basic_info": {
            "nickname": "测试昵称",
            "user_id": "5f58bd990000000001003753",
            "red_id": "xhs_red_001",
            "images": "https://sns-avatar.example/avatar.jpg",
        }
    }
    result = extract_self_info_result(data)
    assert result.nickname == "测试昵称"
    assert result.user_id == "5f58bd990000000001003753"
    assert result.red_id == "xhs_red_001"
    assert result.avatar_url == "https://sns-avatar.example/avatar.jpg"
    assert result.home_url == "https://www.xiaohongshu.com/user/profile/5f58bd990000000001003753"
    assert result.field_sources["home_url"] == "derived_from_user_id"


def test_extract_self_info_red_id_without_user_id_does_not_construct_home_url():
    data = {"basic_info": {"nickname": "興趣使然", "red_id": "1479543583", "images": "https://sns-avatar.example/a.jpg"}}
    result = extract_self_info_result(data)
    assert result.user_id is None
    assert result.red_id == "1479543583"
    assert result.home_url is None
    summary = build_self_info_account_summary(logged_in=True, status="partial", extract=result)
    assert summary["stable_user_key"] == "1479543583"
    assert summary["stable_user_key_source"] == "red_id"
    assert classify_self_info_severity(logged_in=True, summary=summary) == AuditSeverity.P2_MAJOR


def test_extract_self_info_derives_home_url_when_api_has_user_id_only():
    data = {
        "user_info": {
            "nickname": "昵称",
            "user_id": "5f58bd990000000001003753",
            "red_id": "1234567890",
            "avatar_url": "https://sns-avatar.example/avatar.jpg",
        }
    }
    result = extract_self_info_result(data)
    assert result.home_url == "https://www.xiaohongshu.com/user/profile/5f58bd990000000001003753"
    summary = build_self_info_account_summary(logged_in=True, status="ok", extract=result)
    assert summary["home_url_source"] == "derived_from_user_id"
    assert classify_self_info_severity(logged_in=True, summary=summary) == AuditSeverity.P4_INFO


def test_extract_self_info_uses_api_home_url_when_present():
    data = {
        "basic_info": {
            "nickname": "昵称",
            "user_id": "5f58bd990000000001003753",
            "red_id": "1234567890",
            "profile_url": "https://www.xiaohongshu.com/user/profile/custom",
            "avatar_url": "https://sns-avatar.example/avatar.jpg",
        }
    }
    fields = extract_self_info_fields(data)
    summary = build_self_info_account_summary(logged_in=True, status="ok", fields=fields)
    assert summary["home_url"] == "https://www.xiaohongshu.com/user/profile/custom"
    assert summary["home_url_source"] == "api"
    assert classify_self_info_severity(logged_in=True, summary=summary) == AuditSeverity.P4_INFO


def test_classify_self_info_severity_rules():
    complete = build_self_info_account_summary(
        logged_in=True,
        status="ok",
        fields={
            "nickname": "a",
            "user_id": "5f58bd990000000001003753",
            "red_id": "123",
            "home_url": "https://x.test/u",
            "avatar_url": "https://x.test/a",
        },
    )
    assert classify_self_info_severity(logged_in=True, summary=complete) == AuditSeverity.P4_INFO

    avatar_only_missing = build_self_info_account_summary(
        logged_in=True,
        status="partial",
        fields={
            "nickname": "a",
            "user_id": "5f58bd990000000001003753",
            "red_id": "123",
            "home_url": "https://x.test/u",
        },
    )
    assert classify_self_info_severity(logged_in=True, summary=avatar_only_missing) == AuditSeverity.P3_MINOR

    incomplete = build_self_info_account_summary(
        logged_in=True,
        status="partial",
        fields={"nickname": "a", "red_id": "123"},
    )
    assert classify_self_info_severity(logged_in=True, summary=incomplete) == AuditSeverity.P2_MAJOR
    assert classify_self_info_severity(logged_in=False, summary=incomplete) == AuditSeverity.P1_BLOCKER


def test_self_info_summary_files_include_field_sources_and_missing_reasons(tmp_path: Path):
    account_summary = build_self_info_account_summary(
        logged_in=True,
        status="partial",
        fields={"nickname": "真实昵称ABC", "red_id": "1479543583", "avatar_url": "https://sns-avatar.example/avatar.jpg"},
    )
    record = EngineAuditRecord(
        "xhs.account.self_info",
        "self_info",
        "partial",
        severity=AuditSeverity.P2_MAJOR,
        items_seen=1,
        normalized_items=1,
        source_path="signed_api_selfinfo",
        account_summary=account_summary,
        payload={"Cookie": "a1=secret-cookie", "X-S": "signed-value", "xsec_token": "abcdefghijklmnop"},
    )
    summary = EngineAuditRunSummary("20260524_test001", [record], 12.3)
    logger = EngineAuditLogger(project_root=tmp_path, run_id="20260524_test001")
    logger.write_records([record])
    logger.write_summary(summary)

    md_text = logger.summary_md_path.read_text(encoding="utf-8")
    json_text = logger.summary_json_path.read_text(encoding="utf-8")
    ndjson_text = logger.ndjson_path.read_text(encoding="utf-8")
    summary_json = json.loads(json_text)

    assert "| field | value | source |" in md_text
    assert "stable_user_key" in md_text
    assert "user_id_missing_reason" in md_text
    assert "cannot_derive_without_user_id" in md_text

    assert summary_json["self_info"]["missing_fields"] == ["user_id", "home_url"]
    assert summary_json["self_info"]["missing_reasons"]["home_url"] == "cannot_derive_without_user_id"
    assert summary_json["self_info"]["stable_user_key_source"] == "red_id"

    for blob in (md_text, json_text, ndjson_text):
        assert "secret-cookie" not in blob
        assert "signed-value" not in blob
        assert "abcdefghijklmnop" not in blob
        assert "Cookie: a1=" not in blob


def test_format_self_info_terminal_lines():
    account_summary = build_self_info_account_summary(
        logged_in=True,
        status="partial",
        fields={"nickname": "真实昵称", "red_id": "1479543583", "avatar_url": "https://x.test/a"},
    )
    lines = format_self_info_terminal_lines(status="partial", account_summary=account_summary)
    assert lines[0].startswith("self_info: partial, nickname=真实昵称")
    assert "stable_user_key=1479543583(red_id)" in lines[0]
    assert "missing_fields: user_id, home_url" in lines
    assert lines[-1] == "highest_severity: P2_MAJOR"


def test_sanitize_self_info_raw_fields_strips_sensitive_keys():
    raw = {
        "basic_info": {"nickname": "测试", "red_id": "123"},
        "Cookie": "secret",
        "headers": {"X-S": "signed", "X-T": "123"},
        "xsec_token": "token-value",
    }
    sanitized = sanitize_self_info_raw_fields(raw)
    blob = json.dumps(sanitized, ensure_ascii=False)
    assert sanitized["basic_info"]["nickname"] == "测试"
    assert "Cookie" not in sanitized
    assert "headers" not in sanitized
    assert "xsec_token" not in sanitized
    assert "secret" not in blob
    assert "signed" not in blob


def test_write_self_info_raw_fields_debug_file(tmp_path: Path):
    data = {"basic_info": {"nickname": "测试", "red_id": "1479543583"}, "Cookie": "secret"}
    path = write_self_info_raw_fields_debug(project_root=tmp_path, run_id="20260524_debug001", data=data)
    assert path.name == "self_info_raw_fields_20260524_debug001.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["data"]["basic_info"]["nickname"] == "测试"
    assert "Cookie" not in payload["data"]
    assert "secret" not in path.read_text(encoding="utf-8")
