from fastapi.testclient import TestClient

from intelligence_engine.db.session import get_db
from intelligence_engine.main import create_app
from intelligence_engine.storage.repositories.workflow_repository import WorkflowRepository
from tests.test_intelligence_pool_product_fields import _seed_content


def _client(db_session) -> TestClient:
    app = create_app()

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    client.headers.update({"X-Role": "admin", "X-User-Id": "admin-user"})
    return client


def test_manual_tags_patch_and_note(db_session):
    content = _seed_content(db_session)
    client = _client(db_session)
    response = client.patch(
        f"/api/intelligence/contents/{content.id}/manual-tags",
        json={"manual_tags": ["可仿写", "求助"], "user_id": "admin-user"},
    )
    assert response.status_code == 200
    assert response.json()["metadata"]["manual_tags"] == ["可仿写", "求助"]
    notes = WorkflowRepository(db_session).list_notes(content_id=content.id)
    assert any("更新运营标签" in note.note for note in notes)
