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
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from local_agent_runtime.connectors.douyin.feed_probe import DouyinFeedProbe
from local_agent_runtime.connectors.douyin.suggest_probe import DouyinSearchSuggestProbe
from local_agent_runtime.sessions.douyin_browser_session import DouyinBrowserSessionProvider
from local_agent_runtime.enums import SessionStatus


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Douyin engine audit (browser intercept)")
    parser.add_argument("--surface", required=True, choices=["session", "homefeed", "search", "suggest"])
    parser.add_argument("--cdp-url", default="http://127.0.0.1:9223")
    parser.add_argument("--keyword", default="考研")
    parser.add_argument("--limit", type=int, default=15)
    parser.add_argument("--sort", default="comprehensive", choices=["comprehensive", "latest", "most_liked"])
    parser.add_argument("--publish-time", default="all", choices=["all", "one_day", "one_week", "half_year"])
    parser.add_argument("--start-rank", type=int, default=0)
    return parser.parse_args()


async def main() -> int:
    args = parse_args()
    provider = DouyinBrowserSessionProvider()
    session = await provider.acquire(session_meta={"cdp_url": args.cdp_url})
    print(f"session status: {session.status.value} — {session.message}")
    print(f"page url: {(session.diagnostics or {}).get('url')}")
    try:
        if args.surface == "session":
            return 0 if session.status == SessionStatus.READY else 1
        if session.status != SessionStatus.READY:
            print("session not ready; finish login in the Chrome window first.")
            return 1
        if args.surface == "suggest":
            items, report = await DouyinSearchSuggestProbe(core_keyword=args.keyword).collect(session.page)
            print("\n== suggest (long-tail keywords) ==")
            print(f"intercepted_responses: {report['intercepted_responses']} (parse_errors={report['intercept_parse_errors']})")
            print(f"typed_selector: {report['typed_selector']}  count: {report['suggestion_count']}")
            print(f"perf: {report['perf']}")
            print("\nlong-tail words (rank | keyword):")
            for it in items:
                print(f"  {it['suggestion_rank']:>2} | {it['suggested_keyword']}")
            return 0
        keyword = args.keyword if args.surface == "search" else None
        probe = DouyinFeedProbe(
            keyword=keyword,
            target_count=args.limit,
            max_scrolls=12,
            sort=args.sort,
            publish_time=args.publish_time,
            start_rank=args.start_rank,
        )
        candidates, report = await probe.collect(session.page)
        print(f"\n== {args.surface} ==")
        print(f"intercepted_responses: {report['intercepted_responses']} (parse_errors={report['intercept_parse_errors']})")
        print(f"raw_awemes_seen: {report['raw_awemes_seen']}  unique: {report['unique_awemes']}  normalized: {report['normalized_items']}")
        print(f"filter: {report.get('requested_filter_context')}  status={report.get('filter_apply_status')}  start_rank={report.get('start_rank')}")
        print(f"scrolls: {report['actual_scroll_count']}")
        print(f"field_coverage: {report['field_coverage']}")
        print(f"perf: {report['perf']}")
        print("\nsample items:")
        for c in candidates[:5]:
            ctype = getattr(c.content_type, "value", c.content_type)
            print(
                f"  [{ctype}] {c.platform_content_id}  "
                f"like={c.visible_like_count}  author={c.author_name}  "
                f"title={(c.title_or_summary or '')[:30]}"
            )
        return 0
    finally:
        await session.close()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
