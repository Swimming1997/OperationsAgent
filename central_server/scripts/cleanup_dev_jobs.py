"""Development-only job queue cleanup. Does not delete content or product config."""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from intelligence_engine.db.session import SessionLocal
from intelligence_engine.services.job_queue_diagnostics import collect_job_queue_report
from intelligence_engine.storage.repositories.job_repository import JobRepository

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def parse_args():
    parser = argparse.ArgumentParser(description="Clean development/test backlog jobs.")
    parser.add_argument("--list", action="store_true", help="List matching jobs only.")
    parser.add_argument("--apply", action="store_true", help="Apply cleanup actions.")
    parser.add_argument("--agent-id", default=None, help="Filter by local agent id.")
    parser.add_argument("--task-run-id", default=None, help="Filter by task_run_id.")
    parser.add_argument("--created-before-hours", type=float, default=None, help="Only jobs older than N hours.")
    parser.add_argument("--only-legacy", action="store_true", help="Only pending jobs without task_run or legacy probe payloads.")
    parser.add_argument("--cancel-pending", action="store_true", help="Cancel pending jobs matching filters.")
    parser.add_argument("--fail-active", action="store_true", help="Fail claimed/running jobs matching filters.")
    parser.add_argument("--fail-stale-running", action="store_true", help="Fail all running jobs older than running timeout.")
    parser.add_argument("--running-timeout-seconds", type=int, default=1800)
    parser.add_argument("--reason", default="dev_cleanup")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.list and not args.apply:
        print("Specify --list or --apply", file=sys.stderr)
        return 2
    if args.apply and not (args.cancel_pending or args.fail_active or args.fail_stale_running):
        print("With --apply, choose at least one of --cancel-pending / --fail-active / --fail-stale-running", file=sys.stderr)
        return 2

    created_before = None
    if args.created_before_hours is not None:
        created_before = datetime.now(timezone.utc) - timedelta(hours=args.created_before_hours)

    with SessionLocal() as db:
        report = collect_job_queue_report(db, agent_id=args.agent_id)
        repo = JobRepository(db)
        dry_run = not args.apply
        summary: dict[str, int | list[str]] = {}

        if args.fail_stale_running or args.list:
            stale_ids = [item["job_id"] for item in report["stale_running_jobs"]]
            if args.list and args.fail_stale_running:
                print(f"[stale_running] {len(stale_ids)}")
                for job_id in stale_ids[:50]:
                    print(f"  {job_id}")
            if args.fail_stale_running:
                if args.apply:
                    count = repo.fail_stale_running_jobs(max_running_seconds=args.running_timeout_seconds)
                    summary["failed_stale_running"] = count
                else:
                    summary["failed_stale_running"] = len(stale_ids)

        if args.cancel_pending:
            cancelled = repo.cancel_pending_jobs(
                reason=args.reason,
                agent_id=args.agent_id,
                task_run_id=args.task_run_id,
                created_before=created_before,
                only_legacy=args.only_legacy,
                dry_run=dry_run,
            )
            summary["cancelled_pending"] = len(cancelled)
            if args.list:
                print(f"[cancel_pending] {len(cancelled)}")
                for job_id in cancelled[:50]:
                    print(f"  {job_id}")

        if args.fail_active:
            failed = repo.fail_active_jobs(reason=args.reason, agent_id=args.agent_id, dry_run=dry_run)
            summary["failed_active"] = len(failed)
            if args.list:
                print(f"[fail_active] {len(failed)}")
                for job_id in failed[:50]:
                    print(f"  {job_id}")

        if args.apply:
            db.commit()
            print("cleanup applied:", summary)
        else:
            print("dry-run summary:", summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
