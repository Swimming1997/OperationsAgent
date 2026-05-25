#!/usr/bin/env python3
"""Smoke-test individual XHS capabilities locally without central_server."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from local_agent_runtime.smoke.runner import CAPABILITIES, SmokeRunOptions, XhsCapabilitySmokeRunner

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def parse_bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Smoke-test a single XHS capability locally.")
    parser.add_argument("--capability", required=True, choices=sorted(CAPABILITIES))
    parser.add_argument("--profile-key", required=True)
    parser.add_argument("--keyword", default=None)
    parser.add_argument("--note-url", default=None)
    parser.add_argument("--creator-url", default=None)
    parser.add_argument("--max-items", type=int, default=20)
    parser.add_argument(
        "--search-sort",
        default="comprehensive",
        choices=["comprehensive", "latest", "most_liked", "most_commented", "most_collected"],
    )
    parser.add_argument("--note-type", default="all", choices=["all", "video", "image_text"])
    parser.add_argument("--publish-time", default="all", choices=["all", "one_day", "one_week", "half_year"])
    parser.add_argument("--headless", default="false")
    parser.add_argument("--save-html", action="store_true")
    parser.add_argument("--save-screenshot", action="store_true")
    parser.add_argument("--cdp-url", default=None, help="Optional CDP URL override instead of profile launch.")
    parser.add_argument("--output-dir", default=None)
    return parser


async def main_async(args: argparse.Namespace) -> int:
    options = SmokeRunOptions(
        capability=args.capability,
        profile_key=args.profile_key,
        project_root=ROOT,
        keyword=args.keyword,
        note_url=args.note_url,
        creator_url=args.creator_url,
        max_items=args.max_items,
        search_sort=args.search_sort,
        note_type=args.note_type,
        publish_time=args.publish_time,
        headless=parse_bool(args.headless),
        save_html=args.save_html,
        save_screenshot=args.save_screenshot,
        cdp_url=args.cdp_url,
        output_dir=Path(args.output_dir) if args.output_dir else None,
    )
    report = await XhsCapabilitySmokeRunner(options).run()
    paths = report.get("output_paths") or {}
    print(f"run_id: {report.get('run_id')}")
    print(f"status: {report.get('status')}")
    print(f"item_count: {report.get('item_count')}")
    print(f"error_code: {report.get('error_code')}")
    if paths.get("markdown"):
        print(f"markdown: {paths['markdown']}")
    if paths.get("json"):
        print(f"json: {paths['json']}")
    if paths.get("ndjson"):
        print(f"ndjson: {paths['ndjson']}")
    if paths.get("screenshot"):
        print(f"screenshot: {paths['screenshot']}")
    if paths.get("html"):
        print(f"html: {paths['html']}")
    return 0 if report.get("status") in {"success", "partial"} else 1


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    raise SystemExit(asyncio.run(main_async(args)))


if __name__ == "__main__":
    main()
