from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from intelligence_engine.db.models import AccountSession, LocalAgent, utcnow
from intelligence_engine.db.session import get_db
from intelligence_engine.domain.enums import JobType
from intelligence_engine.main import create_app
from intelligence_engine.services.employee_agent_pool import AgentEmployeeConflictError, register_agents_to_employee
from intelligence_engine.storage.repositories.job_repository import JobRepository
from intelligence_engine.storage.repositories.product_repository import ProductRepository


def _client(db_session):
    app = create_app()

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)


def test_register_agents_conflict_and_force_rebind(db_session):
    repo = ProductRepository(db_session)
    employee_a = repo.create_employee(user_id=None, display_name="A", email=None, status="active")
    employee_b = repo.create_employee(user_id=None, display_name="B", email=None, status="active")
    agent = LocalAgent(
        employee_id=employee_a.id,
        device_name="WIN-A",
        machine_fingerprint="fp-a",
        status="online",
        capabilities_json={"job_types": ["feed_collect"]},
        last_heartbeat_at=utcnow(),
    )
    db_session.add(agent)
    db_session.commit()

    with pytest.raises(AgentEmployeeConflictError):
        register_agents_to_employee(db_session, agent_ids=[agent.id], employee_id=employee_b.id, force=False)

    register_agents_to_employee(db_session, agent_ids=[agent.id], employee_id=employee_b.id, force=True)
    db_session.commit()
    assert agent.employee_id == employee_b.id


def test_claim_jobs_uses_employee_pool_and_ready_session(db_session):
    repo = ProductRepository(db_session)
    owner = repo.create_employee(user_id=None, display_name="owner", email=None, status="active")
    agent = LocalAgent(
        employee_id=owner.id,
        device_name="WIN-POOL",
        machine_fingerprint="fp-pool",
        status="online",
        capabilities_json={"job_types": ["feed_collect"]},
        last_heartbeat_at=utcnow(),
    )
    db_session.add(agent)
    db_session.flush()
    account = repo.create_account(
        employee_id=owner.id,
        platform="xhs",
        display_name="pool-acct",
        external_account_id=None,
        business_account_type=None,
        business_account_type_id=None,
        metadata={},
    )
    db_session.add(
        AccountSession(
            account_id=account.id,
            local_agent_id=agent.id,
            platform="xhs",
            session_type="managed_chrome",
            status="ready",
            session_meta_json={},
            last_validated_at=utcnow(),
        )
    )
    job = JobRepository(db_session).create_job(
        job_type=JobType.FEED_COLLECT,
        account_id=account.id,
        local_agent_id=None,
        payload={"account_id": account.id},
    )
    db_session.commit()

    claimed = JobRepository(db_session).claim_jobs_for_agent(
        agent_id=agent.id,
        supported_job_types=[JobType.FEED_COLLECT],
        max_jobs=1,
        ttl_seconds=60,
    )
    assert len(claimed) == 1
    assert claimed[0].id == job.id
    assert claimed[0].local_agent_id == agent.id
