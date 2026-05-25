import json
from datetime import datetime, timezone
from pathlib import Path

from local_agent_runtime.audit.logger import (
    EngineAuditLogger,
    build_homefeed_items_markdown,
    sanitize_homefeed_raw_payload,
    serialize_homefeed_item,
)
from local_agent_runtime.audit.models import EngineAuditRecord, EngineAuditRunSummary
from local_agent_runtime.contracts import FeedCandidateInput
from local_agent_runtime.enums import ContentType, FeedType, Platform, SourceSurface


def _sample_item(*, note_id: str, title: str, with_xsec: bool = False) -> FeedCandidateInput:
    url = f"https://www.xiaohongshu.com/explore/{note_id}"
    if with_xsec:
        url += "?xsec_token=abcdefghijklmnop&xsec_source=pc_feed"
    return FeedCandidateInput(
        platform=Platform.XHS,
        platform_content_id=note_id,
        canonical_url=url,
        content_type=ContentType.IMAGE_TEXT,
        title_or_summary=title,
        cover_url="https://sns-img-qc.xhscdn.com/cover.jpg",
        author_platform_id="5f58bd990000000001003753",
        author_name="作者A",
        visible_like_count=1234,
        source_surface=SourceSurface.XHS_HOME_FEED,
        feed_type=FeedType.XHS_HOME_FEED,
        feed_position=1,
        discovered_at=datetime(2026, 5, 24, 12, 0, tzinfo=timezone.utc),
        raw_payload={"title": title, "Cookie": "secret", "X-S": "signed"},
        platform_context={"has_xsec_context": with_xsec, "api_detail_ready": with_xsec, "note_id": note_id},
    )


def test_serialize_homefeed_item_keeps_full_url_and_strips_sensitive_raw_fields():
    item = _sample_item(note_id="note001", title="SCI投稿经验", with_xsec=True)
    payload = serialize_homefeed_item(item, index=1)
    assert payload["platform_content_id"] == "note001"
    assert payload["title_or_summary"] == "SCI投稿经验"
    assert payload["author_name"] == "作者A"
    assert payload["visible_like_count"] == "1234"
    assert "xsec_token=abcdefghijklmnop" in payload["canonical_url"]
    assert payload["has_xhs_context"] is True
    assert "Cookie" not in payload["raw_payload"]
    assert "X-S" not in payload["raw_payload"]
    assert payload["raw_payload"]["title"] == "SCI投稿经验"


def test_build_homefeed_items_markdown_truncates_title_and_shows_url():
    items = [
        serialize_homefeed_item(_sample_item(note_id="note001", title="短标题"), index=1),
        serialize_homefeed_item(
            _sample_item(note_id="note002", title="中" * 100),
            index=2,
        ),
    ]
    md = build_homefeed_items_markdown("20260524_test001", items)
    assert "# Homefeed Items 20260524_test001" in md
    assert "note001" in md
    assert "作者A" in md
    assert "1234" in md
    assert "yes" in md
    assert "https://www.xiaohongshu.com/explore/note002" in md
    assert ("中" * 80 + "...") in md


def test_write_homefeed_items_and_summary_artifacts(tmp_path: Path):
    items = [_sample_item(note_id=f"note{i:03d}", title=f"标题{i}") for i in range(1, 21)]
    logger = EngineAuditLogger(project_root=tmp_path, run_id="20260524_hf001")
    artifacts = logger.write_homefeed_items(items)
    record = EngineAuditRecord("xhs.feed.home_recommend", "homefeed", "ok", items_seen=30, normalized_items=20)
    summary = EngineAuditRunSummary("20260524_hf001", [record], 100.0, artifacts=artifacts)
    logger.write_summary(summary)

    json_path = tmp_path / "logs" / "audit" / "xhs_engine" / "20260524" / artifacts["homefeed_items_json"]
    md_path = tmp_path / "logs" / "audit" / "xhs_engine" / "20260524" / artifacts["homefeed_items_md"]
    assert json_path.exists()
    assert md_path.exists()

    serialized = json.loads(json_path.read_text(encoding="utf-8"))
    assert len(serialized) == 20
    assert serialized[0]["title_or_summary"] == "标题1"
    assert serialized[0]["canonical_url"].startswith("https://www.xiaohongshu.com/explore/")

    summary_json = json.loads(logger.summary_json_path.read_text(encoding="utf-8"))
    summary_md = logger.summary_md_path.read_text(encoding="utf-8")
    assert summary_json["artifacts"]["homefeed_items_json"] == artifacts["homefeed_items_json"]
    assert "## Artifacts" in summary_md
    assert artifacts["homefeed_items_md"] in summary_md
    assert "secret" not in json_path.read_text(encoding="utf-8")
    assert "Cookie" not in md_path.read_text(encoding="utf-8")
