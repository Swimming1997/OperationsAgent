from local_agent_runtime.audit.levels import AuditSeverity, ISSUE_CODES
from local_agent_runtime.audit.models import EngineAuditIssue, EngineAuditRecord, EngineAuditRunSummary
from local_agent_runtime.connectors.xhs.api_client import build_self_info_account_summary


def test_severity_enum_and_summary():
    issue = EngineAuditIssue(AuditSeverity.P2_MAJOR, "xhs.note.comments", "comment", "field_mismatch", "mismatch")
    record = EngineAuditRecord("xhs.note.comments", "comment", "failed", issues=[issue])
    summary = EngineAuditRunSummary("run", [record], 12.3)
    assert summary.severity == AuditSeverity.P2_MAJOR
    assert "field_mismatch" in ISSUE_CODES


def test_summary_markdown_payload_shape():
    record = EngineAuditRecord("xhs.feed.home_recommend", "homefeed", "ok", items_seen=1, normalized_items=1)
    payload = EngineAuditRunSummary("run", [record], 1.0).to_dict()
    assert payload["records"][0]["surface"] == "homefeed"


def test_self_info_summary_json_includes_top_level_self_info():
    account_summary = build_self_info_account_summary(
        logged_in=True,
        status="ok",
        fields={
            "nickname": "昵称",
            "user_id": "5f58bd990000000001003753",
            "red_id": "1234567890",
            "home_url": "https://x.test/u",
            "avatar_url": "https://x.test/a",
        },
    )
    record = EngineAuditRecord(
        "xhs.account.self_info",
        "self_info",
        "ok",
        account_summary=account_summary,
    )
    payload = EngineAuditRunSummary("run", [record], 1.0).to_dict()
    assert payload["self_info"]["nickname"] == "昵称"
    assert payload["self_info"]["stable_user_key"] == "5f58bd990000000001003753"
    assert payload["self_info"]["missing_fields"] == []
    assert payload["records"][0]["account_summary"]["user_id"] == "5f58bd990000000001003753"
