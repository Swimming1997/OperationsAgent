from fastapi.testclient import TestClient

from intelligence_engine.db.models import Employee, User
from intelligence_engine.db.session import get_db
from intelligence_engine.domain.enums import Platform, SessionStatus
from intelligence_engine.main import create_app
from intelligence_engine.storage.repositories.account_repository import AccountRepository
from intelligence_engine.storage.repositories.product_repository import ProductRepository
from tests.task_template_helpers import create_feed_template, run_template


def _client(db_session, role: str, user_id: str) -> TestClient:
    app = create_app()

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    client.headers.update({"X-Role": role, "X-User-Id": user_id})
    return client


def _seed_operator_account(db_session):
    db_session.add(User(id="operator-user", username="operator1", display_name="运营甲", status="active"))
    employee = Employee(id="employee-1", user_id="operator-user", display_name="运营甲", status="active")
    db_session.add(employee)
    repo = ProductRepository(db_session)
    business_type = repo.create_business_account_type(name="论文服务", description=None, enabled=True)
    agent = AccountRepository(db_session).register_agent(
        employee_id=employee.id,
        device_name="op-pc",
        machine_fingerprint="op-fp",
        agent_version="0.2.0",
        capabilities={"tasks": ["feed_collect"]},
    )
    account = AccountRepository(db_session).create_account(
        employee_id=employee.id,
        platform=Platform.XHS.value,
        display_name="运营账号A",
        external_account_id=None,
        business_account_type=None,
        business_account_type_id=business_type.id,
        default_agent_id=agent.id,
        metadata={},
    )
    AccountRepository(db_session).create_session(
        account=account,
        local_agent_id=agent.id,
        session_type="browser_profile",
        profile_ref="profiles/op",
        cookie_ref=None,
        status=SessionStatus.READY.value,
        session_meta={},
    )
    db_session.flush()
    return business_type, account, employee


def test_operator_creates_template_and_lists_in_same_business_type(db_session):
    business_type, account, _employee = _seed_operator_account(db_session)
    operator = _client(db_session, "operator", "operator-user")

    create = operator.post(
        "/api/task-templates/recommendation-feed",
        json={
            "name": "我的推荐流",
            "business_account_type_id": business_type.id,
            "enabled": True,
            "feed_type": "xhs_home_feed",
            "target_count": 10,
            "refresh_rounds": 1,
            "per_round_scroll_target": 10,
        },
    )
    assert create.status_code == 200, create.text
    template_id = create.json()["id"]

    supervisor = _client(db_session, "supervisor", "supervisor-user")
    supervisor_create = supervisor.post(
        "/api/task-templates/recommendation-feed",
        json={
            "name": "主管推荐流",
            "business_account_type_id": business_type.id,
            "enabled": True,
            "feed_type": "xhs_home_feed",
            "target_count": 10,
            "refresh_rounds": 1,
            "per_round_scroll_target": 10,
        },
    )
    assert supervisor_create.status_code == 200, supervisor_create.text

    listed = operator.get("/api/task-templates/list")
    assert listed.status_code == 200
    names = {item["name"] for item in listed.json()}
    assert "我的推荐流" in names
    assert "主管推荐流" in names

    patch_other = operator.patch(
        f"/api/task-templates/recommendation-feed/{supervisor_create.json()['id']}",
        json={"name": "试图改名"},
    )
    assert patch_other.status_code == 403

    run = run_template(operator, template_id, account.id)
    assert run.status_code == 200, run.text


def test_operator_cannot_run_with_other_account(db_session):
    business_type, account, employee = _seed_operator_account(db_session)
    db_session.add(User(id="operator-b", username="operator-b", display_name="运营乙", status="active"))
    db_session.flush()
    other_account = AccountRepository(db_session).create_account(
        employee_id="employee-b",
        platform=Platform.XHS.value,
        display_name="运营账号B",
        external_account_id=None,
        business_account_type=None,
        business_account_type_id=business_type.id,
        default_agent_id=account.default_agent_id,
        metadata={},
    )
    db_session.flush()

    supervisor = _client(db_session, "supervisor", "supervisor-user")
    created = supervisor.post(
        "/api/task-templates/recommendation-feed",
        json={
            "name": "共享模板",
            "business_account_type_id": business_type.id,
            "enabled": True,
            "feed_type": "xhs_home_feed",
            "target_count": 5,
            "refresh_rounds": 1,
            "per_round_scroll_target": 5,
        },
    )
    template_id = created.json()["id"]

    operator = _client(db_session, "operator", "operator-user")
    denied = run_template(operator, template_id, other_account.id)
    assert denied.status_code == 403

    allowed = run_template(operator, template_id, account.id)
    assert allowed.status_code in {200, 409}


def test_operator_schedule_requires_own_template(db_session):
    business_type, account, _employee = _seed_operator_account(db_session)
    operator = _client(db_session, "operator", "operator-user")
    own = operator.post(
        "/api/task-templates/recommendation-feed",
        json={
            "name": "可调度模板",
            "business_account_type_id": business_type.id,
            "enabled": True,
            "feed_type": "xhs_home_feed",
            "target_count": 5,
            "refresh_rounds": 1,
            "per_round_scroll_target": 5,
        },
    )
    own_id = own.json()["id"]

    supervisor = _client(db_session, "supervisor", "supervisor-user")
    other = supervisor.post(
        "/api/task-templates/recommendation-feed",
        json={
            "name": "主管模板",
            "business_account_type_id": business_type.id,
            "enabled": True,
            "feed_type": "xhs_home_feed",
            "target_count": 5,
            "refresh_rounds": 1,
            "per_round_scroll_target": 5,
        },
    )
    other_id = other.json()["id"]

    denied = operator.post(
        "/api/task-schedules",
        json={
            "task_template_id": other_id,
            "executor_account_id": account.id,
            "schedule_type": "interval_seconds",
            "interval_seconds": 3600,
            "enabled": True,
        },
    )
    assert denied.status_code == 403

    allowed = operator.post(
        "/api/task-schedules",
        json={
            "task_template_id": own_id,
            "executor_account_id": account.id,
            "schedule_type": "interval_seconds",
            "interval_seconds": 3600,
            "enabled": True,
        },
    )
    assert allowed.status_code == 200, allowed.text
    assert allowed.json()["next_run_at"] is not None


def test_operator_can_delete_own_template_not_others(db_session):
    business_type, account, _employee = _seed_operator_account(db_session)
    operator = _client(db_session, "operator", "operator-user")

    own = operator.post(
        "/api/task-templates/recommendation-feed",
        json={
            "name": "可删除模板",
            "business_account_type_id": business_type.id,
            "enabled": True,
            "feed_type": "xhs_home_feed",
            "target_count": 5,
            "refresh_rounds": 1,
            "per_round_scroll_target": 5,
        },
    )
    assert own.status_code == 200, own.text
    own_id = own.json()["id"]

    supervisor = _client(db_session, "supervisor", "supervisor-user")
    other = supervisor.post(
        "/api/task-templates/recommendation-feed",
        json={
            "name": "主管模板",
            "business_account_type_id": business_type.id,
            "enabled": True,
            "feed_type": "xhs_home_feed",
            "target_count": 5,
            "refresh_rounds": 1,
            "per_round_scroll_target": 5,
        },
    )
    assert other.status_code == 200, other.text
    other_id = other.json()["id"]

    denied = operator.delete(f"/api/task-templates/{other_id}")
    assert denied.status_code == 403

    deleted = operator.delete(f"/api/task-templates/{own_id}")
    assert deleted.status_code == 204
    assert operator.get(f"/api/task-templates/{own_id}").status_code == 404


def test_supervisor_can_delete_any_template(db_session):
    business_type, _account, _employee = _seed_operator_account(db_session)
    operator = _client(db_session, "operator", "operator-user")
    created = operator.post(
        "/api/task-templates/recommendation-feed",
        json={
            "name": "运营模板",
            "business_account_type_id": business_type.id,
            "enabled": True,
            "feed_type": "xhs_home_feed",
            "target_count": 5,
            "refresh_rounds": 1,
            "per_round_scroll_target": 5,
        },
    )
    template_id = created.json()["id"]

    supervisor = _client(db_session, "supervisor", "supervisor-user")
    response = supervisor.delete(f"/api/task-templates/{template_id}")
    assert response.status_code == 204


def test_operator_can_list_task_page_policy_resources(db_session):
    _seed_operator_account(db_session)
    operator = _client(db_session, "operator", "operator-user")

    for path in ("/api/behavior-profiles", "/api/network-egress-profiles", "/api/risk-policies"):
        response = operator.get(path)
        assert response.status_code == 200, response.text
