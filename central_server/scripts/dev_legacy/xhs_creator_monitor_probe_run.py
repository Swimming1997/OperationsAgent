# legacy DB-coupled smoke tool; not part of the formal Local Agent Runtime.
import argparse
import asyncio
import json
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from intelligence_engine.db.init_db import init_db
from intelligence_engine.db.session import SessionLocal
from intelligence_engine.local_agent.xhs_creator_monitor_runner import XhsCreatorMonitorRunner


def parse_args():
    parser = argparse.ArgumentParser(description="Run real XHS creator monitor probe for one or two creator profile URLs.")
    parser.add_argument("--cdp-url", default="http://127.0.0.1:9222")
    parser.add_argument("--creator-url", action="append", required=True)
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--repeat", type=int, default=1)
    parser.add_argument("--output", default="")
    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    init_db()
    all_runs = []
    with SessionLocal() as db:
        runner = XhsCreatorMonitorRunner(db=db)
        for run_index in range(args.repeat):
            result = await runner.run_urls(
                creator_urls=args.creator_url[:2],
                session_meta={"cdp_url": args.cdp_url},
                limit_per_creator=args.limit,
            )
            result["run_index"] = run_index + 1
            all_runs.append(result)
    output = {"runs": all_runs} if args.repeat > 1 else all_runs[0]
    text = json.dumps(output, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    asyncio.run(main())
