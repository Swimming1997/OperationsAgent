from fastapi.testclient import TestClient

from intelligence_engine.db.session import get_db
from intelligence_engine.main import create_app
from intelligence_engine.security.passwords import hash_password, verify_password


def _client(db_session) -> TestClient:
    app = create_app()

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)


def test_bootstrap_status_empty_system(db_session):
    client = _client(db_session)
    response = client.get("/api/auth/bootstrap-status")
    assert response.status_code == 200
    body = response.json()
    assert body["users_count"] == 0
    assert body["needs_bootstrap"] is True
    assert body["admin_exists"] is False


def test_bootstrap_admin_only_once_and_login(db_session):
    client = _client(db_session)
    bootstrap = client.post(
        "/api/auth/bootstrap-admin",
        json={
            "username": "admin",
            "display_name": "系统管理员",
            "email": "admin@demo.local",
            "password": "AdminPass123!",
        },
    )
    assert bootstrap.status_code == 200, bootstrap.text
    token = bootstrap.json()["access_token"]
    assert bootstrap.json()["user"]["roles"] == ["admin"]

    second = client.post(
        "/api/auth/bootstrap-admin",
        json={"username": "admin2", "display_name": "其他", "password": "x"},
    )
    assert second.status_code == 409

    status = client.get("/api/auth/bootstrap-status").json()
    assert status["users_count"] == 1
    assert status["needs_bootstrap"] is False

    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["username"] == "admin"

    login_ok = client.post("/api/auth/login", json={"username": "admin", "password": "AdminPass123!"})
    assert login_ok.status_code == 200
    assert login_ok.json()["access_token"]

    login_fail = client.post("/api/auth/login", json={"username": "admin", "password": "wrong"})
    assert login_fail.status_code == 401


def test_create_user_plaintext_password_hashed(db_session):
    client = _client(db_session)
    bootstrap = client.post(
        "/api/auth/bootstrap-admin",
        json={"username": "admin", "display_name": "Admin", "password": "AdminPass123!"},
    )
    token = bootstrap.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    created = client.post(
        "/api/users",
        headers=headers,
        json={
            "username": "supervisor1",
            "display_name": "主管一号",
            "password": "SuperPass123!",
            "role_names": ["supervisor"],
        },
    )
    assert created.status_code == 200, created.text

    from intelligence_engine.storage.repositories.product_repository import ProductRepository

    user = ProductRepository(db_session).get_user_by_username("supervisor1")
    assert user is not None
    assert user.password_hash is not None
    assert user.password_hash != "SuperPass123!"
    assert verify_password("SuperPass123!", user.password_hash)

    login = client.post("/api/auth/login", json={"username": "supervisor1", "password": "SuperPass123!"})
    assert login.status_code == 200


def test_employee_with_user_and_org_permissions(db_session):
    client = _client(db_session)
    bootstrap = client.post(
        "/api/auth/bootstrap-admin",
        json={"username": "admin", "display_name": "Admin", "password": "AdminPass123!"},
    )
    admin_headers = {"Authorization": f"Bearer {bootstrap.json()['access_token']}"}

    employee = client.post(
        "/api/employees/with-user",
        headers=admin_headers,
        json={
            "username": "operator1",
            "display_name": "运营一号",
            "password": "OperatorPass123!",
            "role": "operator",
        },
    )
    assert employee.status_code == 200, employee.text
    assert employee.json()["user_username"] == "operator1"
    assert employee.json()["account_count"] == 0

    operator_login = client.post("/api/auth/login", json={"username": "operator1", "password": "OperatorPass123!"})
    operator_headers = {"Authorization": f"Bearer {operator_login.json()['access_token']}"}

    denied_users = client.get("/api/users", headers=operator_headers)
    assert denied_users.status_code == 403

    allowed_intel = client.get("/api/intelligence/contents/product", headers=operator_headers)
    assert allowed_intel.status_code == 200


def test_password_hash_helpers():
    hashed = hash_password("secret")
    assert verify_password("secret", hashed)
    assert not verify_password("wrong", hashed)
