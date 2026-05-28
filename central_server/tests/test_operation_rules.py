from fastapi.testclient import TestClient

from intelligence_engine.db.session import get_db
from intelligence_engine.domain.enums import OperationRuleType
from intelligence_engine.main import create_app


def _client(db_session, role: str = "admin", user_id: str = "admin-user") -> TestClient:
    app = create_app()

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    client.headers.update({"X-Role": role, "X-User-Id": user_id})
    return client


def test_operation_rule_crud_and_filters(db_session):
    client = _client(db_session)
    created = client.post(
        "/api/operation-rules",
        json={
            "rule_type": OperationRuleType.TITLE.value,
            "title": "标题避免夸张词",
            "content": "不要使用绝对化承诺",
            "platform": "xhs",
            "enabled": True,
        },
    )
    assert created.status_code == 200, created.text
    rule_id = created.json()["id"]
    assert created.json()["version"] == 1

    listed = client.get("/api/operation-rules", params={"rule_type": OperationRuleType.TITLE.value, "platform": "xhs"})
    assert listed.status_code == 200
    assert any(item["id"] == rule_id for item in listed.json())

    updated = client.patch(
        f"/api/operation-rules/{rule_id}",
        json={"content": "不要使用绝对化承诺，补充案例说明", "bump_version": True},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["version"] == 2

    deleted = client.delete(f"/api/operation-rules/{rule_id}")
    assert deleted.status_code == 204
    listed_after_delete = client.get("/api/operation-rules", params={"rule_type": OperationRuleType.TITLE.value, "platform": "xhs"})
    assert all(item["id"] != rule_id for item in listed_after_delete.json())


def test_operator_cannot_create_operation_rule(db_session):
    client = _client(db_session, role="operator", user_id="operator-user")
    response = client.post(
        "/api/operation-rules",
        json={
            "rule_type": OperationRuleType.BODY.value,
            "title": "正文",
            "content": "test",
            "enabled": True,
        },
    )
    assert response.status_code == 403


def test_operator_cannot_delete_operation_rule(db_session):
    admin = _client(db_session)
    created = admin.post(
        "/api/operation-rules",
        json={
            "rule_type": OperationRuleType.BODY.value,
            "title": "正文",
            "content": "test",
            "enabled": True,
        },
    )
    rule_id = created.json()["id"]
    operator = _client(db_session, role="operator", user_id="operator-user")
    response = operator.delete(f"/api/operation-rules/{rule_id}")
    assert response.status_code == 403
