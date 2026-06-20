from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
REPOSITORY_ROOT = PROJECT_ROOT.parent
for path in (PROJECT_ROOT, REPOSITORY_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from local_agent_runtime.audit.xhs_engine_audit import XhsEngineAuditor
from local_agent_runtime.connectors.xhs.api_client import format_self_info_terminal_lines


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="XHS engine audit v1")
    parser.add_argument("--surface", required=True, choices=["capabilities", "self_info", "homefeed", "search", "search_api", "detail", "comment", "note_bundle", "creator", "smoke", "all"])
    parser.add_argument("--config")
    parser.add_argument("--keyword", default="SCI投稿")
    parser.add_argument("--target-count", type=int, default=20)
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--limit-comments", type=int, default=20)
    parser.add_argument("--url")
    parser.add_argument("--creator-url")
    parser.add_argument("--export-zip", action="store_true")
    return parser.parse_args()


async def main() -> int:
    args = parse_args()
    surfaces = ["self_info", "homefeed", "search", "detail", "comment", "creator"] if args.surface == "all" else [args.surface]
    auditor = XhsEngineAuditor(project_root=PROJECT_ROOT, config_path=Path(args.config) if args.config else None)
    summary, logger = await auditor.run(
        surfaces=surfaces,
        keyword=args.keyword,
        target_count=args.target_count,
        limit=args.limit,
        limit_comments=args.limit_comments,
        url=args.url,
        creator_url=args.creator_url,
    )
    print(f"最高等级: {summary.severity.value}")
    print(f"总耗时: {summary.total_ms:.2f} ms")
    print(f"summary.json: {logger.summary_json_path}")
    print(f"summary.md: {logger.summary_md_path}")
    if args.export_zip:
        print(f"export.zip: {logger.export_bundle()}")
    if args.surface == "capabilities":
        for record in summary.records:
            for item in record.payload.get("capabilities", []):
                print(f"{item['key']}\t{item['layer'].value if hasattr(item['layer'], 'value') else item['layer']}\t{item['status'].value if hasattr(item['status'], 'value') else item['status']}\taudit={item['audit_supported']}")
    if args.surface == "self_info":
        for record in summary.records:
            if record.surface == "self_info" and record.account_summary:
                for line in format_self_info_terminal_lines(status=record.status, account_summary=record.account_summary):
                    print(line)
    if args.surface == "search_api":
        for record in summary.records:
            if record.surface == "search_api":
                payload = record.payload or {}
                print(f"search_api items_count={payload.get('items_count', 0)}")
                print(f"items_with_id={payload.get('items_with_id', 0)}")
                print(f"items_with_xsec_token={payload.get('items_with_xsec_token', 0)}")
                print(f"items_with_xsec_source={payload.get('items_with_xsec_source', 0)}")
                print(f"detail_ready_count={payload.get('detail_ready_count', 0)}")
                for item in (payload.get("sample_items") or [])[:3]:
                    print(
                        f"sample: note_id={item.get('platform_content_id')} "
                        f"title={item.get('title_or_summary')} "
                        f"xsec_source={item.get('xsec_source_effective')}"
                    )
    if args.surface == "detail":
        for record in summary.records:
            if record.surface == "detail":
                payload = record.payload or {}
                print(
                    f"detail: fetch_source={payload.get('fetch_source')}, "
                    f"author={payload.get('author_name')}, "
                    f"severity={record.severity.value}"
                )
    if args.surface == "smoke":
        for record in summary.records:
            if record.surface == "smoke":
                payload = record.payload or {}
                print(f"smoke 选源: {payload.get('selection_source')}")
                print(f"新鲜 URL(脱敏): {payload.get('selected_url_redacted')}")
                print(f"子链路: {payload.get('sub_surfaces')}")
    if args.surface == "note_bundle":
        for record in summary.records:
            if record.surface == "note_bundle":
                payload = record.payload or {}
                print(
                    f"note_bundle: status={record.status}, "
                    f"detail_source={payload.get('detail_fetch_source')}, "
                    f"comment_source={payload.get('comment_fetch_source')}, "
                    f"comments={payload.get('comment_count')}, "
                    f"images_ok={payload.get('downloaded_images_ok')}, "
                    f"severity={record.severity.value}"
                )
                for name in ("note_bundle_json", "note_bundle_md", "note_bundle_media_dir"):
                    if summary.artifacts.get(name):
                        print(f"{name}: {logger.output_dir / summary.artifacts[name]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
