from datetime import timedelta

from fastapi.testclient import TestClient

from intelligence_engine.db.models import ReferenceLibraryItem, User, utcnow
from intelligence_engine.db.session import get_db
from intelligence_engine.main import create_app
from intelligence_engine.security.intelligence_access import OPERATOR_REFERENCE_REVOKE_WINDOW
from tests.test_intelligence_pool_product_fields import _seed_content


def _client(db_session, role: str, user_id: str) -> TestClient:
    app = create_app()

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    client.headers.update({"X-Role": role, "X-User-Id": user_id})
    return client


def test_operator_cannot_re_evaluate_but_can_revoke_own_item_within_window(db_session):
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

    revoke = operator.post(f"/api/reference-library/items/{item_id}/revoke")
    assert revoke.status_code == 200, revoke.text
    assert revoke.json()["status"] == "archived"

    events = operator.get(f"/api/reference-library/items/{item_id}/events")
    assert events.status_code == 200
    assert any(event["event_type"] == "revoked" for event in events.json())


def test_supervisor_archives_via_archive_not_revoke(db_session):
    content = _seed_content(db_session)
    operator = _client(db_session, "operator", "operator-user")
    create = operator.post(
        f"/api/intelligence/contents/{content.id}/reference-library-items",
        json={"library_type": "lead", "rating": "watching", "user_id": "operator-user"},
    )
    assert create.status_code == 200, create.text
    item_id = create.json()["id"]

    supervisor = _client(db_session, "supervisor", "supervisor-user")
    revoke = supervisor.post(f"/api/reference-library/items/{item_id}/revoke")
    assert revoke.status_code == 403

    archive = supervisor.post(f"/api/reference-library/items/{item_id}/archive")
    assert archive.status_code == 200, archive.text

    events = supervisor.get(f"/api/reference-library/items/{item_id}/events")
    assert any(event["event_type"] == "archived" for event in events.json())


def test_operator_cannot_revoke_other_users_reference_item(db_session):
    content = _seed_content(db_session)
    db_session.add(User(id="operator-b", username="operator-b", display_name="运营B"))
    db_session.flush()
    owner = _client(db_session, "operator", "operator-user")
    other = _client(db_session, "operator", "operator-b")
    create = owner.post(
        f"/api/intelligence/contents/{content.id}/reference-library-items",
        json={"library_type": "lead", "rating": "watching", "user_id": "operator-user"},
    )
    assert create.status_code == 200, create.text
    item_id = create.json()["id"]

    revoke = other.post(f"/api/reference-library/items/{item_id}/revoke")
    assert revoke.status_code == 403


def test_operator_revoke_window_expired(db_session):
    content = _seed_content(db_session)
    operator = _client(db_session, "operator", "operator-user")
    create = operator.post(
        f"/api/intelligence/contents/{content.id}/reference-library-items",
        json={"library_type": "lead", "rating": "watching", "user_id": "operator-user"},
    )
    assert create.status_code == 200, create.text
    item_id = create.json()["id"]
    item = db_session.get(ReferenceLibraryItem, item_id)
    item.created_at = utcnow() - OPERATOR_REFERENCE_REVOKE_WINDOW - timedelta(seconds=1)
    db_session.flush()

    revoke = operator.post(f"/api/reference-library/items/{item_id}/revoke")
    assert revoke.status_code == 403


def test_sales_can_read_intelligence_and_reference_library(db_session):
    content = _seed_content(db_session)
    admin = _client(db_session, "admin", "admin-user")
    created = admin.post(
        f"/api/intelligence/contents/{content.id}/reference-library-items",
        json={"library_type": "lead", "rating": "watching"},
    )
    assert created.status_code == 200, created.text

    sales = _client(db_session, "sales", "sales-user")
    listing = sales.get("/api/intelligence/contents/product")
    assert listing.status_code == 200, listing.text
    detail = sales.get(f"/api/intelligence/contents/{content.id}/product-detail")
    assert detail.status_code == 200, detail.text
    library = sales.get("/api/reference-library/items")
    assert library.status_code == 200, library.text
    events = sales.get(f"/api/reference-library/items/{created.json()['id']}/events")
    assert events.status_code == 200, events.text
    scenario_filters = sales.get("/api/product/me/intelligence/scenario-filters")
    assert scenario_filters.status_code == 200, scenario_filters.text


def test_sales_cannot_create_reference_library_item(db_session):
    content = _seed_content(db_session)
    sales = _client(db_session, "sales", "sales-user")
    response = sales.post(
        f"/api/intelligence/contents/{content.id}/reference-library-items",
        json={"library_type": "lead", "rating": "watching", "user_id": "sales-user"},
    )
    assert response.status_code == 403


def test_sales_cannot_upsert_scenario_filters(db_session):
    sales = _client(db_session, "sales", "sales-user")
    response = sales.put(
        "/api/product/me/intelligence/scenario-filters/pending",
        json={"filters": {"in_reference_library": "false"}, "rolling": {}},
    )
    assert response.status_code == 403
