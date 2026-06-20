"""Enqueue detail-fetch jobs for contents missing locally stored cover images."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT.parent) not in sys.path:
    sys.path.insert(0, str(ROOT.parent))

from sqlalchemy import text

from intelligence_engine.db.models import ContentIdentity, ContentSnapshot
from intelligence_engine.db.session import SessionLocal
from intelligence_engine.domain.enums import JobType, Platform
from intelligence_engine.storage.repositories.job_repository import JobRepository


def main() -> None:
    parser = argparse.ArgumentParser(description="Enqueue detail jobs for contents without stored cover files.")
    parser.add_argument("--limit", type=int, default=50, help="Max jobs to enqueue (default: 50)")
    parser.add_argument("--dry-run", action="store_true", help="Only print candidates")
    args = parser.parse_args()

    with SessionLocal() as db:
        rows = db.execute(
            text(
                """
            select ci.id, ci.platform, ci.platform_content_id, ci.canonical_url, cs.stored_cover_path
            from content_identity ci
            join content_snapshots cs on cs.id = ci.latest_snapshot_id
            where cs.stored_cover_path is null or trim(cs.stored_cover_path) = ''
            order by cs.fetched_at desc
            """
            )
        ).fetchall()
        candidates = rows[: max(args.limit, 0)]
        print(f"candidates={len(candidates)} (total missing stored cover={len(rows)})")
        if args.dry_run:
            for row in candidates:
                print(row[0], row[3])
            return

        repo = JobRepository(db)
        created = 0
        for content_id, platform, platform_content_id, canonical_url, _stored in candidates:
            repo.create_job(
                job_type=JobType.DETAIL_FETCH,
                payload={
                    "content_id": content_id,
                    "platform": platform or Platform.XHS.value,
                    "platform_content_id": platform_content_id,
                    "canonical_url": canonical_url,
                },
                priority=80,
            )
            created += 1
        db.commit()
        print(f"enqueued={created}")


if __name__ == "__main__":
    main()
