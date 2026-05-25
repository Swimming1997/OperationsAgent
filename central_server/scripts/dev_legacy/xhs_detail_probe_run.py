# legacy DB-coupled smoke tool; not part of the formal Local Agent Runtime.
import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from intelligence_engine.db.init_db import init_db
from intelligence_engine.db.session import SessionLocal
from intelligence_engine.local_agent.xhs_detail_probe_runner import XhsDetailProbeRunner


def parse_args():
    parser = argparse.ArgumentParser(description="Run real XHS Detail probe for pending detail_fetch jobs.")
    parser.add_argument("--center-url", default="http://127.0.0.1:8000")
    parser.add_argument("--cdp-url", default="http://127.0.0.1:9222")
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--no-post", action="store_true")
    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    init_db()
    with SessionLocal() as db:
        result = await XhsDetailProbeRunner(db=db, center_base_url=args.center_url).run(
            session_meta={"cdp_url": args.cdp_url},
            limit=args.limit,
            post_ingestion=not args.no_post,
        )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
