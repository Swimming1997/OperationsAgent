from fastapi.testclient import TestClient

from intelligence_engine.db.models import Employee, TaskTemplate, User
from intelligence_engine.db.session import get_db
from intelligence_engine.domain.enums import Platform, SessionStatus, TaskTemplateType
from intelligence_engine.main import create_app
from intelligence_engine.storage.repositories.account_repository import AccountRepository
from intelligence_engine.storage.repositories.product_repository import ProductRepository


def _client(db_session, role: str, user_id: str) -> TestClient:
    app = create_app()

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    client.headers.update({"X-Role": role, "X-User-Id": user_id})
    return client


def _seed_operator_with_legacy_template(db_session):
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
    template = TaskTemplate(
        name="旧版推荐流",
        template_type=TaskTemplateType.RECOMMENDATION_FEED_TASK.value,
        platform=Platform.XHS.value,
        account_id=None,
        business_account_type_id=None,
        config_json={
            "executor_account_id": account.id,
            "feed_type": "xhs_home_feed",
            "target_count": 33,
            "refresh_rounds": 3,
            "per_round_scroll_target": 40,
        },
        enabled=True,
    )
    db_session.add(template)
    db_session.commit()
    return business_type, account, template


def test_admin_can_read_legacy_template_detail(db_session):
    _business_type, _account, template = _seed_operator_with_legacy_template(db_session)
    admin = _client(db_session, "admin", "admin-user")

    response = admin.get(f"/api/task-templates/{template.id}")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["name"] == "旧版推荐流"
    assert body["business_account_type_id"]
    assert body["typed_payload"]["target_count"] == 33
    assert "executor_account_id" not in body["config"]
    assert "executor_account_id" not in body["typed_payload"]


def test_operator_lists_benchmark_groups_for_business_type(db_session):
    business_type, _account, _template = _seed_operator_with_legacy_template(db_session)
    operator = _client(db_session, "operator", "operator-user")

    response = operator.get(f"/api/business-account-types/{business_type.id}/benchmark-groups")
    assert response.status_code == 200, response.text


def test_operator_can_read_legacy_template_after_repair(db_session):
    _business_type, account, template = _seed_operator_with_legacy_template(db_session)
    operator = _client(db_session, "operator", "operator-user")

    response = operator.get(f"/api/task-templates/{template.id}")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["typed_payload"]["target_count"] == 33

    readiness = operator.get(f"/api/task-templates/{template.id}/readiness")
    assert readiness.status_code == 200, readiness.text

    run_readiness = operator.get(
        f"/api/task-templates/{template.id}/run-readiness",
        params={"executor_account_id": account.id},
    )
    assert run_readiness.status_code == 200, run_readiness.text
