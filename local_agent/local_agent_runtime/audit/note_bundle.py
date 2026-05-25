from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from local_agent_runtime.audit.levels import AuditSeverity
from local_agent_runtime.audit.logger import _markdown_table_cell
from local_agent_runtime.audit.models import EngineAuditIssue, EngineAuditRecord


TOPIC_PATTERN = re.compile(r"#([^#\[\]]+)\[话题\]#")


def extract_topics(body_text: str | None) -> list[str]:
    if not body_text:
        return []
    return list(dict.fromkeys(TOPIC_PATTERN.findall(body_text)))


def _issue_to_dict(issue: EngineAuditIssue) -> dict[str, Any]:
    return {
        "severity": issue.severity.value,
        "capability_key": issue.capability_key,
        "surface": issue.surface,
        "code": issue.code,
        "message": issue.message,
        "evidence": issue.evidence,
        "suggested_action": issue.suggested_action,
    }


def media_download_issues(downloaded_images: list[dict[str, Any]]) -> list[EngineAuditIssue]:
    issues: list[EngineAuditIssue] = []
    for item in downloaded_images:
        if item.get("status") != "failed":
            continue
        issues.append(
            EngineAuditIssue(
                AuditSeverity.P3_MINOR,
                "xhs.note.bundle",
                "note_bundle",
                "media_download_failed",
                f"图片下载失败: image_{int(item.get('index') or 0):02d}",
                {
                    "index": item.get("index"),
                    "source_url": item.get("source_url"),
                    "error": item.get("error"),
                },
            )
        )
    return issues


def classify_note_bundle_status(
    *,
    detail_record: EngineAuditRecord,
    comment_record: EngineAuditRecord,
) -> tuple[str, AuditSeverity]:
    if detail_record.severity != AuditSeverity.P4_INFO:
        return "failed", detail_record.severity
    if comment_record.severity != AuditSeverity.P4_INFO:
        return "partial", comment_record.severity
    return "ok", AuditSeverity.P4_INFO


def build_note_bundle_payload(
    *,
    run_id: str,
    input_url: str,
    platform_context: dict[str, Any],
    detail_item: dict[str, Any],
    detail_snapshot: dict[str, Any],
    comment_items: list[dict[str, Any]],
    detail_record: EngineAuditRecord,
    comment_record: EngineAuditRecord,
    extra_issues: list[EngineAuditIssue],
    artifacts: dict[str, str],
    total_ms: float,
    fetched_at: str | None = None,
) -> dict[str, Any]:
    note_id = str(detail_item.get("note_id") or platform_context.get("note_id") or "")
    video_url = detail_item.get("video_url")
    content_type = "video" if video_url else "note"
    body_text = detail_item.get("body_text") or ""
    publish_time = detail_snapshot.get("publish_time")
    issues = [*detail_record.issues, *comment_record.issues, *extra_issues]
    status, severity = classify_note_bundle_status(detail_record=detail_record, comment_record=comment_record)
    downloaded_images = list(detail_item.get("downloaded_images") or [])
    image_urls = list(detail_item.get("image_urls") or [])
    images = []
    for index, source_url in enumerate(image_urls, start=1):
        downloaded = next((item for item in downloaded_images if item.get("index") == index), {})
        images.append(
            {
                "index": index,
                "source_url": source_url,
                "local_path": downloaded.get("local_path"),
                "bytes": downloaded.get("bytes"),
                "status": downloaded.get("status") or "missing",
                "error": downloaded.get("error"),
            }
        )
    return {
        "context": {
            "input_url": input_url,
            "canonical_url": detail_item.get("canonical_url") or input_url,
            "note_id": note_id,
            "xsec_source": platform_context.get("xsec_source_effective") or platform_context.get("xsec_source") or "",
            "xsec_source_status": platform_context.get("xsec_source_status") or "",
            "source_surface": platform_context.get("source_surface") or "manual_url",
            "fetched_at": fetched_at or datetime.now(timezone.utc).isoformat(),
        },
        "identity": {
            "platform": "xhs",
            "platform_content_id": note_id,
            "content_type": content_type,
            "dedupe_key": f"xhs:{note_id}" if note_id else "",
        },
        "detail": {
            "title": detail_item.get("title"),
            "body_text": body_text,
            "topics": extract_topics(body_text),
            "author_name": detail_item.get("author_name"),
            "author_platform_id": detail_item.get("author_platform_id"),
            "like_count": detail_item.get("like_count"),
            "comment_count": detail_item.get("comment_count"),
            "collect_count": detail_item.get("collect_count"),
            "share_count": detail_item.get("share_count"),
            "publish_time": publish_time,
        },
        "media": {
            "image_count": len(image_urls),
            "images": images,
            "video_url": video_url,
        },
        "comments": {
            "level1_count": len(comment_items),
            "items": comment_items,
        },
        "audit": {
            "run_id": run_id,
            "status": status,
            "severity": severity.value,
            "detail_fetch_source": detail_item.get("fetch_source"),
            "comment_fetch_source": comment_record.source_path,
            "total_ms": total_ms,
            "issues": [_issue_to_dict(issue) for issue in issues],
            "artifacts": artifacts,
        },
    }


def build_note_bundle_markdown(bundle: dict[str, Any]) -> str:
    context = bundle.get("context") or {}
    detail = bundle.get("detail") or {}
    media = bundle.get("media") or {}
    comments = bundle.get("comments") or {}
    audit = bundle.get("audit") or {}
    run_id = audit.get("run_id") or ""
    lines = [
        f"# XHS Note Bundle {run_id}",
        "",
        "## Basic",
        "",
        "| field | value |",
        "|---|---|",
    ]
    for field, value in (
        ("note_id", context.get("note_id")),
        ("title", detail.get("title")),
        ("author_name", detail.get("author_name")),
        ("author_platform_id", detail.get("author_platform_id")),
        ("canonical_url", context.get("canonical_url")),
        ("detail_fetch_source", audit.get("detail_fetch_source")),
        ("comment_fetch_source", audit.get("comment_fetch_source")),
    ):
        lines.append(f"| {field} | {_markdown_table_cell(value)} |")
    lines.extend(["", "## Body", "", detail.get("body_text") or "(empty)", "", "## Metrics", "", "| metric | value |", "|---|---:|"])
    for metric in ("like_count", "comment_count", "collect_count", "share_count"):
        lines.append(f"| {metric} | {_markdown_table_cell(detail.get(metric))} |")
    lines.extend(["", "## Media", "", "| # | source_url | local_path | bytes | status |", "|---:|---|---|---:|---|"])
    for image in media.get("images") or []:
        lines.append(
            "| {index} | {source_url} | {local_path} | {bytes} | {status} |".format(
                index=image.get("index", ""),
                source_url=_markdown_table_cell(image.get("source_url")),
                local_path=_markdown_table_cell(image.get("local_path") or image.get("error") or ""),
                bytes=_markdown_table_cell(image.get("bytes")),
                status=_markdown_table_cell(image.get("status")),
            )
        )
    lines.extend(["", ""])
    for image in media.get("images") or []:
        if image.get("status") == "ok" and image.get("local_path"):
            local_path = str(image["local_path"]).replace("\\", "/")
            filename = local_path.rsplit("/", 1)[-1]
            lines.append(f"![{filename}]({local_path})")
        elif image.get("status") == "failed":
            lines.append(f"- image_{int(image.get('index') or 0):02d}: download failed — {image.get('error') or 'unknown error'}")
    lines.extend(["", "## Comments", "", "| # | comment_id | author | text | like | sub_comments | created_at | ip_location |", "|---:|---|---|---|---:|---:|---|---|"])
    for item in comments.get("items") or []:
        lines.append(
            "| {index} | {comment_id} | {author} | {text} | {like} | {sub_comments} | {created_at} | {ip_location} |".format(
                index=item.get("index", ""),
                comment_id=_markdown_table_cell(item.get("platform_comment_id")),
                author=_markdown_table_cell(item.get("author_name")),
                text=_markdown_table_cell(item.get("body_text"), max_len=120),
                like=_markdown_table_cell(item.get("like_count")),
                sub_comments=_markdown_table_cell(item.get("sub_comment_count")),
                created_at=_markdown_table_cell(item.get("created_at")),
                ip_location=_markdown_table_cell(item.get("ip_location")),
            )
        )
    return "\n".join(lines) + "\n"


def compose_note_bundle_record(
    *,
    bundle: dict[str, Any],
    detail_record: EngineAuditRecord,
    comment_record: EngineAuditRecord,
    extra_issues: list[EngineAuditIssue],
    perf: dict[str, float],
) -> EngineAuditRecord:
    audit = bundle.get("audit") or {}
    issues = [*detail_record.issues, *comment_record.issues, *extra_issues]
    return EngineAuditRecord(
        capability_key="xhs.note.bundle",
        surface="note_bundle",
        status=str(audit.get("status") or "ok"),
        severity=AuditSeverity(str(audit.get("severity") or AuditSeverity.P4_INFO.value)),
        items_seen=1 + len((bundle.get("comments") or {}).get("items") or []),
        normalized_items=1 + len((bundle.get("comments") or {}).get("items") or []),
        field_coverage={},
        perf=perf,
        issues=issues,
        source_path="note_bundle",
        payload={
            "note_id": (bundle.get("context") or {}).get("note_id"),
            "detail_fetch_source": audit.get("detail_fetch_source"),
            "comment_fetch_source": audit.get("comment_fetch_source"),
            "comment_count": (bundle.get("comments") or {}).get("level1_count"),
            "image_count": (bundle.get("media") or {}).get("image_count"),
            "downloaded_images_ok": sum(1 for item in (bundle.get("media") or {}).get("images") or [] if item.get("status") == "ok"),
            "downloaded_images_failed": sum(1 for item in (bundle.get("media") or {}).get("images") or [] if item.get("status") == "failed"),
        },
    )
