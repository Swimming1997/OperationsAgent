"""Print current intelligence engine job queue diagnostics."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from intelligence_engine.db.session import SessionLocal
from intelligence_engine.services.job_queue_diagnostics import collect_job_queue_report

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def parse_args():
    parser = argparse.ArgumentParser(description="Diagnose pending/running job queue state.")
    parser.add_argument("--agent-id", default=None, help="Focus on one local agent queue.")
    parser.add_argument("--json", action="store_true", help="Output raw JSON.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    with SessionLocal() as db:
        report = collect_job_queue_report(db, agent_id=args.agent_id)
        db.commit()
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0

    print(f"generated_at: {report['generated_at']}")
    print("\n[status_counts]")
    for key, value in sorted(report["status_counts"].items()):
        print(f"  {key}: {value}")

    print("\n[job_type_status_counts]")
    for job_type, counter in sorted(report["job_type_status_counts"].items()):
        print(f"  {job_type}: {counter}")

    print(f"\nlegacy_pending_estimate: {report['legacy_pending_estimate']}")
    print(f"stale_running_jobs: {len(report['stale_running_jobs'])}")
    for item in report["stale_running_jobs"][:10]:
        print(f"  - {item['job_id']} {item['job_type']} agent={item['claimed_by_agent_id']} stale={item.get('stale_for_seconds')}s")
    print(f"stale_claimed_jobs: {len(report['stale_claimed_jobs'])}")

    if report.get("agent"):
        agent = report["agent"]
        print(f"\n[agent {agent['agent_id']}] {agent.get('device_name')} status={agent.get('status')}")
        print(f"pending_queue_length: {agent['pending_queue_length']}")
        print("next_pending_jobs:")
        for item in agent["next_pending_jobs"]:
            print(
                f"  - {item['job_id']} priority={item['priority']} type={item['job_type']} "
                f"task_run={item['task_run_id']} legacy={item['legacy_candidate']}"
            )
        print("active_jobs:")
        for item in agent["active_jobs"]:
            print(f"  - {item['job_id']} {item['status']} type={item['job_type']} started={item['started_at']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
