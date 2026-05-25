from __future__ import annotations

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from intelligence_engine.db.models import LocalAgent
from intelligence_engine.db.session import get_db
from intelligence_engine.main import create_app
from intelligence_engine.services.account_login_service import AccountLoginService, is_agent_online
from intelligence_engine.storage.repositories.product_repository import ProductRepository


@pytest.fixture()
def client(db_session):
    app = create_app()

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)


def _auth_headers(client: TestClient) -> dict[str, str]:
    bootstrap = client.post(
        "/api/auth/bootstrap-admin",
        json={
            "username": "login_admin",
            "display_name": "Login Admin",
            "email": "login@demo.local",
            "password": "LoginPass123!",
        },
    )
    assert bootstrap.status_code == 200, bootstrap.text
    return {"Authorization": f"Bearer {bootstrap.json()['access_token']}"}


def test_start_login_waiting_agent_without_online_agent(client: TestClient):
    headers = _auth_headers(client)
    create = client.post(
        "/api/product/accounts",
        headers=headers,
        json={"platform": "xhs", "display_name": "XHS-A", "employee_id": None, "default_agent_id": None},
    )
    assert create.status_code == 200
    account_id = create.json()["id"]
    assert create.json()["auth_status"] == "not_logged_in"
    assert create.json()["profile_key"] == f"accounts/{account_id}"

    start = client.post(f"/api/product/accounts/{account_id}/login-sessions", headers=headers)
    assert start.status_code == 200
    body = start.json()
    assert body["session"]["status"] == "waiting_agent"
    assert "Agent" in body["message"]

    active = client.get(f"/api/product/accounts/{account_id}/login-sessions/active", headers=headers)
    assert active.status_code == 200
    assert active.json()["status"] == "waiting_agent"


def test_claim_login_session_for_agent(client: TestClient, db_session):
    repo = ProductRepository(db_session)
    repo.ensure_default_roles()
    user = repo.create_user(
        username="agentowner",
        display_name="Owner",
        email=None,
        password_hash="x",
        role_names=["operator"],
        metadata={},
    )
    employee = repo.create_employee(user_id=user.id, display_name="Owner", email=None, status="active")
    from intelligence_engine.db.models import utcnow

    agent = LocalAgent(
        employee_id=employee.id,
        device_name="WIN-1",
        machine_fingerprint="fp1",
        status="online",
        capabilities_json={"supports_account_login": True},
        last_heartbeat_at=utcnow(),
    )
    db_session.add(agent)
    db_session.flush()
    account = repo.create_account(
        employee_id=employee.id,
        platform="xhs",
        display_name="XHS-B",
        external_account_id=None,
        business_account_type=None,
        business_account_type_id=None,
        default_agent_id=agent.id,
        metadata={},
    )
    session = AccountLoginService(db_session).start_login(account)
    db_session.commit()
    agent_id = agent.id
    session_id = session.id
    account_id = account.id

    claim = client.post(f"/api/agents/{agent_id}/login-sessions/claim", params={"max_sessions": 1})
    assert claim.status_code == 200
    sessions = claim.json()["sessions"]
    assert len(sessions) == 1
    assert sessions[0]["id"] == session_id
    assert sessions[0]["platform_account_id"] == account_id
    assert sessions[0]["cdp_port"]


def test_reset_login_clears_false_positive_active(client: TestClient, db_session):
    headers = _auth_headers(client)
    repo = ProductRepository(db_session)
    account = repo.create_account(
        employee_id=None,
        platform="xhs",
        display_name="False Positive",
        external_account_id=None,
        business_account_type=None,
        business_account_type_id=None,
        default_agent_id=None,
        metadata={},
    )
    account.auth_status = "active"
    db_session.commit()

    reset = client.post(f"/api/product/accounts/{account.id}/login-sessions/reset", headers=headers)
    assert reset.status_code == 200, reset.text
    assert reset.json()["auth_status"] == "not_logged_in"

    get_account = client.get(f"/api/product/accounts/{account.id}", headers=headers)
    assert get_account.status_code == 200
    assert get_account.json()["auth_status"] == "not_logged_in"


def test_relogin_with_force_resets_then_starts(client: TestClient):
    headers = _auth_headers(client)
    create = client.post(
        "/api/product/accounts",
        headers=headers,
        json={"platform": "xhs", "display_name": "Relogin-A", "employee_id": None, "default_agent_id": None},
    )
    account_id = create.json()["id"]
    service_reset = client.post(f"/api/product/accounts/{account_id}/login-sessions/reset", headers=headers)
    assert service_reset.status_code == 200

    start = client.post(
        f"/api/product/accounts/{account_id}/login-sessions",
        headers=headers,
        json={"force": True},
    )
    assert start.status_code == 200
    assert start.json()["session"]["status"] in {"waiting_agent", "created", "launching_browser"}


def test_is_agent_online_requires_recent_heartbeat():
    from intelligence_engine.db.models import utcnow

    agent = LocalAgent(device_name="x", status="online", capabilities_json={}, last_heartbeat_at=utcnow())
    assert is_agent_online(agent) is True
    agent.last_heartbeat_at = utcnow() - timedelta(minutes=5)
    assert is_agent_online(agent) is False
