import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from intelligence_engine.db.session import SessionLocal
from intelligence_engine.jobs.maintenance import JobMaintenanceService


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def parse_args():
    parser = argparse.ArgumentParser(description="Run central maintenance tasks.")
    parser.add_argument("--dry-run", action="store_true", help="Validate the maintenance entrypoint without mutating state.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        with SessionLocal() as db:
            result = JobMaintenanceService(db).run_once(dry_run=args.dry_run)
            if args.dry_run:
                db.rollback()
            else:
                db.commit()
            print(json.dumps(result.as_dict(), ensure_ascii=False))
            return 0
    except Exception as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

