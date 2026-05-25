from fastapi.testclient import TestClient

from intelligence_engine.audit.intelligence_center_audit import audit_reference_library
from intelligence_engine.db.session import get_db
from intelligence_engine.main import create_app
from intelligence_engine.storage.repositories.reference_library_repository import ReferenceLibraryRepository
from tests.test_intelligence_pool_product_fields import _seed_content


def _client(db_session) -> TestClient:
    app = create_app()

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    client.headers.update({"X-Role": "admin", "X-User-Id": "admin-user"})
    return client


def test_reference_library_duplicate_active_detection(db_session):
    content = _seed_content(db_session)
    repo = ReferenceLibraryRepository(db_session)
    repo.create_item(
        content_id=content.id,
        library_type="benchmark_work",
        created_by_user_id="admin-user",
        created_by_employee_id=None,
        selected_reason="案例",
        rating="A",
        manual_tags=["可仿写"],
        material_tags=[],
        usage_status="unused",
        note=None,
        metadata={},
    )
    repo.create_item(
        content_id=content.id,
        library_type="benchmark_work",
        created_by_user_id="admin-user",
        created_by_employee_id=None,
        selected_reason="重复",
        rating="B",
        manual_tags=[],
        material_tags=[],
        usage_status="unused",
        note=None,
        metadata={},
    )
    report = audit_reference_library(db_session)
    assert report["total"] >= 1
    assert report["duplicate_active_groups"] == []


def test_reference_library_detail_returns_items(db_session):
    content = _seed_content(db_session)
    client = _client(db_session)
    create_resp = client.post(
        f"/api/intelligence/contents/{content.id}/reference-library-items",
        json={"library_type": "benchmark_work", "selected_reason": "高互动", "rating": "A", "user_id": "admin-user"},
    )
    assert create_resp.status_code == 200
    detail = client.get(f"/api/intelligence/contents/{content.id}/product-detail")
    assert detail.status_code == 200
    assert len(detail.json()["reference_library_items"]) == 1
    assert detail.json()["reference_library_items"][0]["created_by_user_id"] == "admin-user"
