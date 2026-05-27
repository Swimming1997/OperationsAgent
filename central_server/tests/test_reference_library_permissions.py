from fastapi.testclient import TestClient

from intelligence_engine.db.session import get_db
from intelligence_engine.main import create_app
from tests.test_intelligence_pool_product_fields import _seed_content


def _client(db_session, role: str, user_id: str) -> TestClient:
    app = create_app()

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    client.headers.update({"X-Role": role, "X-User-Id": user_id})
    return client


def test_operator_cannot_re_evaluate_or_archive_reference_library(db_session):
    content = _seed_content(db_session)
    operator = _client(db_session, "operator", "operator-user")
    create = operator.post(
        f"/api/intelligence/contents/{content.id}/reference-library-items",
        json={"library_type": "lead", "rating": "watching", "user_id": "operator-user"},
    )
    assert create.status_code == 200, create.text
    item_id = create.json()["id"]

    re_eval = operator.post("/api/reference-library/items/re-evaluate", json={"content_ids": [content.id]})
    assert re_eval.status_code == 403

    archive = operator.post(f"/api/reference-library/items/{item_id}/archive")
    assert archive.status_code == 403


def test_sales_cannot_create_reference_library_item(db_session):
    content = _seed_content(db_session)
    sales = _client(db_session, "sales", "sales-user")
    response = sales.post(
        f"/api/intelligence/contents/{content.id}/reference-library-items",
        json={"library_type": "lead", "rating": "watching", "user_id": "sales-user"},
    )
    assert response.status_code == 403
