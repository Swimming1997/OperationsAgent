# legacy DB-coupled smoke tool; not part of the formal Local Agent Runtime.
import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from intelligence_engine.local_agent.xhs_probe_runner import XhsProbeRunner


def parse_args():
    parser = argparse.ArgumentParser(description="Run XHS HomeFeed probe with a local logged-in Chrome session.")
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--account-id", required=True)
    parser.add_argument("--center-url", default="http://127.0.0.1:8000")
    parser.add_argument("--target-count", type=int, default=50)
    parser.add_argument("--cdp-url")
    parser.add_argument("--user-data-dir")
    parser.add_argument("--chrome-executable-path")
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--no-post", action="store_true")
    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    session_meta = {
        "cdp_url": args.cdp_url,
        "user_data_dir": args.user_data_dir,
        "chrome_executable_path": args.chrome_executable_path,
        "headless": args.headless,
    }
    session_meta = {key: value for key, value in session_meta.items() if value not in (None, "")}
    result = await XhsProbeRunner(center_base_url=args.center_url).run(
        job_id=args.job_id,
        account_id=args.account_id,
        session_meta=session_meta,
        target_count=args.target_count,
        post_ingestion=not args.no_post,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
