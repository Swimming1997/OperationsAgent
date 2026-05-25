from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

from local_agent_runtime.audit.models import EngineAuditRecord, EngineAuditRunSummary
from local_agent_runtime.audit.redaction import redact_mapping
from local_agent_runtime.contracts import FeedCandidateInput
from local_agent_runtime.enums import ContentType


HOMEFEED_SENSITIVE_KEYS = frozenset(
    {
        "cookie",
        "cookies",
        "authorization",
        "headers",
        "x-s",
        "x-t",
        "x-s-common",
    }
)


SELF_INFO_MD_FIELDS = (
    "login_status",
    "nickname",
    "user_id",
    "red_id",
    "stable_user_key",
    "home_url",
    "avatar_url",
    "source",
)


def _self_info_field_source(account_summary: dict[str, Any], field: str) -> str:
    field_sources = account_summary.get("field_sources") or {}
    if field in field_sources:
        return str(field_sources[field])
    source_key = f"{field}_source"
    if source_key in account_summary:
        return str(account_summary[source_key])
    if field == "login_status":
        return "self_info"
    if field == "source":
        return "api"
    return "missing"


def self_info_markdown_section(account_summary: dict[str, Any]) -> list[str]:
    lines = ["", "## Self Info", "", "| field | value | source |", "|---|---|---|"]
    for field in SELF_INFO_MD_FIELDS:
        value = account_summary.get(field, "missing")
        source = _self_info_field_source(account_summary, field)
        lines.append(f"| {field} | {value} | {source} |")
    missing_reasons = account_summary.get("missing_reasons") or {}
    for field, reason in missing_reasons.items():
        lines.append(f"| {field}_missing_reason | {reason} | audit |")
    return lines


def record_to_log_dict(record: EngineAuditRecord) -> dict:
    payload = redact_mapping(record.to_dict())
    if record.account_summary is not None:
        payload["account_summary"] = record.account_summary
    return payload


def sanitize_homefeed_raw_payload(raw: Any) -> Any:
    if isinstance(raw, dict):
        return {
            str(key): sanitize_homefeed_raw_payload(value)
            for key, value in raw.items()
            if str(key).lower() not in HOMEFEED_SENSITIVE_KEYS
        }
    if isinstance(raw, list):
        return [sanitize_homefeed_raw_payload(item) for item in raw[:50]]
    if isinstance(raw, str):
        return raw if len(raw) <= 2000 else raw[:2000] + "..."
    return raw


def _homefeed_content_type_label(content_type: ContentType | str) -> str:
    value = content_type.value if isinstance(content_type, ContentType) else str(content_type)
    if value == ContentType.VIDEO.value:
        return "video"
    if value == ContentType.IMAGE_TEXT.value:
        return "note"
    return "unknown"


def serialize_homefeed_item(item: FeedCandidateInput, *, index: int) -> dict[str, Any]:
    like_count = item.visible_like_count
    return {
        "index": index,
        "platform_content_id": item.platform_content_id,
        "title_or_summary": item.title_or_summary,
        "author_name": item.author_name,
        "author_platform_id": item.author_platform_id,
        "visible_like_count": str(like_count) if like_count is not None else None,
        "canonical_url": item.canonical_url,
        "cover_url": item.cover_url,
        "content_type": _homefeed_content_type_label(item.content_type),
        "feed_position": item.feed_position,
        "discovered_at": item.discovered_at.isoformat() if item.discovered_at else None,
        "has_xhs_context": bool((item.platform_context or {}).get("api_detail_ready")),
        "xsec_source_effective": (item.platform_context or {}).get("xsec_source_effective"),
        "xsec_source_status": (item.platform_context or {}).get("xsec_source_status"),
        "raw_payload": sanitize_homefeed_raw_payload(item.raw_payload),
    }


def _markdown_table_cell(value: Any, *, max_len: int | None = None) -> str:
    if value is None:
        text = ""
    else:
        text = str(value).replace("|", "\\|").replace("\n", " ")
    if max_len is not None and len(text) > max_len:
        return text[:max_len] + "..."
    return text


def build_homefeed_items_markdown(run_id: str, items: list[dict[str, Any]]) -> str:
    lines = [
        f"# Homefeed Items {run_id}",
        "",
        "| # | note_id | title | author | like | has_url | has_cover | url |",
        "|---:|---|---|---|---:|---|---|---|",
    ]
    for item in items[:20]:
        lines.append(
            "| {index} | {note_id} | {title} | {author} | {like} | {has_url} | {has_cover} | {url} |".format(
                index=item.get("index", ""),
                note_id=_markdown_table_cell(item.get("platform_content_id")),
                title=_markdown_table_cell(item.get("title_or_summary"), max_len=80),
                author=_markdown_table_cell(item.get("author_name")),
                like=_markdown_table_cell(item.get("visible_like_count")),
                has_url="yes" if item.get("canonical_url") else "no",
                has_cover="yes" if item.get("cover_url") else "no",
                url=_markdown_table_cell(item.get("canonical_url")),
            )
        )
    return "\n".join(lines) + "\n"


def artifacts_markdown_section(artifacts: dict[str, str]) -> list[str]:
    if not artifacts:
        return []
    lines = ["", "## Artifacts", ""]
    if artifacts.get("homefeed_items_json"):
        lines.append(f"- homefeed_items.json: {artifacts['homefeed_items_json']}")
    if artifacts.get("homefeed_items_md"):
        lines.append(f"- homefeed_items.md: {artifacts['homefeed_items_md']}")
    if artifacts.get("search_api_items_json"):
        lines.append(f"- search_api_items.json: {artifacts['search_api_items_json']}")
    if artifacts.get("search_api_items_md"):
        lines.append(f"- search_api_items.md: {artifacts['search_api_items_md']}")
    if artifacts.get("detail_item_json"):
        lines.append(f"- detail_item.json: {artifacts['detail_item_json']}")
    if artifacts.get("detail_item_md"):
        lines.append(f"- detail_item.md: {artifacts['detail_item_md']}")
    if artifacts.get("detail_media_dir"):
        lines.append(f"- media_dir: {artifacts['detail_media_dir']}")
    if artifacts.get("comment_items_json"):
        lines.append(f"- comment_items.json: {artifacts['comment_items_json']}")
    if artifacts.get("comment_items_md"):
        lines.append(f"- comment_items.md: {artifacts['comment_items_md']}")
    if artifacts.get("note_bundle_json"):
        lines.append(f"- note_bundle.json: {artifacts['note_bundle_json']}")
    if artifacts.get("note_bundle_md"):
        lines.append(f"- note_bundle.md: {artifacts['note_bundle_md']}")
    if artifacts.get("note_bundle_media_dir"):
        lines.append(f"- media_dir: {artifacts['note_bundle_media_dir']}")
    return lines


def _comment_field_or_missing(value: Any) -> Any:
    if value is None or value == "":
        return "missing"
    return value


def _first_comment_raw_value(raw: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = raw.get(key)
        if value not in (None, "", [], {}):
            return value
    return None


def _format_comment_created_at(value: Any) -> str:
    if value in (None, ""):
        return "missing"
    text = str(value).strip()
    if not text:
        return "missing"
    normalized = text.replace("Z", "+00:00")
    try:
        from datetime import datetime

        parsed = datetime.fromisoformat(normalized)
        return parsed.strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return text


def serialize_comment_item(item: dict[str, Any], *, index: int, source_path: str | None = None) -> dict[str, Any]:
    raw = item.get("raw_payload") or {}
    parent_comment_id = item.get("parent_platform_comment_id")
    if parent_comment_id in (None, "", 0, "0"):
        parent_comment_id = _first_comment_raw_value(raw, "parent_comment_id", "parentCommentId")
        if parent_comment_id in (None, "", 0, "0"):
            target_comment = raw.get("target_comment") or raw.get("targetComment") or {}
            parent_comment_id = target_comment.get("id")
    root_comment_id = _first_comment_raw_value(raw, "root_comment_id", "rootCommentId")
    created_at = item.get("created_time") or _first_comment_raw_value(raw, "create_time", "createTime", "created_time", "time")
    sub_comment_count = _first_comment_raw_value(raw, "sub_comment_count", "subCommentCount")
    ip_location = _first_comment_raw_value(raw, "ip_location", "ipLocation")
    like_count = item.get("like_count")
    return {
        "index": index,
        "platform_comment_id": _comment_field_or_missing(item.get("platform_comment_id")),
        "author_name": _comment_field_or_missing(item.get("author_name")),
        "author_platform_id": _comment_field_or_missing(item.get("author_platform_id")),
        "body_text": item.get("body_text") or "missing",
        "like_count": like_count if like_count is not None else "missing",
        "sub_comment_count": sub_comment_count if sub_comment_count is not None else "missing",
        "created_at": _format_comment_created_at(created_at),
        "ip_location": ip_location if ip_location is not None else "missing",
        "root_comment_id": root_comment_id if root_comment_id not in (None, "", 0, "0") else None,
        "parent_comment_id": parent_comment_id if parent_comment_id not in (None, "", 0, "0") else None,
        "source_path": source_path or item.get("source_path") or "missing",
    }


def build_comment_items_markdown(run_id: str, items: list[dict[str, Any]]) -> str:
    lines = [
        f"# Comment Items {run_id}",
        "",
        "| # | comment_id | author | author_id | text | like | sub_comments | create_time | ip_location |",
        "|---:|---|---|---|---|---:|---:|---|---|",
    ]
    for item in items:
        lines.append(
            "| {index} | {comment_id} | {author} | {author_id} | {text} | {like} | {sub_comments} | {create_time} | {ip_location} |".format(
                index=item.get("index", ""),
                comment_id=_markdown_table_cell(item.get("platform_comment_id")),
                author=_markdown_table_cell(item.get("author_name")),
                author_id=_markdown_table_cell(item.get("author_platform_id")),
                text=_markdown_table_cell(item.get("body_text"), max_len=120),
                like=_markdown_table_cell(item.get("like_count")),
                sub_comments=_markdown_table_cell(item.get("sub_comment_count")),
                create_time=_markdown_table_cell(item.get("created_at")),
                ip_location=_markdown_table_cell(item.get("ip_location")),
            )
        )
    return "\n".join(lines) + "\n"


def build_detail_item_markdown(run_id: str, item: dict[str, Any]) -> str:
    body_text = str(item.get("body_text") or "")
    lines = [
        f"# Detail Item {run_id}",
        "",
        "## Basic",
        "",
        "| field | value |",
        "|---|---|",
    ]
    for field in (
        "note_id",
        "title",
        "author_name",
        "author_platform_id",
        "like_count",
        "comment_count",
        "collect_count",
        "share_count",
        "image_count",
        "video_url_present",
        "fetch_source",
        "api_success",
        "canonical_url",
    ):
        lines.append(f"| {field} | {_markdown_table_cell(item.get(field))} |")
    lines.extend(["", "## body_text", "", body_text or "(empty)", "", "## image_urls", ""])
    downloaded_by_index = {entry.get("index"): entry for entry in item.get("downloaded_images") or []}
    lines.extend(["| # | source_url | downloaded | local_path | bytes |", "|---:|---|---|---|---:|"])
    for index, source_url in enumerate(item.get("image_urls") or [], start=1):
        downloaded = downloaded_by_index.get(index) or {}
        status = downloaded.get("status")
        lines.append(
            "| {index} | {source_url} | {downloaded} | {local_path} | {bytes} |".format(
                index=index,
                source_url=_markdown_table_cell(source_url),
                downloaded="yes" if status == "ok" else ("no" if status == "failed" else "no"),
                local_path=_markdown_table_cell(downloaded.get("local_path") or downloaded.get("error") or ""),
                bytes=_markdown_table_cell(downloaded.get("bytes")),
            )
        )
    lines.extend(["", "## downloaded_images", ""])
    for downloaded in item.get("downloaded_images") or []:
        if downloaded.get("status") == "ok" and downloaded.get("local_path"):
            local_path = str(downloaded["local_path"]).replace("\\", "/")
            filename = local_path.rsplit("/", 1)[-1]
            lines.append(f"![{filename}]({local_path})")
        elif downloaded.get("status") == "failed":
            lines.append(f"- image_{downloaded.get('index', '?'):02d}: download failed — {downloaded.get('error') or 'unknown error'}")
    return "\n".join(lines) + "\n"


def serialize_detail_item(
    *,
    note_id: str,
    url: str,
    snapshot: dict[str, Any],
    diagnostics: dict[str, Any],
    downloaded_images: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    body_text = snapshot.get("body_text") or ""
    image_urls = list(snapshot.get("image_urls") or [])
    video_url = snapshot.get("video_url")
    return {
        "note_id": note_id,
        "title": snapshot.get("title"),
        "author_name": snapshot.get("author_name"),
        "author_platform_id": snapshot.get("author_platform_id"),
        "body_text": body_text,
        "like_count": snapshot.get("like_count"),
        "comment_count": snapshot.get("comment_count"),
        "collect_count": snapshot.get("collect_count"),
        "share_count": snapshot.get("share_count"),
        "image_count": len(image_urls),
        "image_urls": image_urls,
        "downloaded_images": downloaded_images or [],
        "video_url": video_url,
        "video_url_present": bool(video_url),
        "fetch_source": diagnostics.get("fetch_source"),
        "canonical_url": diagnostics.get("canonical_url") or url,
        "api_attempted": diagnostics.get("api_attempted"),
        "api_success": diagnostics.get("api_success"),
        "xsec_source_effective": diagnostics.get("xsec_source_effective"),
        "xsec_source_status": diagnostics.get("xsec_source_status"),
        "suspect_author": diagnostics.get("suspect_author"),
    }


def downloaded_media_to_dict(items: list[Any]) -> list[dict[str, Any]]:
    from dataclasses import asdict, is_dataclass

    result: list[dict[str, Any]] = []
    for item in items:
        if is_dataclass(item):
            result.append(asdict(item))
        elif isinstance(item, dict):
            result.append(item)
    return result


def build_search_api_items_markdown(run_id: str, items: list[dict[str, Any]]) -> str:
    lines = [
        f"# Search API Items {run_id}",
        "",
        "| # | note_id | title | author | has_token | has_source | detail_ready | url |",
        "|---:|---|---|---|---|---|---|---|",
    ]
    for item in items[:10]:
        lines.append(
            "| {index} | {note_id} | {title} | {author} | {has_token} | {has_source} | {detail_ready} | {url} |".format(
                index=item.get("index", ""),
                note_id=_markdown_table_cell(item.get("platform_content_id")),
                title=_markdown_table_cell(item.get("title_or_summary"), max_len=80),
                author=_markdown_table_cell(item.get("author_name")),
                has_token="yes" if item.get("xsec_token") else "no",
                has_source="yes" if item.get("xsec_source") else "no",
                detail_ready="yes" if item.get("api_detail_ready") else "no",
                url=_markdown_table_cell(item.get("canonical_url")),
            )
        )
    return "\n".join(lines) + "\n"


class EngineAuditLogger:
    def __init__(self, *, project_root: Path, run_id: str):
        self.run_id = run_id
        self.output_dir = project_root / "logs" / "audit" / "xhs_engine" / run_id[:8]
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.ndjson_path = self.output_dir / f"engine_audit_{run_id}.ndjson"
        self.summary_json_path = self.output_dir / f"engine_audit_{run_id}.summary.json"
        self.summary_md_path = self.output_dir / f"engine_audit_{run_id}.summary.md"

    def write_homefeed_items(self, items: list[FeedCandidateInput]) -> dict[str, str]:
        json_name = f"engine_audit_{self.run_id}.homefeed_items.json"
        md_name = f"engine_audit_{self.run_id}.homefeed_items.md"
        serialized = [serialize_homefeed_item(item, index=index) for index, item in enumerate(items, start=1)]
        self.output_dir.joinpath(json_name).write_text(
            json.dumps(serialized, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        self.output_dir.joinpath(md_name).write_text(
            build_homefeed_items_markdown(self.run_id, serialized),
            encoding="utf-8",
        )
        return {
            "homefeed_items_json": json_name,
            "homefeed_items_md": md_name,
        }

    def write_search_api_items(self, items: list[dict[str, Any]]) -> dict[str, str]:
        json_name = f"engine_audit_{self.run_id}.search_api_items.json"
        md_name = f"engine_audit_{self.run_id}.search_api_items.md"
        self.output_dir.joinpath(json_name).write_text(
            json.dumps(items, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        self.output_dir.joinpath(md_name).write_text(
            build_search_api_items_markdown(self.run_id, items),
            encoding="utf-8",
        )
        return {
            "search_api_items_json": json_name,
            "search_api_items_md": md_name,
        }

    def detail_media_dir(self, note_id: str) -> Path:
        return self.output_dir / "media" / f"detail_{note_id}"

    def write_detail_item(self, item: dict[str, Any]) -> dict[str, str]:
        json_name = f"engine_audit_{self.run_id}.detail_item.json"
        md_name = f"engine_audit_{self.run_id}.detail_item.md"
        note_id = str(item.get("note_id") or "unknown")
        media_dir_name = f"media/detail_{note_id}/"
        self.output_dir.joinpath(json_name).write_text(
            json.dumps(item, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        self.output_dir.joinpath(md_name).write_text(
            build_detail_item_markdown(self.run_id, item),
            encoding="utf-8",
        )
        return {
            "detail_item_json": json_name,
            "detail_item_md": md_name,
            "detail_media_dir": media_dir_name,
        }

    def write_comment_items(self, items: list[dict[str, Any]]) -> dict[str, str]:
        json_name = f"engine_audit_{self.run_id}.comment_items.json"
        md_name = f"engine_audit_{self.run_id}.comment_items.md"
        self.output_dir.joinpath(json_name).write_text(
            json.dumps(items, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        self.output_dir.joinpath(md_name).write_text(
            build_comment_items_markdown(self.run_id, items),
            encoding="utf-8",
        )
        return {
            "comment_items_json": json_name,
            "comment_items_md": md_name,
        }

    def write_note_bundle(self, bundle: dict[str, Any]) -> dict[str, str]:
        from local_agent_runtime.audit.note_bundle import build_note_bundle_markdown

        json_name = f"engine_audit_{self.run_id}.note_bundle.json"
        md_name = f"engine_audit_{self.run_id}.note_bundle.md"
        note_id = str((bundle.get("context") or {}).get("note_id") or "unknown")
        media_dir_name = f"media/detail_{note_id}/"
        self.output_dir.joinpath(json_name).write_text(
            json.dumps(bundle, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        self.output_dir.joinpath(md_name).write_text(
            build_note_bundle_markdown(bundle),
            encoding="utf-8",
        )
        return {
            "note_bundle_json": json_name,
            "note_bundle_md": md_name,
            "note_bundle_media_dir": media_dir_name,
        }

    def write_records(self, records: Iterable[EngineAuditRecord]) -> None:
        with self.ndjson_path.open("w", encoding="utf-8", newline="\n") as handle:
            for record in records:
                handle.write(json.dumps(record_to_log_dict(record), ensure_ascii=False) + "\n")

    def write_summary(self, summary: EngineAuditRunSummary) -> None:
        summary_dict = summary.to_dict()
        payload = redact_mapping(summary_dict)
        if summary_dict.get("self_info"):
            payload["self_info"] = summary_dict["self_info"]
        if summary_dict.get("artifacts"):
            payload["artifacts"] = summary_dict["artifacts"]
        self.summary_json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        lines = [
            f"# XHS Engine Audit {summary.run_id}",
            "",
            f"- severity: {summary.severity.value}",
            f"- total_ms: {summary.total_ms:.2f}",
            f"- surface_count: {len(summary.records)}",
            "",
            "| surface | capability | status | severity | items | normalized | source |",
            "|---|---|---|---|---:|---:|---|",
        ]
        self_info_summary = None
        for record in summary.records:
            lines.append(
                f"| {record.surface} | {record.capability_key} | {record.status} | {record.severity.value} | "
                f"{record.items_seen} | {record.normalized_items} | {record.source_path or ''} |"
            )
            if record.surface == "self_info" and record.account_summary:
                self_info_summary = record.account_summary
        if self_info_summary:
            lines.extend(self_info_markdown_section(self_info_summary))
        lines.extend(artifacts_markdown_section(summary.artifacts))
        self.summary_md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
