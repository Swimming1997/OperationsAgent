from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def render_smoke_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# XHS Capability Smoke Report",
        "",
        f"- capability: {report.get('capability')}",
        f"- profile_key: {report.get('profile_key')}",
        f"- status: {report.get('status')}",
        f"- error_code: {report.get('error_code')}",
        f"- item_count: {report.get('item_count')}",
        f"- total_ms: {(report.get('timings_ms') or {}).get('total', 0)}",
        f"- screenshot: {(report.get('diagnostics') or {}).get('screenshot_path', '')}",
        f"- html: {(report.get('diagnostics') or {}).get('html_path', '')}",
        "",
        "## Requested Filter",
        "",
        "```json",
        json.dumps(report.get("requested_filter_context") or {}, ensure_ascii=False, indent=2),
        "```",
        "",
        "## Applied Filter",
        "",
        "```json",
        json.dumps(report.get("applied_filter_context"), ensure_ascii=False, indent=2),
        "```",
        "",
        f"- filter_apply_status: {report.get('filter_apply_status')}",
        "",
    ]

    requested = report.get("requested_filter_context") or {}
    applied = report.get("applied_filter_context")
    if applied and applied != requested:
        lines.append("> requested 与 applied 存在差异，请勿把 requested 当作已生效筛选。")
        lines.append("")
    elif report.get("filter_apply_status") == "not_implemented":
        lines.append("> 当前仅记录 requested filter，页面筛选控件尚未确认应用。")
        lines.append("")

    lines.extend(["## Sample Items", ""])
    items = report.get("items") or []
    capability = report.get("capability")
    if capability == "search_suggest":
        payload = report.get("payload") or {}
        for item in (payload.get("suggestions") or items)[:5]:
            lines.append(f"- rank={item.get('suggestion_rank')} keyword={item.get('suggested_keyword')}")
    elif capability == "creator_notes":
        payload = report.get("payload") or {}
        lines.append(f"- creator_name: {payload.get('creator_name')}")
        for item in (payload.get("notes") or items)[:5]:
            lines.append(
                f"- rank={item.get('creator_note_rank')} title={item.get('title')} url={item.get('canonical_url')} like={item.get('visible_like_count')}"
            )
    elif capability in {"detail", "comments"}:
        payload = report.get("payload") or (items[0] if items else {})
        if capability == "detail":
            lines.append(
                f"- title={payload.get('title')} author={payload.get('author_name')} images={len(payload.get('image_urls') or [])}"
            )
        else:
            for item in items[:5]:
                lines.append(
                    f"- rank={item.get('comment_rank')} author={item.get('comment_author')} text={(item.get('comment_text') or '')[:80]}"
                )
    else:
        for item in items[:5]:
            lines.append(
                f"- rank={item.get('feed_position') or item.get('search_rank')} title={item.get('title')} url={item.get('canonical_url')} author={item.get('author_name')} like={item.get('visible_like_count')}"
            )

    missing = report.get("missing_fields") or {}
    lines.extend(["", "## Missing Fields", ""])
    if missing:
        for field, count in sorted(missing.items(), key=lambda item: (-item[1], item[0])):
            lines.append(f"- {field}: {count}")
    else:
        lines.append("- 无")

    diagnostics = report.get("diagnostics") or {}
    lines.extend(["", "## Diagnostics", ""])
    lines.append(f"- current_url: {diagnostics.get('current_url', '')}")
    lines.append(f"- page_title: {diagnostics.get('page_title', '')}")
    if report.get("error_message"):
        lines.append(f"- error_message: {report.get('error_message')}")
    for key in ("selector_hits", "filter_diagnostics", "login_status", "account_hint"):
        if key in diagnostics:
            lines.append(f"- {key}: {json.dumps(diagnostics.get(key), ensure_ascii=False)}")

    return "\n".join(lines) + "\n"


def write_smoke_outputs(report: dict[str, Any], output_dir: Path) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    capability = str(report.get("capability") or "unknown")
    run_id = str(report.get("run_id") or "unknown")
    base = f"{capability}_{run_id}"
    markdown_path = output_dir / f"{base}.summary.md"
    json_path = output_dir / f"{base}.json"
    ndjson_path = output_dir / f"{base}.ndjson"

    markdown_path.write_text(render_smoke_markdown(report), encoding="utf-8")
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    ndjson_path.write_text(json.dumps(report, ensure_ascii=False) + "\n", encoding="utf-8")

    paths = {
        "markdown": str(markdown_path),
        "json": str(json_path),
        "ndjson": str(ndjson_path),
    }
    diagnostics = report.setdefault("diagnostics", {})
    if diagnostics.get("screenshot_path"):
        paths["screenshot"] = diagnostics["screenshot_path"]
    if diagnostics.get("html_path"):
        paths["html"] = diagnostics["html_path"]
    return paths
