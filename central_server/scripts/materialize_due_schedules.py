import argparse
import json
import sys
from pathlib import Path

from sqlalchemy import select

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from intelligence_engine.db.models import TaskSchedule, utcnow
from intelligence_engine.db.session import SessionLocal
from intelligence_engine.services.task_materialization import TaskMaterializationService


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def parse_args():
    parser = argparse.ArgumentParser(description="Materialize due task schedules into jobs.")
    parser.add_argument("--dry-run", action="store_true", help="Only count due schedules; do not create jobs.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        with SessionLocal() as db:
            now = utcnow()
            if args.dry_run:
                due_ids = list(
                    db.scalars(
                        select(TaskSchedule.id)
                        .where(TaskSchedule.enabled.is_(True))
                        .where(TaskSchedule.next_run_at.is_not(None))
                        .where(TaskSchedule.next_run_at <= now)
                    )
                )
                print(json.dumps({"dry_run": True, "due_schedule_count": len(due_ids), "due_schedule_ids": due_ids}, ensure_ascii=False))
                return 0
            results = TaskMaterializationService(db).materialize_due_schedules(now=now)
            db.commit()
            print(
                json.dumps(
                    {
                        "dry_run": False,
                        "schedule_count": len(results),
                        "job_count": sum(len(item["job_ids"]) for item in results),
                        "materialized": results,
                    },
                    ensure_ascii=False,
                )
            )
            return 0
    except Exception as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
