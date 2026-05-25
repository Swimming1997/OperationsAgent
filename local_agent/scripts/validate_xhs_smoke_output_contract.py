#!/usr/bin/env python3
"""Validate local XHS smoke JSON output against central ingestion contracts."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from local_agent_runtime.smoke.contract import validate_smoke_json_file, validate_smoke_report

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate XHS smoke output contract mapping.")
    parser.add_argument("json_path", help="Path to smoke capability JSON output.")
    args = parser.parse_args()
    path = Path(args.json_path)
    if not path.exists():
        print(json.dumps({"valid": False, "errors": [f"file not found: {path}"]}, ensure_ascii=False))
        return 1
    result = validate_smoke_json_file(path)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("valid") else 1


if __name__ == "__main__":
    raise SystemExit(main())
