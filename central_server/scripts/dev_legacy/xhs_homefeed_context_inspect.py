# legacy DB-coupled smoke tool; not part of the formal Local Agent Runtime.
import argparse
import asyncio
import json
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from intelligence_engine.local_agent.xhs_homefeed_context_inspector import XhsHomeFeedContextInspector


def parse_args():
    parser = argparse.ArgumentParser(description="Inspect XHS HomeFeed card xsec context sources.")
    parser.add_argument("--cdp-url", default="http://127.0.0.1:9222")
    parser.add_argument("--sample-count", type=int, default=8)
    parser.add_argument("--click-count", type=int, default=5)
    parser.add_argument("--output", default="")
    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    result = await XhsHomeFeedContextInspector(cdp_url=args.cdp_url).run(
        sample_count=args.sample_count,
        click_count=args.click_count,
    )
    text = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    asyncio.run(main())
