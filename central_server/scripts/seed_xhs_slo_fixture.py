"""Seed terminal XHS jobs for SLO report acceptance when no Local Agent history exists.

Usage (PostgreSQL recommended, after migrations):
  $env:INTEL_ENGINE_DATABASE_URL = "postgresql+psycopg://intel:intel@localhost:55432/intelligence_engine"
  ..\\.venv\\Scripts\\python.exe scripts/seed_xhs_slo_fixture.py --per-type 55 --success-rate 0.92
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from intelligence_engine.db.models import Job, utcnow
from intelligence_engine.db.session import SessionLocal
from intelligence_engine.domain.enums import JobStatus, JobType


TRACKED = [
    JobType.FEED_COLLECT.value,
    JobType.SEARCH_COLLECT.value,
    JobType.DETAIL_FETCH.value,
    JobType.COMMENT_FETCH.value,
]


def seed(*, per_type: int, success_rate: float) -> None:
    now = utcnow()
    session = SessionLocal()
    try:
        success_count = max(0, int(per_type * success_rate))
        fail_count = per_type - success_count
        created = 0
        for job_type in TRACKED:
            for index in range(success_count):
                session.add(
                    Job(
                        id=str(uuid4()),
                        job_type=job_type,
                        status=JobStatus.SUCCESS.value if index % 2 == 0 else JobStatus.PARTIAL_SUCCESS.value,
                        payload_json={"fixture": True, "index": index},
                        created_at=now,
                        updated_at=now,
                    )
                )
                created += 1
            for index in range(fail_count):
                session.add(
                    Job(
                        id=str(uuid4()),
                        job_type=job_type,
                        status=JobStatus.FAILED.value,
                        payload_json={"fixture": True, "failed": index},
                        last_error_code="FIXTURE_FAILED",
                        created_at=now,
                        updated_at=now,
                    )
                )
                created += 1
        session.commit()
        print(f"seed_xhs_slo_fixture: job_types={len(TRACKED)}, per_type={per_type}, success_rate={success_rate}, rows={created}")
    finally:
        session.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--per-type", type=int, default=55, help="terminal jobs per tracked job type (>=50 for SLO)")
    parser.add_argument("--success-rate", type=float, default=0.92, help="fraction of jobs that succeed")
    args = parser.parse_args()
    seed(per_type=args.per_type, success_rate=args.success_rate)


if __name__ == "__main__":
    main()
