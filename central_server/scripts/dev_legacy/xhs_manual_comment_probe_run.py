# legacy DB-coupled smoke tool; not part of the formal Local Agent Runtime.
import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from intelligence_engine.db.init_db import init_db
from intelligence_engine.db.session import SessionLocal
from intelligence_engine.local_agent.xhs_manual_comment_probe_runner import XhsManualCommentProbeRunner


def parse_args():
    parser = argparse.ArgumentParser(description="Run XHS Comment probe for manually supplied note URLs.")
    parser.add_argument("urls", nargs="+")
    parser.add_argument("--center-url", default="http://127.0.0.1:8000")
    parser.add_argument("--cdp-url", default="http://127.0.0.1:9222")
    parser.add_argument("--max-comments", type=int, default=20)
    parser.add_argument("--no-post", action="store_true")
    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    init_db()
    with SessionLocal() as db:
        result = await XhsManualCommentProbeRunner(db=db, center_base_url=args.center_url).run(
            urls=args.urls,
            session_meta={"cdp_url": args.cdp_url},
            max_comments=args.max_comments,
            post_ingestion=not args.no_post,
        )
    summary = {
        "selected_url_count": result.get("selected_url_count"),
        "success_count": result.get("success_count"),
        "failed_count": result.get("failed_count"),
        "comment_snapshot_count": result.get("comment_snapshot_count"),
        "field_report": result.get("field_report"),
        "keyword_hits": result.get("keyword_hits"),
        "comment_surface_unavailable_urls": result.get("comment_surface_unavailable_urls"),
        "successes": result.get("successes"),
        "failures": result.get("failures"),
        "prepare_failures": result.get("prepare_failures"),
        "prepared_urls": result.get("prepared_urls"),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
