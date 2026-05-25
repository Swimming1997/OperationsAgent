from __future__ import annotations

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from intelligence_engine.db.models import LocalAgent, utcnow
from intelligence_engine.db.session import get_db
from intelligence_engine.main import create_app
from intelligence_engine.security.passwords import hash_password
from intelligence_engine.services.agent_presence import effective_agent_status, is_agent_live
from intelligence_engine.storage.repositories.account_repository import AccountRepository
from intelligence_engine.storage.repositories.product_repository import ProductRepository


@pytest.fixture()
def client(db_session):
    app = create_app()

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)


def _admin_headers(client: TestClient) -> dict[str, str]:
    bootstrap = client.post(
        "/api/auth/bootstrap-admin",
        json={
            "username": "agent_admin",
            "display_name": "Agent Admin",
            "email": "agent@demo.local",
            "password": "AgentPass123!",
        },
    )
    assert bootstrap.status_code == 200, bootstrap.text
    return {"Authorization": f"Bearer {bootstrap.json()['access_token']}"}


def test_effective_status_offline_without_heartbeat(db_session):
    agent = LocalAgent(device_name="offline-agent", status="online", capabilities_json={})
    db_session.add(agent)
    db_session.flush()
    assert effective_agent_status(agent) == "offline"
    assert not is_agent_live(agent)


def test_stale_heartbeat_marks_offline(db_session):
    agent = LocalAgent(
        device_name="stale",
        status="online",
        capabilities_json={},
        last_heartbeat_at=utcnow() - timedelta(minutes=5),
    )
    db_session.add(agent)
    db_session.flush()
    assert effective_agent_status(agent) == "offline"


def test_heartbeat_updates_version_and_presence(client: TestClient):
    headers = _admin_headers(client)
    register = client.post(
        "/api/agents/register",
        json={
            "device_name": "HB-1",
            "machine_fingerprint": "hb-fp-1",
            "agent_version": "0.2.0",
            "capabilities": {"supports_account_login": True},
        },
    )
    assert register.status_code == 200
    agent_id = register.json()["agent_id"]

    listed = client.get("/api/local-agents", headers=headers)
    assert listed.status_code == 200
    row = next(item for item in listed.json() if item["id"] == agent_id)
    assert row["agent_version"] == "0.2.0"
    assert row["last_heartbeat_at"] is not None
    assert row["status"] == "online"

    heartbeat = client.post(
        f"/api/agents/{agent_id}/heartbeat",
        json={"status": "online", "agent_version": "0.2.1", "capabilities": {"supports_account_login": True}},
    )
    assert heartbeat.status_code == 200

    listed2 = client.get("/api/local-agents", headers=headers)
    row2 = next(item for item in listed2.json() if item["id"] == agent_id)
    assert row2["agent_version"] == "0.2.1"
    assert row2["status"] == "online"


def test_operator_lists_agent_bound_to_account(client: TestClient, db_session):
    repo = ProductRepository(db_session)
    repo.ensure_default_roles()
    user = repo.create_user(
        username="op_agent",
        display_name="Operator",
        email=None,
        password_hash=hash_password("OpPass123!"),
        role_names=["operator"],
        metadata={},
    )
    employee = repo.create_employee(user_id=user.id, display_name="Operator", email=None, status="active")
    agent = AccountRepository(db_session).register_agent(
        employee_id=None,
        device_name="WIN-1",
        machine_fingerprint="win-1-fp",
        agent_version="0.1.0",
        capabilities={"supports_account_login": True},
    )
    repo.create_account(
        employee_id=employee.id,
        platform="xhs",
        display_name="A1",
        external_account_id=None,
        business_account_type=None,
        business_account_type_id=None,
        default_agent_id=agent.id,
        metadata={},
    )
    db_session.commit()

    login = client.post("/api/auth/login", json={"username": "op_agent", "password": "OpPass123!"})
    assert login.status_code == 200, login.text
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    agents = client.get("/api/local-agents", headers=headers)
    assert agents.status_code == 200, agents.text
    ids = {item["id"] for item in agents.json()}
    assert agent.id in ids


def test_admin_can_bind_agent_to_employee(client: TestClient, db_session):
    headers = _admin_headers(client)
    register = client.post(
        "/api/agents/register",
        json={
            "device_name": "BIND-1",
            "machine_fingerprint": "bind-fp-1",
            "agent_version": "0.1.0",
            "capabilities": {"supports_account_login": True},
        },
    )
    assert register.status_code == 200
    agent_id = register.json()["agent_id"]

    repo = ProductRepository(db_session)
    employee = repo.create_employee(user_id=None, display_name="Bind Target", email=None, status="active")
    db_session.commit()

    patch = client.patch(
        f"/api/local-agents/{agent_id}",
        json={"employee_id": employee.id},
        headers=headers,
    )
    assert patch.status_code == 200, patch.text
    body = patch.json()
    assert body["employee_id"] == employee.id
    assert body["employee_display_name"] == "Bind Target"

    listed = client.get("/api/local-agents", headers=headers)
    row = next(item for item in listed.json() if item["id"] == agent_id)
    assert row["employee_id"] == employee.id


def test_operator_cannot_bind_agent_to_employee(client: TestClient, db_session):
    repo = ProductRepository(db_session)
    repo.ensure_default_roles()
    user = repo.create_user(
        username="op_bind",
        display_name="Operator",
        email=None,
        password_hash=hash_password("OpPass123!"),
        role_names=["operator"],
        metadata={},
    )
    employee = repo.create_employee(user_id=user.id, display_name="Operator", email=None, status="active")
    agent = AccountRepository(db_session).register_agent(
        employee_id=None,
        device_name="WIN-BIND",
        machine_fingerprint="win-bind-fp",
        agent_version="0.1.0",
        capabilities={},
    )
    db_session.commit()

    login = client.post("/api/auth/login", json={"username": "op_bind", "password": "OpPass123!"})
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    patch = client.patch(
        f"/api/local-agents/{agent.id}",
        json={"employee_id": employee.id},
        headers=headers,
    )
    assert patch.status_code == 403
