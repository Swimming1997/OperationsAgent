#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from local_agent_runtime.connectors.xhs.search_probe import XhsSearchProbe


async def run_stress(*, keywords: list[str], rounds: int, max_items: int, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = output_dir / f"xhs_engine_stress_{stamp}.ndjson"
    records: list[dict] = []
    for round_index in range(1, rounds + 1):
        record = {
            "round": round_index,
            "keywords": keywords,
            "max_items": max_items,
            "session_acquire_ms": 0,
            "page_goto_ms": 0,
            "initial_wait_ms": 0,
            "scroll_ms": 0,
            "dom_extract_ms": 0,
            "api_ms": 0,
            "normalize_ms": 0,
            "ingestion_ms": 0,
            "total_ms": 0,
            "items_per_second": 0,
            "error_code": None,
        }
        try:
            from playwright.async_api import async_playwright

            probe = XhsSearchProbe(keywords=keywords, max_items=max_items)
            async with async_playwright() as playwright:
                browser = await playwright.chromium.launch(headless=True)
                page = await browser.new_page()
                candidates, report = await probe.collect(page)
                perf = report.get("perf") or {}
                record.update(
                    {
                        "page_goto_ms": perf.get("page_goto_ms", report.get("page_goto_ms", 0)),
                        "scroll_ms": perf.get("scroll_ms", 0),
                        "dom_extract_ms": perf.get("dom_extract_ms", 0),
                        "total_ms": perf.get("total_ms", report.get("total_ms", 0)),
                        "items_per_second": perf.get("items_per_second", 0),
                        "normalized_items": len(candidates),
                    }
                )
                await browser.close()
        except Exception as exc:
            record["error_code"] = exc.__class__.__name__
            record["error_message"] = str(exc)
        records.append(record)
    output_path.write_text("\n".join(json.dumps(item, ensure_ascii=False) for item in records) + "\n", encoding="utf-8")
    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Stress test XHS engine")
    parser.add_argument("--keywords", nargs="+", default=["SCI"])
    parser.add_argument("--rounds", type=int, default=3)
    parser.add_argument("--max-items", type=int, default=5)
    parser.add_argument("--output-dir", default=str(Path(__file__).resolve().parents[1] / "logs" / "stress"))
    args = parser.parse_args()
    output = asyncio.run(run_stress(keywords=args.keywords, rounds=args.rounds, max_items=args.max_items, output_dir=Path(args.output_dir)))
    print(output)


if __name__ == "__main__":
    main()
