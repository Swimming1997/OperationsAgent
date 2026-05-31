from fastapi.testclient import TestClient

from intelligence_engine.db.session import get_db
from intelligence_engine.main import create_app
from intelligence_engine.services.manual_tag_service import ManualTagService
from intelligence_engine.storage.repositories.manual_tag_repository import ManualTagRepository
from tests.test_intelligence_pool_product_fields import _seed_content


def _client(db_session, *, role: str = "admin", user_id: str = "admin-user") -> TestClient:
    app = create_app()

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    client.headers.update({"X-Role": role, "X-User-Id": user_id})
    return client


def test_manual_tag_registry_create_list_and_set_content_tags(db_session):
    ManualTagService(db_session).ensure_bootstrap()
    content = _seed_content(db_session)
    client = _client(db_session)

    create_response = client.post("/api/manual-tags", json={"name": "可仿写"})
    assert create_response.status_code == 200
    tag_id = create_response.json()["id"]

    list_response = client.get("/api/manual-tags")
    assert list_response.status_code == 200
    assert any(item["name"] == "可仿写" for item in list_response.json()["items"])
    assert any(item["name"] == "稍后看" for item in list_response.json()["items"])

    patch_response = client.patch(
        f"/api/intelligence/contents/{content.id}/manual-tags",
        json={"tag_ids": [tag_id], "user_id": "admin-user"},
    )
    assert patch_response.status_code == 200
    assert patch_response.json()["metadata"]["manual_tags"] == ["可仿写"]
    assert ManualTagRepository(db_session).list_content_tag_names(content.id) == ["可仿写"]


def test_operator_cannot_delete_tag_in_use(db_session):
    from intelligence_engine.domain.enums import UserRoleName
    from intelligence_engine.security.auth import Principal

    ManualTagService(db_session).ensure_bootstrap()
    content = _seed_content(db_session)
    service = ManualTagService(db_session)
    repo = ManualTagRepository(db_session)
    tag = repo.create_tag(name="求助", created_by_user_id="operator-user")
    service.set_content_tags(
        content_id=content.id,
        tag_ids=[tag.id],
        principal=Principal(user_id="admin-user", role_names=frozenset({UserRoleName.ADMIN.value})),
    )
    db_session.commit()

    client = _client(db_session, role="operator", user_id="operator-user")
    response = client.delete(f"/api/manual-tags/{tag.id}")
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "tag_in_use"


def test_operator_can_delete_unused_own_tag(db_session):
    ManualTagService(db_session).ensure_bootstrap()
    client = _client(db_session, role="operator", user_id="operator-user")
    create_response = client.post("/api/manual-tags", json={"name": "临时标签"})
    assert create_response.status_code == 200
    tag_id = create_response.json()["id"]

    delete_response = client.delete(f"/api/manual-tags/{tag_id}")
    assert delete_response.status_code == 200
    assert ManualTagRepository(db_session).get_by_id(tag_id) is None


def test_reference_library_filter_untagged_and_by_tag(db_session):
    from intelligence_engine.db.models import ContentIdentity
    from intelligence_engine.storage.repositories.reference_library_repository import ReferenceLibraryRepository

    ManualTagService(db_session).ensure_bootstrap()
    content_tagged = _seed_content(db_session)
    content_untagged = ContentIdentity(
        platform="xhs",
        platform_content_id="pool-product-untagged",
        content_type="image_text",
        first_seen_at=content_tagged.first_seen_at,
        last_seen_at=content_tagged.last_seen_at,
        metadata_json={},
    )
    db_session.add(content_untagged)
    db_session.flush()

    repo = ManualTagRepository(db_session)
    tag = repo.create_tag(name="可仿写", created_by_user_id="admin-user")
    repo.replace_content_tags(content_id=content_tagged.id, tag_ids=[tag.id])

    ref_repo = ReferenceLibraryRepository(db_session)
    for content in (content_tagged, content_untagged):
        ref_repo.create_item(
            content_id=content.id,
            library_type="lead",
            created_by_user_id="admin-user",
            created_by_employee_id=None,
            selected_reason="test",
            rating="good",
            manual_tags=[],
            material_tags=[],
            usage_status="unused",
            note=None,
            metadata={},
            selection_sources=["manual"],
            matched_keywords=[],
        )
    db_session.commit()

    client = _client(db_session)
    untagged_response = client.get("/api/reference-library/items?untagged=true")
    assert untagged_response.status_code == 200
    assert untagged_response.json()["total"] == 1

    tagged_response = client.get(f"/api/reference-library/items?manual_tag_id={tag.id}")
    assert tagged_response.status_code == 200
    assert tagged_response.json()["total"] == 1
    assert tagged_response.json()["items"][0]["manual_tags"] == ["可仿写"]
