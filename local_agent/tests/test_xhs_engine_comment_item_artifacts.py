import json
from datetime import datetime, timezone
from pathlib import Path

from local_agent_runtime.audit.logger import (
    EngineAuditLogger,
    build_comment_items_markdown,
    serialize_comment_item,
)
from local_agent_runtime.audit.models import EngineAuditRecord, EngineAuditRunSummary


def _sample_comment(*, comment_id: str, body_text: str, index: int = 1) -> dict:
    return serialize_comment_item(
        {
            "platform_comment_id": comment_id,
            "author_name": f"作者{index}",
            "author_platform_id": f"uid{index:03d}",
            "body_text": body_text,
            "like_count": index * 10,
            "created_time": datetime(2026, 5, 24, 12, index, tzinfo=timezone.utc).isoformat(),
            "raw_payload": {
                "sub_comment_count": index,
                "ip_location": "广东",
                "Cookie": "secret",
                "X-S": "signed",
            },
        },
        index=index,
        source_path="api",
    )


def test_serialize_comment_item_includes_full_body_text_and_required_fields():
    item = _sample_comment(comment_id="cmt001", body_text="完整评论正文" * 20, index=1)
    assert len(item["body_text"]) > 100
    assert item["platform_comment_id"] == "cmt001"
    assert item["author_name"] == "作者1"
    assert item["author_platform_id"] == "uid001"
    assert item["like_count"] == 10
    assert item["sub_comment_count"] == 1
    assert item["ip_location"] == "广东"
    assert item["source_path"] == "api"
    assert item["root_comment_id"] is None
    assert item["parent_comment_id"] is None
    assert "raw_payload" not in item


def test_serialize_comment_item_uses_missing_for_absent_fields():
    item = serialize_comment_item(
        {
            "platform_comment_id": "cmt002",
            "body_text": "只有正文",
            "raw_payload": {},
        },
        index=2,
        source_path="api",
    )
    assert item["author_name"] == "missing"
    assert item["author_platform_id"] == "missing"
    assert item["like_count"] == "missing"
    assert item["sub_comment_count"] == "missing"
    assert item["ip_location"] == "missing"


def test_build_comment_items_markdown_contains_comment_table():
    items = [_sample_comment(comment_id=f"cmt{i:03d}", body_text=f"评论正文{i}", index=i) for i in range(1, 4)]
    md = build_comment_items_markdown("20260524_cmt001", items)
    assert "# Comment Items 20260524_cmt001" in md
    assert "## body_text" not in md
    assert "XHS Engine Audit" not in md
    assert "| # | comment_id | author | author_id | text | like | sub_comments | create_time | ip_location |" in md
    assert "cmt001" in md
    assert "作者1" in md
    assert "评论正文1" in md
    assert "Cookie" not in md
    assert "X-S" not in md


def test_write_comment_items_and_summary_artifacts(tmp_path: Path):
    items = [_sample_comment(comment_id=f"cmt{i:03d}", body_text=f"评论正文{i}", index=i) for i in range(1, 21)]
    logger = EngineAuditLogger(project_root=tmp_path, run_id="20260524_cmt001")
    artifacts = logger.write_comment_items(items)
    record = EngineAuditRecord("xhs.note.comments", "comment", "ok", items_seen=20, normalized_items=20, source_path="api")
    summary = EngineAuditRunSummary("20260524_cmt001", [record], 100.0, artifacts=artifacts)
    logger.write_summary(summary)

    json_path = tmp_path / "logs" / "audit" / "xhs_engine" / "20260524" / artifacts["comment_items_json"]
    md_path = tmp_path / "logs" / "audit" / "xhs_engine" / "20260524" / artifacts["comment_items_md"]
    assert json_path.exists()
    assert md_path.exists()

    serialized = json.loads(json_path.read_text(encoding="utf-8"))
    assert len(serialized) == 20
    assert serialized[0]["body_text"] == "评论正文1"
    assert serialized[0]["platform_comment_id"] == "cmt001"

    summary_json = json.loads(logger.summary_json_path.read_text(encoding="utf-8"))
    summary_md = logger.summary_md_path.read_text(encoding="utf-8")
    comment_md = md_path.read_text(encoding="utf-8")

    assert summary_json["artifacts"]["comment_items_json"] == artifacts["comment_items_json"]
    assert summary_json["artifacts"]["comment_items_md"] == artifacts["comment_items_md"]
    assert "## Artifacts" in summary_md
    assert artifacts["comment_items_md"] in summary_md
    assert "# XHS Engine Audit 20260524_cmt001" in summary_md
    assert "# Comment Items 20260524_cmt001" in comment_md
    assert "comment | xhs.note.comments" in summary_md
    assert "comment | xhs.note.comments" not in comment_md
    assert "secret" not in json_path.read_text(encoding="utf-8")
