from __future__ import annotations

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from intelligence_engine.db.models import LocalAgent, utcnow
from intelligence_engine.db.session import get_db
from intelligence_engine.main import create_app
from intelligence_engine.services.account_login_service import AccountLoginService
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
            "username": "reroute_admin",
            "display_name": "Reroute Admin",
            "email": "reroute@demo.local",
            "password": "ReroutePass123!",
        },
    )
    assert bootstrap.status_code == 200, bootstrap.text
    return {"Authorization": f"Bearer {bootstrap.json()['access_token']}"}


def test_waiting_session_claimed_by_live_agent_of_same_employee(client: TestClient, db_session):
    repo = ProductRepository(db_session)
    employee = repo.create_employee(user_id=None, display_name="范贤亮", email=None, status="active")
    stale = LocalAgent(
        employee_id=employee.id,
        device_name="WIN-1",
        machine_fingerprint="stale-fp",
        status="offline",
        capabilities_json={},
    )
    live = LocalAgent(
        employee_id=employee.id,
        device_name="WIN-1",
        machine_fingerprint="live-fp",
        status="online",
        capabilities_json={"supports_account_login": True},
        last_heartbeat_at=utcnow(),
    )
    db_session.add_all([stale, live])
    db_session.flush()
    account = repo.create_account(
        employee_id=employee.id,
        platform="xhs",
        display_name="账号A",
        external_account_id=None,
        business_account_type=None,
        business_account_type_id=None,
        default_agent_id=stale.id,
        metadata={},
    )
    service = AccountLoginService(db_session)
    session = service.start_login(account)
    assert session.status == "waiting_agent"
    assert session.agent_id == stale.id
    db_session.commit()

    claim = client.post(f"/api/agents/{live.id}/login-sessions/claim", params={"max_sessions": 1})
    assert claim.status_code == 200, claim.text
    sessions = claim.json()["sessions"]
    assert len(sessions) == 1
    assert sessions[0]["id"] == session.id


def test_patch_default_agent_reroutes_waiting_session(client: TestClient, db_session):
    headers = _auth_headers(client)
    repo = ProductRepository(db_session)
    employee = repo.create_employee(user_id=None, display_name="范贤亮", email=None, status="active")
    stale = LocalAgent(
        employee_id=employee.id,
        device_name="WIN-1",
        machine_fingerprint="stale-fp-2",
        status="offline",
        capabilities_json={},
    )
    live = LocalAgent(
        employee_id=employee.id,
        device_name="WIN-1",
        machine_fingerprint="live-fp-2",
        status="online",
        capabilities_json={"supports_account_login": True},
        last_heartbeat_at=utcnow(),
    )
    db_session.add_all([stale, live])
    db_session.flush()
    account = repo.create_account(
        employee_id=employee.id,
        platform="xhs",
        display_name="账号B",
        external_account_id=None,
        business_account_type=None,
        business_account_type_id=None,
        default_agent_id=stale.id,
        metadata={},
    )
    session = AccountLoginService(db_session).start_login(account)
    db_session.commit()

    patch = client.patch(
        f"/api/product/accounts/{account.id}",
        headers=headers,
        json={"default_agent_id": live.id},
    )
    assert patch.status_code == 200, patch.text

    db_session.expire_all()
    refreshed = AccountLoginService(db_session).get_active_session(account.id)
    assert refreshed is not None
    assert refreshed.agent_id == live.id
