from fastapi.testclient import TestClient

from intelligence_engine.db.session import get_db
from intelligence_engine.main import create_app
from intelligence_engine.storage.repositories.account_repository import AccountRepository


def _client(db_session, *, role: str = "admin") -> TestClient:
    app = create_app()

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    client.headers.update({"X-Role": role, "X-User-Id": f"{role}-user"})
    return client


def _register_agent(db_session) -> str:
    agent = AccountRepository(db_session).register_agent(
        employee_id=None,
        device_name="pc-1",
        machine_fingerprint="snapshot-agent",
        agent_version="0.1.0",
        capabilities={},
    )
    db_session.commit()
    return agent.id


def test_report_account_snapshots_upserts_and_reconciles(db_session):
    client = _client(db_session)
    agent_id = _register_agent(db_session)

    first = client.post(
        f"/api/agents/{agent_id}/account-snapshots",
        json={
            "accounts": [
                {"local_account_id": "a1", "platform": "xhs", "display_name": "号一", "auth_status": "active"},
                {"local_account_id": "a2", "platform": "douyin", "display_name": "号二", "auth_status": "not_logged_in"},
            ]
        },
    )
    assert first.status_code == 200
    assert first.json()["stored"] == 2

    monitor = client.get("/api/product/account-monitor")
    assert monitor.status_code == 200
    body = monitor.json()
    assert body["total"] == 2
    by_account = {row["local_account_id"]: row for row in body["items"]}
    assert by_account["a1"]["auth_status"] == "active"
    assert by_account["a1"]["agent_device_name"] == "pc-1"

    # Second report drops a2 and updates a1 -> mirror should reconcile.
    second = client.post(
        f"/api/agents/{agent_id}/account-snapshots",
        json={"accounts": [{"local_account_id": "a1", "platform": "xhs", "display_name": "号一", "auth_status": "expired"}]},
    )
    assert second.status_code == 200
    assert second.json()["stored"] == 1

    monitor2 = client.get("/api/product/account-monitor").json()
    assert monitor2["total"] == 1
    assert monitor2["items"][0]["auth_status"] == "expired"


def test_report_account_snapshots_unknown_agent_404(db_session):
    client = _client(db_session)
    response = client.post(
        "/api/agents/nonexistent/account-snapshots",
        json={"accounts": []},
    )
    assert response.status_code == 404


def test_account_monitor_forbidden_for_operator(db_session):
    client = _client(db_session, role="operator")
    response = client.get("/api/product/account-monitor")
    assert response.status_code == 403


def test_promote_local_content_creates_content_and_allows_reference_item(db_session):
    client = _client(db_session, role="operator")
    promote = client.post(
        "/api/intelligence/contents/promote",
        json={
            "candidate": {
                "platform": "xhs",
                "platform_content_id": "promote-note-1",
                "canonical_url": "https://www.xiaohongshu.com/explore/promote-note-1",
                "content_type": "image_text",
                "title_or_summary": "本地精选内容",
                "source_surface": "manual_import",
                "discovered_at": "2026-06-21T08:00:00Z",
            },
            "detail": {
                "title": "本地精选内容",
                "body_text": "正文",
                "like_count": 120,
            },
        },
    )
    assert promote.status_code == 200
    body = promote.json()
    assert body["is_new"] is True
    content_id = body["content_id"]

    # Re-promote is idempotent on identity (no duplicate content).
    again = client.post(
        "/api/intelligence/contents/promote",
        json={
            "candidate": {
                "platform": "xhs",
                "platform_content_id": "promote-note-1",
                "content_type": "image_text",
                "source_surface": "manual_import",
                "discovered_at": "2026-06-21T08:05:00Z",
            }
        },
    )
    assert again.status_code == 200
    assert again.json()["content_id"] == content_id
    assert again.json()["is_new"] is False

    item = client.post(
        f"/api/intelligence/contents/{content_id}/reference-library-items",
        json={"library_type": "uncategorized", "selection_sources": ["manual"]},
    )
    assert item.status_code == 200
