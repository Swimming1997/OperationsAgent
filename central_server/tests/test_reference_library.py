from fastapi.testclient import TestClient

from intelligence_engine.db.session import get_db
from intelligence_engine.main import create_app
from tests.test_intelligence_pool_product_fields import _seed_content


def _client(db_session) -> TestClient:
    app = create_app()

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    client.headers.update({"X-Role": "admin", "X-User-Id": "admin-user"})
    return client


def test_reference_library_create_and_deduplicate(db_session):
    content = _seed_content(db_session)
    client = _client(db_session)
    payload = {
        "library_type": "benchmark_work",
        "selected_reason": "高互动 SCI 案例",
        "rating": "A",
        "manual_tags": ["可仿写"],
        "user_id": "admin-user",
    }
    first = client.post(f"/api/intelligence/contents/{content.id}/reference-library-items", json=payload)
    second = client.post(f"/api/intelligence/contents/{content.id}/reference-library-items", json=payload)
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["id"] == second.json()["id"]

    listing = client.get("/api/reference-library/items")
    assert listing.status_code == 200
    assert listing.json()["total"] == 1

    detail = client.get(f"/api/intelligence/contents/{content.id}/product-detail")
    assert detail.status_code == 200
    assert len(detail.json()["reference_library_items"]) == 1
