"""Job queue facade.

The current implementation lives in storage.repositories.job_repository.
Keeping this facade gives new code a domain-level import path while the
repository is migrated incrementally.
"""

from intelligence_engine.storage.repositories.job_repository import JobRepository

__all__ = ["JobRepository"]

