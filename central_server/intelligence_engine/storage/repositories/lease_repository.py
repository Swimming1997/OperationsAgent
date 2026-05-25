from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from intelligence_engine.db.models import FetchLease, utcnow
from intelligence_engine.domain.enums import LeaseResourceType


class LeaseRepository:
    def __init__(self, db: Session):
        self.db = db

    def try_acquire(self, *, resource_type: LeaseResourceType, resource_key: str, owner_job_id: str, ttl_seconds: int) -> FetchLease | None:
        self.expire_stale_leases()
        lease = FetchLease(
            resource_type=resource_type.value,
            resource_key=resource_key,
            owner_job_id=owner_job_id,
            expires_at=utcnow() + timedelta(seconds=ttl_seconds),
        )
        try:
            with self.db.begin_nested():
                self.db.add(lease)
                self.db.flush()
        except IntegrityError:
            return None
        return lease

    def release(self, lease: FetchLease) -> None:
        lease.status = "released"
        lease.released_at = utcnow()

    def expire_stale_leases(self) -> int:
        self.db.flush()
        leases = list(
            self.db.scalars(
                select(FetchLease).where(
                    FetchLease.status == "active",
                    FetchLease.expires_at < utcnow(),
                )
            )
        )
        for lease in leases:
            lease.status = "expired"
        self.db.flush()
        return len(leases)
