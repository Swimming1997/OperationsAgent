"""Smoke: saved scenario filters do not break intelligence list API."""

import os
import tempfile

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from intelligence_engine.db import models  # noqa: F401
from intelligence_engine.db.base import Base
from intelligence_engine.db.session import get_db
from intelligence_engine.domain.user_intelligence_scenario_filter_schemas import IntelligenceScenarioRollingConfig
from intelligence_engine.main import create_app
from intelligence_engine.services.intelligence_scenario_filter_service import resolve_discovered_after


def _client(db_session) -> TestClient:
    app = create_app()

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)


def test_saved_filters_and_intelligence_list_smoke():
    path = tempfile.mktemp(suffix=".db")
    engine = create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    client = _client(db)

    try:
        bootstrap = client.post(
            "/api/auth/bootstrap-admin",
            json={"username": "admin", "display_name": "Admin", "password": "AdminPass123!"},
        )
        assert bootstrap.status_code == 200, bootstrap.text
        token = bootstrap.json()["access_token"]
        user_id = bootstrap.json()["user"]["id"]
        headers = {"Authorization": f"Bearer {token}"}

        put = client.put(
            "/api/product/me/intelligence/scenario-filters/pending",
            headers=headers,
            json={
                "filters": {"in_reference_library": "false", "min_like_count": "50"},
                "rolling": {"discovered_after_days": 14},
            },
        )
        assert put.status_code == 200, put.text
        saved = put.json()

        resolved = resolve_discovered_after(
            saved["filters"],
            IntelligenceScenarioRollingConfig(**saved["rolling"]),
        )
        assert resolved["discovered_after"]
        assert resolved["min_like_count"] == "50"

        list_headers = {"X-Role": "admin", "X-User-Id": user_id}
        list_resp = client.get(
            "/api/intelligence/contents/product",
            headers=list_headers,
            params={
                **resolved,
                "sort_by": "latest_discovered_at",
                "sort_order": "desc",
                "page": "1",
                "page_size": "20",
            },
        )
        assert list_resp.status_code == 200, list_resp.text
        body = list_resp.json()
        assert "items" in body
        assert "total" in body

        delete = client.delete("/api/product/me/intelligence/scenario-filters/pending", headers=headers)
        assert delete.status_code == 204

        list_resp_2 = client.get(
            "/api/intelligence/contents/product",
            headers=list_headers,
            params={
                "sort_by": "latest_discovered_at",
                "sort_order": "desc",
                "page": "1",
                "page_size": "20",
            },
        )
        assert list_resp_2.status_code == 200
    finally:
        db.close()
        engine.dispose()
        if os.path.exists(path):
            os.remove(path)
