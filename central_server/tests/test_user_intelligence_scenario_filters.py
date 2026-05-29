from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from intelligence_engine.db.session import get_db
from intelligence_engine.main import create_app
from intelligence_engine.services.intelligence_scenario_filter_service import (
    normalize_upsert_request,
    resolve_discovered_after,
    rolling_config_from_dict,
)
from intelligence_engine.domain.user_intelligence_scenario_filter_schemas import (
    IntelligenceScenarioFilterUpsertRequest,
    IntelligenceScenarioRollingConfig,
)


def _client(db_session) -> TestClient:
    app = create_app()

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)


def _bootstrap_admin(client: TestClient) -> tuple[str, str]:
    response = client.post(
        "/api/auth/bootstrap-admin",
        json={"username": "admin", "display_name": "Admin", "password": "AdminPass123!"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    return body["access_token"], body["user"]["id"]


def _create_operator(client: TestClient, admin_headers: dict) -> tuple[str, str]:
    created = client.post(
        "/api/users",
        headers=admin_headers,
        json={
            "username": "operator1",
            "display_name": "Operator One",
            "password": "OperatorPass123!",
            "role_names": ["operator"],
        },
    )
    assert created.status_code == 200, created.text
    login = client.post("/api/auth/login", json={"username": "operator1", "password": "OperatorPass123!"})
    assert login.status_code == 200, login.text
    body = login.json()
    return body["access_token"], body["user"]["id"]


def test_scenario_filter_endpoints_require_auth(db_session):
    client = _client(db_session)
    response = client.get("/api/product/me/intelligence/scenario-filters")
    assert response.status_code in {401, 403}


def test_put_get_delete_scenario_filters(db_session):
    client = _client(db_session)
    token, _user_id = _bootstrap_admin(client)
    headers = {"Authorization": f"Bearer {token}"}

    put = client.put(
        "/api/product/me/intelligence/scenario-filters/pending",
        headers=headers,
        json={
            "filters": {"in_reference_library": "false", "min_like_count": "20"},
            "rolling": {"discovered_after_days": 14},
        },
    )
    assert put.status_code == 200, put.text
    body = put.json()
    assert body["scenario"] == "pending"
    assert body["filters"]["in_reference_library"] == "false"
    assert body["filters"]["min_like_count"] == "20"
    assert body["rolling"]["discovered_after_days"] == 14
    assert body["is_user_customized"] is True

    listed = client.get("/api/product/me/intelligence/scenario-filters", headers=headers)
    assert listed.status_code == 200
    assert len(listed.json()["items"]) == 1

    got = client.get("/api/product/me/intelligence/scenario-filters/pending", headers=headers)
    assert got.status_code == 200
    assert got.json()["filters"]["min_like_count"] == "20"

    deleted = client.delete("/api/product/me/intelligence/scenario-filters/pending", headers=headers)
    assert deleted.status_code == 204

    missing = client.get("/api/product/me/intelligence/scenario-filters/pending", headers=headers)
    assert missing.status_code == 404


def test_scenario_filters_are_isolated_by_user(db_session):
    client = _client(db_session)
    admin_token, _admin_id = _bootstrap_admin(client)
    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    operator_token, _operator_id = _create_operator(client, admin_headers)
    operator_headers = {"Authorization": f"Bearer {operator_token}"}

    admin_put = client.put(
        "/api/product/me/intelligence/scenario-filters/hot",
        headers=admin_headers,
        json={"filters": {"min_like_count": "500"}, "rolling": {}},
    )
    assert admin_put.status_code == 200

    operator_get = client.get("/api/product/me/intelligence/scenario-filters/hot", headers=operator_headers)
    assert operator_get.status_code == 404

    operator_put = client.put(
        "/api/product/me/intelligence/scenario-filters/hot",
        headers=operator_headers,
        json={"filters": {"min_like_count": "200"}, "rolling": {}},
    )
    assert operator_put.status_code == 200

    admin_get = client.get("/api/product/me/intelligence/scenario-filters/hot", headers=admin_headers)
    assert admin_get.status_code == 200
    assert admin_get.json()["filters"]["min_like_count"] == "500"


def test_reject_quick_filter_keys(db_session):
    client = _client(db_session)
    token, _user_id = _bootstrap_admin(client)
    headers = {"Authorization": f"Bearer {token}"}

    response = client.put(
        "/api/product/me/intelligence/scenario-filters/all",
        headers=headers,
        json={"filters": {"sort_by": "like_count"}, "rolling": {}},
    )
    assert response.status_code == 422


def test_resolve_discovered_after_from_rolling():
    now = datetime.now(timezone.utc)
    resolved = resolve_discovered_after(
        {"in_reference_library": "false"},
        IntelligenceScenarioRollingConfig(discovered_after_days=7),
    )
    assert resolved["discovered_after"]
    parsed = datetime.fromisoformat(resolved["discovered_after"])
    assert parsed <= now
    assert parsed >= now - timedelta(days=8)


def test_normalize_upsert_request_prefers_absolute_discovered_after():
    filters_json, rolling_json = normalize_upsert_request(
        IntelligenceScenarioFilterUpsertRequest.model_validate(
            {
                "filters": {"discovered_after": "2026-01-01T00:00:00+00:00"},
                "rolling": {"discovered_after_days": 7},
            }
        )
    )
    assert filters_json["discovered_after"] == "2026-01-01T00:00:00+00:00"
    assert "discovered_after_days" not in rolling_json


def test_rolling_config_from_dict_rejects_invalid_days():
    with pytest.raises(Exception):
        rolling_config_from_dict({"discovered_after_days": 0})
