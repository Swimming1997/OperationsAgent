"""Benchmark intelligence product list API latency (P95 target < 500ms @ 10k rows).

Usage:
  ..\\.venv\\Scripts\\python.exe scripts/seed_intelligence_perf.py --count 10000
  ..\\.venv\\Scripts\\python.exe scripts/bench_intelligence_list.py --samples 30
"""

from __future__ import annotations

import argparse
import statistics
import sys
import time
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT.parent) not in sys.path:
    sys.path.insert(0, str(ROOT.parent))

from intelligence_engine.db.session import SessionLocal
from intelligence_engine.main import create_app


def p95(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, int(len(ordered) * 0.95) - 1)
    return ordered[index]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--samples", type=int, default=20)
    args = parser.parse_args()

    app = create_app()
    db = SessionLocal()
    durations_ms: list[float] = []

    def override_get_db():
        yield db

    from intelligence_engine.db.session import get_db

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    client.headers.update({"X-Role": "admin", "X-User-Id": "admin-user"})

    for _ in range(args.samples):
        start = time.perf_counter()
        response = client.get(
            "/api/intelligence/contents/product",
            params={"page": 1, "page_size": 50, "sort_by": "latest_discovered_at", "sort_order": "desc"},
        )
        elapsed_ms = (time.perf_counter() - start) * 1000
        if response.status_code != 200:
            print(response.status_code, response.text)
            sys.exit(1)
        durations_ms.append(elapsed_ms)

    db.close()
    print(f"samples={len(durations_ms)}")
    print(f"p50_ms={statistics.median(durations_ms):.1f}")
    print(f"p95_ms={p95(durations_ms):.1f}")
    print(f"max_ms={max(durations_ms):.1f}")
    if p95(durations_ms) > 500:
        print("WARN: P95 exceeds 500ms target")
        sys.exit(2)


if __name__ == "__main__":
    main()
