"""Summarize XHS-related job SLO metrics from the intelligence_engine database.

Usage:
  # default: sqlite:///./data/intelligence_engine.db (no env)
  # optional: set INTEL_ENGINE_DATABASE_URL=postgresql+psycopg://...
  ..\\.venv\\Scripts\\python.exe scripts/xhs_slo_report.py --window-hours 24
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import func, select

from intelligence_engine.db.models import Job, utcnow
from intelligence_engine.db.session import SessionLocal
from intelligence_engine.domain.enums import JobStatus, JobType


TERMINAL = {
    JobStatus.SUCCESS.value,
    JobStatus.PARTIAL_SUCCESS.value,
    JobStatus.FAILED.value,
    JobStatus.CANCELLED.value,
}
SUCCESS = {JobStatus.SUCCESS.value, JobStatus.PARTIAL_SUCCESS.value}
TRACKED_JOB_TYPES = [
    JobType.FEED_COLLECT.value,
    JobType.SEARCH_COLLECT.value,
    JobType.DETAIL_FETCH.value,
    JobType.COMMENT_FETCH.value,
]
SLO_SUCCESS_RATE = 0.9


def _rate(success: int, total: int) -> float | None:
    if total == 0:
        return None
    return success / total


def build_report(*, window_hours: int) -> dict:
    since = utcnow() - timedelta(hours=window_hours)
    session = SessionLocal()
    try:
        rows = list(
            session.execute(
                select(Job.job_type, Job.status, func.count(Job.id))
                .where(Job.created_at >= since, Job.job_type.in_(TRACKED_JOB_TYPES))
                .group_by(Job.job_type, Job.status)
            )
        )
        stale_running = session.scalar(
            select(func.count(Job.id)).where(
                Job.status == JobStatus.RUNNING.value,
                Job.updated_at < utcnow() - timedelta(minutes=30),
            )
        ) or 0
    finally:
        session.close()

    by_type: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for job_type, status, count in rows:
        by_type[job_type][status] = int(count)

    job_types = []
    for job_type in TRACKED_JOB_TYPES:
        counts = by_type.get(job_type, {})
        terminal_total = sum(counts.get(status, 0) for status in TERMINAL)
        success_total = sum(counts.get(status, 0) for status in SUCCESS)
        rate = _rate(success_total, terminal_total)
        job_types.append(
            {
                "job_type": job_type,
                "counts": dict(counts),
                "terminal_total": terminal_total,
                "success_total": success_total,
                "success_rate": rate,
                "slo_target": SLO_SUCCESS_RATE,
                "slo_met": rate is not None and rate >= SLO_SUCCESS_RATE,
            }
        )

    return {
        "window_hours": window_hours,
        "generated_at": utcnow().isoformat(),
        "job_types": job_types,
        "stale_running_over_30m": int(stale_running),
        "notes": [
            "任务成功率按 SUCCESS + PARTIAL_SUCCESS / 终态任务统计。",
            "需结合 Local Agent 实跑与运行中心失败分类进一步验收。",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--window-hours", type=int, default=24)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    report = build_report(window_hours=args.window_hours)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return
    print(f"XHS SLO report (last {report['window_hours']}h)")
    for item in report["job_types"]:
        rate = item["success_rate"]
        rate_text = f"{rate * 100:.1f}%" if rate is not None else "n/a"
        status = "PASS" if item["slo_met"] else "FAIL"
        print(f"- {item['job_type']}: success_rate={rate_text} terminal={item['terminal_total']} [{status}]")
    print(f"- stale_running_over_30m: {report['stale_running_over_30m']}")
    if not all(item["slo_met"] for item in report["job_types"] if item["terminal_total"] > 0):
        sys.exit(2)


if __name__ == "__main__":
    main()
