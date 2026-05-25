import json
from pathlib import Path

from local_agent_runtime.audit.levels import AuditSeverity
from local_agent_runtime.audit.logger import EngineAuditLogger
from local_agent_runtime.audit.models import EngineAuditIssue, EngineAuditRecord, EngineAuditRunSummary
from local_agent_runtime.audit.note_bundle import (
    build_note_bundle_markdown,
    build_note_bundle_payload,
    classify_note_bundle_status,
    compose_note_bundle_record,
    extract_topics,
    media_download_issues,
)


def _detail_record(*, severity: AuditSeverity = AuditSeverity.P4_INFO, fetch_source: str = "api") -> EngineAuditRecord:
    return EngineAuditRecord(
        capability_key="xhs.note.detail",
        surface="detail",
        status="ok" if severity == AuditSeverity.P4_INFO else "partial",
        severity=severity,
        source_path=fetch_source,
        perf={"api_ms": 120.0, "total_ms": 150.0},
    )


def _comment_record(*, severity: AuditSeverity = AuditSeverity.P4_INFO, source_path: str = "api") -> EngineAuditRecord:
    return EngineAuditRecord(
        capability_key="xhs.note.comments",
        surface="comment",
        status="ok" if severity == AuditSeverity.P4_INFO else "failed",
        severity=severity,
        source_path=source_path,
        perf={"api_ms": 80.0, "total_ms": 90.0},
    )


def _sample_bundle_input(*, detail_record, comment_record, downloaded_images=None, extra_issues=None):
    body_text = "地理农业相关#论文投稿[话题]# #期刊投稿[话题]#"
    return build_note_bundle_payload(
        run_id="20260524_bundle001",
        input_url="https://www.xiaohongshu.com/explore/note001?xsec_token=abc&xsec_source=pc_feed",
        platform_context={
            "note_id": "note001",
            "xsec_source": "pc_feed",
            "xsec_source_effective": "pc_feed",
            "xsec_source_status": "provided",
            "source_surface": "manual_url",
        },
        detail_item={
            "note_id": "note001",
            "title": "标题",
            "author_name": "作者",
            "author_platform_id": "uid001",
            "body_text": body_text,
            "like_count": 10,
            "comment_count": 20,
            "collect_count": 3,
            "share_count": 4,
            "image_urls": ["https://img.example/1.webp"],
            "video_url": None,
            "fetch_source": "api",
            "canonical_url": "https://www.xiaohongshu.com/explore/note001",
            "downloaded_images": downloaded_images
            or [
                {
                    "index": 1,
                    "source_url": "https://img.example/1.webp",
                    "local_path": "media/detail_note001/image_01.webp",
                    "bytes": 123,
                    "status": "ok",
                }
            ],
        },
        detail_snapshot={"publish_time": "2026-05-22T12:00:00+08:00"},
        comment_items=[
            {
                "index": 1,
                "platform_comment_id": "cmt001",
                "author_name": "评论者",
                "body_text": "评论正文",
                "like_count": 1,
                "sub_comment_count": 0,
                "created_at": "2026-05-22 12:00",
                "ip_location": "广东",
            }
        ],
        detail_record=detail_record,
        comment_record=comment_record,
        extra_issues=extra_issues or [],
        artifacts={
            "note_bundle_json": "engine_audit_20260524_bundle001.note_bundle.json",
            "note_bundle_md": "engine_audit_20260524_bundle001.note_bundle.md",
            "note_bundle_media_dir": "media/detail_note001/",
        },
        total_ms=500.0,
        fetched_at="2026-05-24T12:00:00+00:00",
    )


def test_extract_topics_from_body_text():
    topics = extract_topics("地理农业相关#论文投稿[话题]# #期刊投稿[话题]#")
    assert topics == ["论文投稿", "期刊投稿"]


def test_note_bundle_json_structure_is_complete():
    bundle = _sample_bundle_input(detail_record=_detail_record(), comment_record=_comment_record())
    assert bundle["context"]["note_id"] == "note001"
    assert bundle["identity"]["dedupe_key"] == "xhs:note001"
    assert bundle["detail"]["body_text"].startswith("地理农业相关")
    assert bundle["detail"]["topics"] == ["论文投稿", "期刊投稿"]
    assert bundle["media"]["image_count"] == 1
    assert bundle["comments"]["level1_count"] == 1
    assert bundle["audit"]["detail_fetch_source"] == "api"
    assert bundle["audit"]["comment_fetch_source"] == "api"
    assert "Cookie" not in json.dumps(bundle, ensure_ascii=False)


def test_note_bundle_markdown_contains_required_sections():
    bundle = _sample_bundle_input(detail_record=_detail_record(), comment_record=_comment_record())
    md = build_note_bundle_markdown(bundle)
    assert "# XHS Note Bundle 20260524_bundle001" in md
    assert "## Basic" in md
    assert "## Body" in md
    assert "地理农业相关#论文投稿[话题]#" in md
    assert "## Metrics" in md
    assert "## Media" in md
    assert "![image_01.webp](media/detail_note001/image_01.webp)" in md
    assert "## Comments" in md
    assert "cmt001" in md


def test_note_bundle_severity_p4_when_detail_and_comment_ok():
    status, severity = classify_note_bundle_status(
        detail_record=_detail_record(),
        comment_record=_comment_record(),
    )
    assert status == "ok"
    assert severity == AuditSeverity.P4_INFO
    bundle = _sample_bundle_input(detail_record=_detail_record(), comment_record=_comment_record())
    assert bundle["audit"]["severity"] == "P4_INFO"


def test_note_bundle_failed_when_detail_fails():
    detail_record = _detail_record(severity=AuditSeverity.P2_MAJOR)
    detail_record = EngineAuditRecord(
        capability_key="xhs.note.detail",
        surface="detail",
        status="partial",
        severity=AuditSeverity.P2_MAJOR,
        issues=[
            EngineAuditIssue(
                AuditSeverity.P2_MAJOR,
                "xhs.note.detail",
                "detail",
                "note_unavailable",
                "detail failed",
            )
        ],
        source_path="api",
    )
    status, severity = classify_note_bundle_status(detail_record=detail_record, comment_record=_comment_record())
    assert status == "failed"
    assert severity == AuditSeverity.P2_MAJOR


def test_note_bundle_partial_when_comment_fails():
    comment_record = EngineAuditRecord(
        capability_key="xhs.note.comments",
        surface="comment",
        status="missing_xsec_context",
        severity=AuditSeverity.P2_MAJOR,
        issues=[
            EngineAuditIssue(
                AuditSeverity.P2_MAJOR,
                "xhs.note.comments",
                "comment",
                "missing_xsec_context",
                "comment failed",
            )
        ],
        source_path="api",
    )
    status, severity = classify_note_bundle_status(detail_record=_detail_record(), comment_record=comment_record)
    assert status == "partial"
    assert severity == AuditSeverity.P2_MAJOR


def test_media_download_failure_records_issue_without_failing_detail():
    issues = media_download_issues(
        [
            {
                "index": 1,
                "source_url": "https://img.example/1.webp",
                "status": "failed",
                "error": "timeout",
            }
        ]
    )
    assert len(issues) == 1
    assert issues[0].severity == AuditSeverity.P3_MINOR
    assert issues[0].code == "media_download_failed"
    detail_record = _detail_record()
    bundle = _sample_bundle_input(
        detail_record=detail_record,
        comment_record=_comment_record(),
        extra_issues=issues,
    )
    assert bundle["audit"]["status"] == "ok"
    assert bundle["audit"]["severity"] == "P4_INFO"
    assert any(issue["code"] == "media_download_failed" for issue in bundle["audit"]["issues"])


def test_write_note_bundle_and_summary_artifacts(tmp_path: Path):
    bundle = _sample_bundle_input(detail_record=_detail_record(), comment_record=_comment_record())
    logger = EngineAuditLogger(project_root=tmp_path, run_id="20260524_bundle001")
    artifacts = logger.write_note_bundle(bundle)
    record = compose_note_bundle_record(
        bundle=bundle,
        detail_record=_detail_record(),
        comment_record=_comment_record(),
        extra_issues=[],
        perf={"total_ms": 500.0},
    )
    summary = EngineAuditRunSummary("20260524_bundle001", [record], 500.0, artifacts=artifacts)
    logger.write_summary(summary)

    json_path = tmp_path / "logs" / "audit" / "xhs_engine" / "20260524" / artifacts["note_bundle_json"]
    md_path = tmp_path / "logs" / "audit" / "xhs_engine" / "20260524" / artifacts["note_bundle_md"]
    assert json_path.exists()
    assert md_path.exists()
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["detail"]["body_text"].startswith("地理农业相关")
    assert payload["comments"]["level1_count"] == 1
    summary_md = logger.summary_md_path.read_text(encoding="utf-8")
    assert artifacts["note_bundle_json"] in summary_md
