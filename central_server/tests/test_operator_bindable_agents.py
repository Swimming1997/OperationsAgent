from __future__ import annotations

from fastapi.testclient import TestClient

from intelligence_engine.db.session import get_db
from intelligence_engine.main import create_app
from intelligence_engine.storage.repositories.account_repository import AccountRepository
from intelligence_engine.storage.repositories.product_repository import ProductRepository


def _client(db_session, *, role: str, user_id: str) -> TestClient:
    app = create_app()

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    client.headers.update({"X-Role": role, "X-User-Id": user_id})
    return client


def test_operator_list_agents_includes_unbound_for_registration(db_session):
    product = ProductRepository(db_session)
    employee = product.create_employee(user_id="op-user", display_name="运营甲", email=None, status="active")
    bound = AccountRepository(db_session).register_agent(
        employee_id=employee.id,
        device_name="bound-pc",
        machine_fingerprint="fp-bound",
        agent_version="0.1.0",
        capabilities={"job_types": ["feed_collect"]},
    )
    unbound = AccountRepository(db_session).register_agent(
        employee_id=None,
        device_name="fresh-pc",
        machine_fingerprint="fp-fresh",
        agent_version="0.1.0",
        capabilities={"job_types": ["feed_collect"]},
    )
    other = product.create_employee(user_id=None, display_name="运营乙", email=None, status="active")
    other_agent = AccountRepository(db_session).register_agent(
        employee_id=other.id,
        device_name="other-pc",
        machine_fingerprint="fp-other",
        agent_version="0.1.0",
        capabilities={"job_types": ["feed_collect"]},
    )
    db_session.commit()

    client = _client(db_session, role="operator", user_id="op-user")
    response = client.get("/api/local-agents")
    assert response.status_code == 200
    ids = {item["id"] for item in response.json()}
    assert bound.id in ids
    assert unbound.id in ids
    assert other_agent.id not in ids


def test_resolve_discover_matches_by_fingerprint(db_session):
    product = ProductRepository(db_session)
    employee = product.create_employee(user_id="op-user", display_name="运营甲", email=None, status="active")
    agent = AccountRepository(db_session).register_agent(
        employee_id=None,
        device_name="WIN-1 [win-1-de]",
        machine_fingerprint="win-1-demo-fingerprint",
        agent_version="0.1.0",
        capabilities={"job_types": ["feed_collect"]},
    )
    db_session.commit()

    client = _client(db_session, role="operator", user_id="op-user")
    response = client.post(
        "/api/product/me/local-agents/resolve-discover",
        json={
            "items": [
                {
                    "device_name": "WIN-1",
                    "machine_fingerprint": "win-1-demo-fingerprint",
                    "bridge_port": 18765,
                },
                {
                    "device_name": "WIN-1",
                    "machine_fingerprint": "win-1-demo-fingerprint",
                    "bridge_port": 18766,
                },
            ],
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert len(body) == 1
    assert body[0]["agent"]["id"] == agent.id
    assert body[0]["bridge_port"] == 18765
