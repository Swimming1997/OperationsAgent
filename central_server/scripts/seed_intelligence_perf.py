"""Seed intelligence pool data for list query performance checks.

Usage (from central_server, default SQLite — no env needed):
  ..\\.venv\\Scripts\\python.exe scripts/seed_intelligence_perf.py --count 500

Optional PostgreSQL (plan P95 @ 10k, requires docker compose):
  $env:INTEL_ENGINE_DATABASE_URL = "postgresql+psycopg://intel:intel@localhost:55432/intelligence_engine"
  ..\\.venv\\Scripts\\python.exe scripts/seed_intelligence_perf.py --count 10000
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import func, select

from intelligence_engine.db.models import CandidateDecision, ContentDiscoveryEvent, ContentIdentity, ContentSnapshot, ContentWorkflowState, utcnow
from intelligence_engine.db.session import SessionLocal
from intelligence_engine.domain.enums import CandidateBucket, ContentType, Platform, SourceSurface
from intelligence_engine.services.rule_profile import RuleProfileService
from intelligence_engine.storage.repositories.product_repository import ProductRepository


def _ensure_seed_prerequisites(session) -> None:
    """Use Alembic schema only; avoid init_db/create_all on PostgreSQL perf runs."""
    ProductRepository(session).ensure_default_roles()
    RuleProfileService(session).ensure_defaults(created_by_user_id=None)
    session.commit()


def seed(count: int, *, batch_size: int = 500) -> None:
    session = SessionLocal()
    try:
        _ensure_seed_prerequisites(session)
        now = utcnow()
        pending = 0
        for index in range(count):
            content_id = f"perf-content-{index:06d}"
            if session.get(ContentIdentity, content_id):
                continue
            snapshot_id = f"perf-snapshot-{index:06d}"
            identity = ContentIdentity(
                id=content_id,
                platform=Platform.XHS.value,
                platform_content_id=f"perf-note-{index}",
                canonical_url=f"https://www.xiaohongshu.com/explore/perf-{index}",
                content_type=ContentType.IMAGE_TEXT.value,
                first_seen_at=now,
                last_seen_at=now,
                latest_snapshot_id=None,
                metadata_json={"visible_like_count": 80 + (index % 500), "manual_tags": ["perf"]},
            )
            session.add(identity)
            session.add(
                ContentSnapshot(
                    id=snapshot_id,
                    content_id=content_id,
                    title=f"性能种子内容 {index}",
                    body_text="论文 SCI 投稿经验",
                    author_name="作者",
                    like_count=80 + (index % 500),
                    comment_count=index % 40,
                    collect_count=index % 20,
                    fetched_at=now,
                )
            )
            session.flush()
            identity.latest_snapshot_id = snapshot_id
            session.add(
                ContentDiscoveryEvent(
                    id=f"perf-event-{index:06d}",
                    content_id=content_id,
                    platform=Platform.XHS.value,
                    source_surface=SourceSurface.XHS_HOME_FEED.value,
                    discovered_at=now,
                    discovery_meta_json={"search_keyword": "SCI"},
                )
            )
            session.add(
                CandidateDecision(
                    id=f"perf-decision-{index:06d}",
                    content_id=content_id,
                    snapshot_id=snapshot_id,
                    business_keyword_hits_json=["论文"],
                    lead_keyword_hits_json=[],
                    comment_keyword_hits_json=[],
                    like_threshold_hit=True,
                    comment_threshold_hit=False,
                    candidate_bucket=CandidateBucket.CONTENT_CANDIDATE.value,
                    decision_reason_json={"seed": True},
                    evaluated_at=now,
                )
            )
            session.add(
                ContentWorkflowState(
                    id=f"perf-workflow-{index:06d}",
                    content_id=content_id,
                    workflow_status="pending_review",
                )
            )
            pending += 1
            if pending >= batch_size:
                session.commit()
                pending = 0
        session.commit()
        total = session.scalar(select(func.count()).select_from(ContentIdentity)) or 0
        print(f"seed complete: target={count}, content_identities={total}, database={os.getenv('INTEL_ENGINE_DATABASE_URL', 'default')}")
    finally:
        session.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=1000)
    parser.add_argument("--batch-size", type=int, default=500)
    args = parser.parse_args()
    seed(args.count, batch_size=args.batch_size)


if __name__ == "__main__":
    main()
