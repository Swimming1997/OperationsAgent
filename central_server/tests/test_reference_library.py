from fastapi.testclient import TestClient
from sqlalchemy import func, select

from intelligence_engine.db.models import CommentSnapshot, ReferenceLibraryEvent, utcnow
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


def test_reference_library_manual_select_maps_p0_fields_and_locks(db_session):
    content = _seed_content(db_session)
    client = _client(db_session)

    first = client.post(
        f"/api/intelligence/contents/{content.id}/reference-library-items",
        json={
            "library_type": "lead",
            "selection_sources": ["ai"],
            "selected_reason": "评论命中求推",
            "rating": "good",
            "matched_keywords": ["求推"],
            "user_id": "admin-user",
        },
    )
    assert first.status_code == 200, first.text
    body = first.json()
    assert body["library_type"] == "lead"
    assert body["rating"] == "good"
    assert body["selection_sources"] == ["ai", "manual"]
    assert body["matched_keywords"] == ["求推"]
    assert body["selected_at"]
    assert body["metadata"]["selection_locked_by_manual"] is True

    second = client.post(
        f"/api/intelligence/contents/{content.id}/reference-library-items",
        json={
            "library_type": "non_lead",
            "selected_reason": "人工改为非获客",
            "rating": "watching",
            "user_id": "admin-user",
        },
    )
    assert second.status_code == 200, second.text
    assert second.json()["id"] == body["id"]
    assert second.json()["library_type"] == "non_lead"
    assert second.json()["rating"] == "watching"

    listing = client.get("/api/reference-library/items")
    assert listing.json()["total"] == 1


def test_reference_library_legacy_values_are_mapped(db_session):
    content = _seed_content(db_session)
    client = _client(db_session)
    response = client.post(
        f"/api/intelligence/contents/{content.id}/reference-library-items",
        json={"library_type": "benchmark_work", "rating": "A", "user_id": "admin-user"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["library_type"] == "uncategorized"
    assert response.json()["rating"] == "good"


def test_rule_profile_list_update_and_ai_re_evaluate(db_session):
    content = _seed_content(db_session)
    client = _client(db_session)

    profiles = client.get("/api/benchmark-rule-profiles")
    assert profiles.status_code == 200, profiles.text
    xhs_non_lead = next(item for item in profiles.json() if item["platform"] == "xhs" and item["library_type"] == "non_lead")
    assert xhs_non_lead["version"] == 1

    updated = client.put(
        f"/api/benchmark-rule-profiles/{xhs_non_lead['id']}",
        json={"config": {"lead_intent_required": False, "rating_thresholds": {"poor": 50, "medium": 100, "good": 500}}},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["version"] == 2

    response = client.post(
        "/api/reference-library/items/re-evaluate",
        json={"content_ids": [content.id], "trigger_source": "test"},
    )
    assert response.status_code == 200, response.text
    result = response.json()["results"][0]
    assert result["status"] == "created"
    assert result["library_type"] == "non_lead"
    assert result["rating"] == "medium"

    detail = client.get(f"/api/intelligence/contents/{content.id}/product-detail")
    item = detail.json()["reference_library_items"][0]
    assert item["selection_sources"] == ["ai"]
    assert item["metadata"]["rule_profile_version"] == 2
    assert item["metadata"]["trigger_source"] == "test"


def test_ai_re_evaluate_skips_manual_locked_item(db_session):
    content = _seed_content(db_session)
    client = _client(db_session)
    manual = client.post(
        f"/api/intelligence/contents/{content.id}/reference-library-items",
        json={"library_type": "lead", "rating": "watching", "user_id": "admin-user"},
    )
    assert manual.status_code == 200, manual.text

    response = client.post("/api/reference-library/items/re-evaluate", json={"content_ids": [content.id]})
    assert response.status_code == 200, response.text
    result = response.json()["results"][0]
    assert result["status"] == "skipped_manual_locked"
    assert result["item_id"] == manual.json()["id"]
    assert result["library_type"] == "lead"
    assert result["rating"] == "watching"


def test_reference_library_events_api_returns_audit_trail(db_session):
    content = _seed_content(db_session)
    client = _client(db_session)
    created = client.post(
        f"/api/intelligence/contents/{content.id}/reference-library-items",
        json={"library_type": "lead", "rating": "watching", "user_id": "admin-user"},
    )
    assert created.status_code == 200, created.text

    updated = client.patch(
        f"/api/reference-library/items/{created.json()['id']}",
        json={"rating": "good", "user_id": "admin-user"},
    )
    assert updated.status_code == 200, updated.text

    events = client.get(f"/api/reference-library/items/{created.json()['id']}/events")
    assert events.status_code == 200, events.text
    event_types = [item["event_type"] for item in events.json()]
    assert "created" in event_types
    assert "updated" in event_types


def test_reference_library_creative_material_preparation(db_session):
    content = _seed_content(db_session)
    db_session.add(
        CommentSnapshot(
            content_id=content.id,
            platform_comment_id="comment-creative-1",
            body_text="这个方案正好解决了我的投稿焦虑",
            like_count=12,
            fetched_at=utcnow(),
            raw_payload_json={},
        )
    )
    db_session.commit()
    client = _client(db_session)
    created = client.post(
        f"/api/intelligence/contents/{content.id}/reference-library-items",
        json={"library_type": "non_lead", "rating": "good", "material_tags": ["标题结构"]},
    )
    assert created.status_code == 200, created.text

    response = client.post(
        f"/api/reference-library/items/{created.json()['id']}/creative-material",
        json={
            "reusable_angles": ["焦虑场景切入"],
            "selling_points": ["投稿规划"],
            "pain_points": ["投稿焦虑"],
            "risk_notes": ["避免夸大承诺"],
            "applicable_business_type_ids": ["biz-1"],
            "operator_note": "适合拆标题",
            "material_tags": ["标题结构", "评论洞察"],
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    material = body["metadata"]["creative_material"]
    assert material["title"] == "SCI投稿经验"
    assert material["comment_highlights"][0]["body_text"] == "这个方案正好解决了我的投稿焦虑"
    assert material["reusable_angles"] == ["焦虑场景切入"]
    assert body["material_tags"] == ["标题结构", "评论洞察"]
    assert body["note"] == "适合拆标题"
    event = db_session.scalar(
        select(ReferenceLibraryEvent).where(
            ReferenceLibraryEvent.library_item_id == body["id"],
            ReferenceLibraryEvent.event_type == "material_prepared",
        )
    )
    assert event is not None


def test_reference_library_list_and_pool_filters_by_p0_fields(db_session):
    content = _seed_content(db_session)
    client = _client(db_session)
    created = client.post(
        f"/api/intelligence/contents/{content.id}/reference-library-items",
        json={
            "library_type": "lead",
            "selection_sources": ["ai"],
            "matched_keywords": ["求推"],
            "rating": "good",
            "user_id": "admin-user",
        },
    )
    assert created.status_code == 200, created.text

    reference_listing = client.get(
        "/api/reference-library/items",
        params={"platform": "xhs", "library_type": "lead", "selection_source": "ai", "rating": "good"},
    )
    assert reference_listing.status_code == 200, reference_listing.text
    assert reference_listing.json()["total"] == 1
    assert reference_listing.json()["items"][0]["platform"] == "xhs"

    pool_listing = client.get(
        "/api/intelligence/contents/product",
        params={
            "in_reference_library": "true",
            "reference_library_type": "lead",
            "selection_source": "ai",
            "reference_rating": "good",
        },
    )
    assert pool_listing.status_code == 200, pool_listing.text
    item = next(row for row in pool_listing.json()["items"] if row["content_id"] == content.id)
    assert item["in_reference_library"] is True
    assert item["reference_library_type"] == "lead"
    assert item["reference_library_rating"] == "good"
    assert item["reference_selection_sources"] == ["ai", "manual"]
    assert item["reference_matched_keywords"] == ["求推"]

    hidden = client.get("/api/intelligence/contents/product", params={"in_reference_library": "false"})
    assert hidden.status_code == 200, hidden.text
    assert all(row["content_id"] != content.id for row in hidden.json()["items"])


def test_reference_library_list_content_query_matches_title(db_session):
    content = _seed_content(db_session)
    client = _client(db_session)
    created = client.post(
        f"/api/intelligence/contents/{content.id}/reference-library-items",
        json={"library_type": "non_lead", "user_id": "admin-user"},
    )
    assert created.status_code == 200, created.text

    hit = client.get("/api/reference-library/items", params={"content_query": "SCI投稿"})
    assert hit.status_code == 200, hit.text
    assert hit.json()["total"] == 1

    legacy = client.get("/api/reference-library/items", params={"search_keyword": "SCI投稿"})
    assert legacy.status_code == 200, legacy.text
    assert legacy.json()["total"] == 1

    miss = client.get("/api/reference-library/items", params={"content_query": "__no_such_title__"})
    assert miss.status_code == 200, miss.text
    assert miss.json()["total"] == 0


def test_reference_library_list_search_keyword_matches_title_and_metadata(db_session):
    content = _seed_content(db_session)
    client = _client(db_session)
    created = client.post(
        f"/api/intelligence/contents/{content.id}/reference-library-items",
        json={"library_type": "non_lead", "user_id": "admin-user"},
    )
    assert created.status_code == 200, created.text

    hit = client.get("/api/reference-library/items", params={"search_keyword": "SCI投稿"})
    assert hit.status_code == 200, hit.text
    assert hit.json()["total"] == 1

    miss = client.get("/api/reference-library/items", params={"search_keyword": "__no_such_title__"})
    assert miss.status_code == 200, miss.text
    assert miss.json()["total"] == 0


def test_reference_library_bulk_partial_success_and_idempotency(db_session):
    content = _seed_content(db_session)
    client = _client(db_session)
    payload = {
        "items": [
            {
                "content_id": content.id,
                "library_type": "lead",
                "rating": "watching",
                "selected_reason": "批量人工入库",
            },
            {
                "content_id": "missing-content",
                "library_type": "lead",
                "rating": "watching",
            },
        ]
    }

    first = client.post("/api/reference-library/items/bulk", json=payload, headers={"Idempotency-Key": "bulk-1"})
    second = client.post("/api/reference-library/items/bulk", json=payload, headers={"Idempotency-Key": "bulk-1"})

    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert len(first.json()["succeeded"]) == 1
    assert len(first.json()["failed"]) == 1
    assert first.json()["succeeded"][0]["id"] == second.json()["succeeded"][0]["id"]
    event_count = db_session.scalar(
        select(func.count(ReferenceLibraryEvent.id)).where(ReferenceLibraryEvent.library_item_id == first.json()["succeeded"][0]["id"])
    )
    assert event_count == 1


def test_reference_library_bulk_atomic_requires_admin(db_session):
    content = _seed_content(db_session)
    client = _client(db_session)
    response = client.post(
        "/api/reference-library/items/bulk?atomic=true",
        headers={"X-Role": "operator", "X-User-Id": "operator-user"},
        json={"items": [{"content_id": content.id, "library_type": "lead", "rating": "watching"}]},
    )
    assert response.status_code == 403
