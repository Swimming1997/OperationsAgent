#!/usr/bin/env python3
"""Audit intelligence center data quality directly from the central database."""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from intelligence_engine.audit.intelligence_center_audit import run_intelligence_center_audit, write_audit_outputs
from intelligence_engine.db.init_db import init_db
from intelligence_engine.db.session import SessionLocal

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit intelligence center pool quality and operational readiness.")
    parser.add_argument("--window-hours", type=int, default=24, help="Recent enrichment policy window in hours.")
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Override output directory. Default: central_server/logs/audit/intelligence_center/YYYYMMDD",
    )
    return parser.parse_args()


def default_output_dir() -> Path:
    day = datetime.now().strftime("%Y%m%d")
    return Path(__file__).resolve().parents[1] / "logs" / "audit" / "intelligence_center" / day


def main() -> int:
    args = parse_args()
    central_root = Path(__file__).resolve().parents[1]
    import os

    os.chdir(central_root)
    init_db()
    output_dir = Path(args.output_dir) if args.output_dir else default_output_dir()
    with SessionLocal() as db:
        report = run_intelligence_center_audit(db, window_hours=args.window_hours)
        db.commit()
    paths = write_audit_outputs(report, output_dir)
    print(f"run_id: {report['run_id']}")
    print(f"markdown: {paths['markdown']}")
    print(f"json: {paths['json']}")
    print(f"ndjson: {paths['ndjson']}")
    if report["findings"]:
        print("\nfindings:")
        for finding in report["findings"]:
            print(f"  - [{finding['severity']}] {finding['code']}: {finding['message']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
