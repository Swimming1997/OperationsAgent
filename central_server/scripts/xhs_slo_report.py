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
if str(ROOT.parent) not in sys.path:
    sys.path.insert(0, str(ROOT.parent))

from sqlalchemy import func, select
from sqlalchemy.orm import Session

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


def _is_fixture_job(job: Job) -> bool:
    payload = job.payload_json or {}
    return bool(payload.get("fixture") or payload.get("slo_fixture"))


def build_report(*, window_hours: int, session: Session | None = None) -> dict:
    since = utcnow() - timedelta(hours=window_hours)
    owns_session = session is None
    if session is None:
        session = SessionLocal()
    try:
        jobs = list(
            session.scalars(
                select(Job).where(Job.created_at >= since, Job.job_type.in_(TRACKED_JOB_TYPES))
            )
        )
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
        if owns_session:
            session.close()

    by_type: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for job_type, status, count in rows:
        by_type[job_type][status] = int(count)
    real_terminal_by_type: dict[str, int] = defaultdict(int)
    fixture_terminal_by_type: dict[str, int] = defaultdict(int)
    error_code_by_type: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for job in jobs:
        if job.status not in TERMINAL:
            continue
        if _is_fixture_job(job):
            fixture_terminal_by_type[job.job_type] += 1
        else:
            real_terminal_by_type[job.job_type] += 1
        if job.last_error_code:
            error_code_by_type[job.job_type][job.last_error_code] += 1

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
                "real_terminal_total": real_terminal_by_type.get(job_type, 0),
                "fixture_terminal_total": fixture_terminal_by_type.get(job_type, 0),
                "error_code_counts": dict(error_code_by_type.get(job_type, {})),
            }
        )

    return {
        "window_hours": window_hours,
        "generated_at": utcnow().isoformat(),
        "job_types": job_types,
        "stale_running_over_30m": int(stale_running),
        "notes": [
            "任务成功率按 SUCCESS + PARTIAL_SUCCESS / 终态任务统计。",
            "real_terminal_total 不包含 seed_xhs_slo_fixture.py 写入的夹具任务。",
            "P1 真实验收建议使用 --require-real-data --min-terminal-per-type 50。",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--window-hours", type=int, default=24)
    parser.add_argument("--require-real-data", action="store_true")
    parser.add_argument("--min-terminal-per-type", type=int, default=0)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    report = build_report(window_hours=args.window_hours)
    real_data_ok = all(item["real_terminal_total"] >= args.min_terminal_per_type for item in report["job_types"])
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        if args.require_real_data and not real_data_ok:
            sys.exit(3)
        return
    print(f"XHS SLO report (last {report['window_hours']}h)")
    for item in report["job_types"]:
        rate = item["success_rate"]
        rate_text = f"{rate * 100:.1f}%" if rate is not None else "n/a"
        status = "PASS" if item["slo_met"] else "FAIL"
        print(
            f"- {item['job_type']}: success_rate={rate_text} terminal={item['terminal_total']} "
            f"real={item['real_terminal_total']} fixture={item['fixture_terminal_total']} [{status}]"
        )
        if item["error_code_counts"]:
            print(f"  error_codes={item['error_code_counts']}")
    print(f"- stale_running_over_30m: {report['stale_running_over_30m']}")
    if args.require_real_data and not real_data_ok:
        print(f"真实终态样本不足：要求每类 >= {args.min_terminal_per_type}，请先用 Local Agent 实跑。")
        sys.exit(3)
    if not all(item["slo_met"] for item in report["job_types"] if item["terminal_total"] > 0):
        sys.exit(2)


if __name__ == "__main__":
    main()
