from fastapi.testclient import TestClient

from intelligence_engine.db.models import AccountSession
from intelligence_engine.db.session import get_db
from intelligence_engine.domain.enums import Platform
from intelligence_engine.main import create_app
from intelligence_engine.storage.repositories.account_repository import AccountRepository


def _client(db_session) -> TestClient:
    app = create_app()

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    client.headers.update({"X-Role": "admin", "X-User-Id": "admin-user"})
    return client


def test_users_roles_employees_and_agent_inventory_api(db_session):
    client = _client(db_session)

    roles_response = client.post("/api/product/bootstrap-default-roles")
    assert roles_response.status_code == 200
    assert {item["name"] for item in roles_response.json()} == {"admin", "supervisor", "operator", "sales"}

    user_response = client.post(
        "/api/users",
        json={
            "username": "alice",
            "display_name": "Alice",
            "email": "alice@example.local",
            "password": "AlicePass123!",
            "role_names": ["supervisor", "operator"],
        },
    )
    assert user_response.status_code == 200, user_response.text
    user = user_response.json()
    assert set(user["roles"]) == {"supervisor", "operator"}

    employee_response = client.post("/api/employees", json={"user_id": user["id"], "display_name": "Alice Ops", "email": "alice@example.local"})
    assert employee_response.status_code == 200
    employee = employee_response.json()

    agent = AccountRepository(db_session).register_agent(
        employee_id=employee["id"],
        device_name="alice-pc",
        machine_fingerprint="alice-fp",
        agent_version="0.2.0",
        capabilities={"tasks": ["feed_collect", "creator_monitor"]},
    )
    db_session.commit()

    agents_response = client.get("/api/local-agents")
    assert agents_response.status_code == 200
    body = agents_response.json()
    assert body[0]["id"] == agent.id
    assert body[0]["employee_display_name"] == "Alice Ops"
    assert body[0]["status"] == "online"
    assert body[0]["capabilities"]["tasks"] == ["feed_collect", "creator_monitor"]


def test_platform_account_product_api_includes_business_type_agent_and_session_health(db_session):
    client = _client(db_session)
    employee = client.post("/api/employees", json={"display_name": "Bob"}).json()
    business_type = client.post("/api/business-account-types", json={"name": "论文咨询型", "description": "SCI/投稿账号"}).json()
    agent = AccountRepository(db_session).register_agent(
        employee_id=employee["id"],
        device_name="bob-pc",
        machine_fingerprint="bob-fp",
        agent_version="0.2.0",
        capabilities={"platforms": ["xhs"]},
    )
    account = AccountRepository(db_session).create_account(
        employee_id=employee["id"],
        platform=Platform.XHS.value,
        display_name="小红书A",
        external_account_id="xhs-a",
        business_account_type="legacy",
        business_account_type_id=business_type["id"],
        metadata={"persona": "paper"},
    )
    agent.employee_id = employee["id"]
    db_session.add(
        AccountSession(
            account_id=account.id,
            local_agent_id=agent.id,
            platform=Platform.XHS.value,
            session_type="browser_profile",
            status="ready",
            session_meta_json={"profile_ref": "profiles/bob"},
        )
    )
    db_session.commit()

    response = client.get(f"/api/product/accounts/{account.id}")
    assert response.status_code == 200
    body = response.json()
    assert body["employee_display_name"] == "Bob"
    assert body["business_account_type_name"] == "论文咨询型"
    assert body["bindings"] == []
    assert body["session_health_status"] == "ready"
    assert body["usage_status"] == "need_login"
    assert body["consecutive_failures"] == 0


def test_benchmark_group_member_and_business_type_binding_api(db_session):
    client = _client(db_session)
    business_type = client.post("/api/business-account-types", json={"name": "A类账号"}).json()
    group = client.post("/api/benchmark-groups", json={"name": "SCI避坑类", "description": "对标账号组"}).json()

    member_response = client.post(
        f"/api/benchmark-groups/{group['id']}/members",
        json={
            "platform": "xhs",
            "creator_platform_id": "5d842aac00000000010097a4",
            "creator_profile_url": "https://www.xiaohongshu.com/user/profile/5d842aac00000000010097a4",
            "display_name": "对标账号",
            "platform_context": {"xsec_source": "pc_feed"},
        },
    )
    assert member_response.status_code == 200, member_response.text
    assert member_response.json()["creator_platform_id"] == "5d842aac00000000010097a4"

    bind_response = client.post(f"/api/benchmark-groups/{group['id']}/business-account-types", json={"business_account_type_id": business_type["id"]})
    assert bind_response.status_code == 200
    assert bind_response.json()["binding_id"]


def test_task_template_schedule_and_risk_policy_skeleton_api(db_session):
    client = _client(db_session)
    agent = AccountRepository(db_session).register_agent(
        employee_id=None,
        device_name="task-pc",
        machine_fingerprint="task-fp",
        agent_version="0.2.0",
        capabilities={},
    )
    account = AccountRepository(db_session).create_account(
        employee_id=None,
        platform=Platform.XHS.value,
        display_name="任务账号",
        external_account_id=None,
        business_account_type=None,
        default_agent_id=agent.id,
        metadata={},
    )
    db_session.commit()
    template = client.post(
        "/api/task-templates",
        json={
            "name": "论文账号推荐流巡检",
            "template_type": "recommendation_feed_task",
            "platform": "xhs",
            "config": {"executor_account_id": account.id, "feed_type": "xhs_home_feed", "target_count": 50},
        },
    ).json()
    schedule_response = client.post(
        "/api/task-schedules",
        json={"task_template_id": template["id"], "schedule_type": "interval_seconds", "interval_seconds": 1800},
    )
    assert schedule_response.status_code == 200
    assert schedule_response.json()["interval_seconds"] == 1800

    behavior = client.post("/api/behavior-profiles", json={"name": "balanced", "config": {"scroll_pause_ms": 1200}}).json()
    egress = client.post("/api/network-egress-profiles", json={"name": "local-direct", "strategy": "direct_local"}).json()
    policy_response = client.post(
        "/api/risk-policies",
        json={
            "name": "default-xhs",
            "behavior_profile_id": behavior["id"],
            "network_egress_profile_id": egress["id"],
            "config": {"daily_feed_runs": 12},
        },
    )
    assert policy_response.status_code == 200
    assert policy_response.json()["config"]["daily_feed_runs"] == 12
