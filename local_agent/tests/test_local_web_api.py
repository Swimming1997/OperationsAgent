from __future__ import annotations

import asyncio
import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from local_agent_runtime.contracts import FeedCandidateIngestionRequest, FeedCandidateInput
from local_agent_runtime.enums import ContentType, Platform, SourceSurface
from local_agent_runtime.local_bridge import LocalBridgeConfig, LocalBridgeServer, LocalBridgeService
from local_agent_runtime.local_bridge_http import fetch_allowed_image
from local_agent_runtime.runtime import AgentRuntimeConfig
from local_agent_runtime.storage import LocalIntelligenceRepository


def _request(url: str, *, method: str = "GET", payload=None, headers=None):
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = Request(
        url,
        data=data,
        method=method,
        headers={"Content-Type": "application/json", **(headers or {})},
    )
    try:
        response = urlopen(request, timeout=3)
    except HTTPError as exc:
        response = exc
    with response:
        content_type = response.headers.get("Content-Type", "")
        body = response.read()
        if "application/json" in content_type:
            return response.status, json.loads(body.decode("utf-8"))
        return response.status, body.decode("utf-8")


def _seed(repository: LocalIntelligenceRepository):
    repository.upsert_feed_candidates(
        FeedCandidateIngestionRequest(
            job_id="job-web",
            candidates=[
                FeedCandidateInput(
                    platform=Platform.XHS,
                    platform_content_id="web-note-1",
                    content_type=ContentType.IMAGE_TEXT,
                    title_or_summary="网页测试内容",
                    source_surface=SourceSurface.SEARCH,
                    discovered_at=datetime.now(timezone.utc),
                    raw_payload={"search_keyword": "网页"},
                )
            ],
        )
    )


def test_local_web_serves_ui_and_content_api(tmp_path):
    repository = LocalIntelligenceRepository(tmp_path / "local.db")
    _seed(repository)
    loop = asyncio.new_event_loop()
    thread = threading.Thread(target=loop.run_forever, daemon=True)
    thread.start()
    service = LocalBridgeService(
        config=AgentRuntimeConfig(project_root=str(tmp_path)),
        loop=loop,
        repository=repository,
    )
    server = LocalBridgeServer(
        bridge_config=LocalBridgeConfig(host="127.0.0.1", port=0),
        service=service,
    )
    try:
        server.start()
        port = server._server.server_address[1]
        status, html = _request(f"http://127.0.0.1:{port}/")
        assert status == 200
        assert "运营情报工作台" in html

        status, listing = _request(f"http://127.0.0.1:{port}/api/local/contents?limit=1")
        assert status == 200
        assert listing["total"] == 1
        content_id = listing["items"][0]["id"]

        status, detail = _request(f"http://127.0.0.1:{port}/api/local/contents/{content_id}")
        assert status == 200
        assert detail["title"] == "网页测试内容"
    finally:
        server.stop()
        loop.call_soon_threadsafe(loop.stop)
        thread.join(timeout=2)
        loop.close()


def test_local_media_proxy_rejects_non_xhs_hosts():
    with pytest.raises(ValueError, match="unsupported image host"):
        fetch_allowed_image("http://127.0.0.1/private.png")


def test_local_web_search_endpoint_returns_async_task(tmp_path, monkeypatch):
    repository = LocalIntelligenceRepository(tmp_path / "local.db")
    loop = asyncio.new_event_loop()
    thread = threading.Thread(target=loop.run_forever, daemon=True)
    thread.start()
    service = LocalBridgeService(
        config=AgentRuntimeConfig(project_root=str(tmp_path), cdp_url="http://127.0.0.1:9222"),
        loop=loop,
        repository=repository,
    )
    monkeypatch.setattr(service.local_collection, "submit", lambda **kwargs: {"task_id": 7, "status": "queued"})
    server = LocalBridgeServer(
        bridge_config=LocalBridgeConfig(host="127.0.0.1", port=0),
        service=service,
    )
    try:
        server.start()
        port = server._server.server_address[1]
        status, payload = _request(
            f"http://127.0.0.1:{port}/api/local/search",
            method="POST",
            payload={"keyword": "考研", "max_items": 20},
        )
        assert status == 202
        assert payload == {"task_id": 7, "status": "queued"}
    finally:
        server.stop()
        loop.call_soon_threadsafe(loop.stop)
        thread.join(timeout=2)
        loop.close()


def test_local_web_batch_content_status(tmp_path):
    repository = LocalIntelligenceRepository(tmp_path / "local.db")
    _seed(repository)
    content_id = repository.list_contents()["items"][0]["id"]
    loop = asyncio.new_event_loop()
    thread = threading.Thread(target=loop.run_forever, daemon=True)
    thread.start()
    service = LocalBridgeService(
        config=AgentRuntimeConfig(project_root=str(tmp_path)),
        loop=loop,
        repository=repository,
    )
    server = LocalBridgeServer(
        bridge_config=LocalBridgeConfig(host="127.0.0.1", port=0),
        service=service,
    )
    try:
        server.start()
        port = server._server.server_address[1]
        status, payload = _request(
            f"http://127.0.0.1:{port}/api/local/contents/batch-status",
            method="POST",
            payload={"content_ids": [content_id], "status": "discarded"},
        )
        assert status == 200
        assert payload["updated"] == 1
        assert repository.get_content_detail(content_id)["processing_status"] == "discarded"
    finally:
        server.stop()
        loop.call_soon_threadsafe(loop.stop)
        thread.join(timeout=2)
        loop.close()


def test_local_web_task_create_and_actions(tmp_path, monkeypatch):
    repository = LocalIntelligenceRepository(tmp_path / "local.db")
    loop = asyncio.new_event_loop()
    thread = threading.Thread(target=loop.run_forever, daemon=True)
    thread.start()
    service = LocalBridgeService(
        config=AgentRuntimeConfig(project_root=str(tmp_path), cdp_url="http://127.0.0.1:9222"),
        loop=loop,
        repository=repository,
    )

    def fake_submit(*, loop, payload):
        task_id = repository.create_collect_task(
            task_type=payload["task_type"],
            target=payload["target"],
            params={"max_items": 20},
            schedule_seconds=payload["schedule_seconds"],
        )
        return {"task_id": task_id, "status": "queued", "task_type": payload["task_type"]}

    monkeypatch.setattr(service.local_collection, "submit", fake_submit)
    server = LocalBridgeServer(
        bridge_config=LocalBridgeConfig(host="127.0.0.1", port=0),
        service=service,
    )
    try:
        server.start()
        port = server._server.server_address[1]
        status, created = _request(
            f"http://127.0.0.1:{port}/api/local/tasks",
            method="POST",
            payload={
                "task_type": "creator_monitor",
                "target": "creator-1",
                "schedule_seconds": 3600,
            },
        )
        assert status == 202
        task_id = created["task_id"]

        status, paused = _request(
            f"http://127.0.0.1:{port}/api/local/tasks/{task_id}/pause",
            method="POST",
            payload={},
        )
        assert status == 200
        assert paused["status"] == "paused"

        status, resumed = _request(
            f"http://127.0.0.1:{port}/api/local/tasks/{task_id}/resume",
            method="POST",
            payload={},
        )
        assert status == 200
        assert resumed["status"] == "active"
    finally:
        server.stop()
        loop.call_soon_threadsafe(loop.stop)
        thread.join(timeout=2)
        loop.close()


def test_local_web_acquisition_material_and_central_session_routes(tmp_path):
    class FakeActions:
        def central_status(self):
            return {"authenticated": False, "user": None, "center_url": "https://central.example.com"}

        async def login_central(self, payload):
            return {
                "authenticated": True,
                "user": {"username": payload["username"]},
                "center_url": payload["center_url"],
                "retry": {"synced": 0, "failed": 0},
            }

        def logout_central(self):
            return {"authenticated": False, "user": None}

        def submit_acquisition_check(self, *, loop, content_id, payload):
            return {"task_id": 9, "content_id": content_id, "status": "queued"}

        def submit_detail_fetch(self, *, loop, content_id):
            return {"task_id": 10, "content_id": content_id, "status": "queued"}

        async def add_to_material_library(self, *, content_id, payload):
            return {"content_id": content_id, "status": "synced", "reference_library_item": {"id": "ref-1"}}

        async def retry_pending_materials(self):
            return {"synced": 1, "failed": 0}

    repository = LocalIntelligenceRepository(tmp_path / "local.db")
    _seed(repository)
    content_id = repository.list_contents()["items"][0]["id"]
    loop = asyncio.new_event_loop()
    thread = threading.Thread(target=loop.run_forever, daemon=True)
    thread.start()
    service = LocalBridgeService(
        config=AgentRuntimeConfig(project_root=str(tmp_path)),
        loop=loop,
        repository=repository,
        action_service=FakeActions(),
    )
    server = LocalBridgeServer(
        bridge_config=LocalBridgeConfig(host="127.0.0.1", port=0),
        service=service,
    )
    try:
        server.start()
        port = server._server.server_address[1]
        base = f"http://127.0.0.1:{port}"

        session_status = _request(f"{base}/api/local/central-session")[1]
        assert session_status["authenticated"] is False
        assert session_status["center_url"] == "https://central.example.com"
        login = _request(
            f"{base}/api/local/central-session/login",
            method="POST",
            payload={
                "center_url": "https://operations.example.com",
                "username": "operator",
                "password": "secret",
            },
        )[1]
        assert login["authenticated"] is True
        assert login["center_url"] == "https://operations.example.com"

        acquisition = _request(
            f"{base}/api/local/contents/{content_id}/acquisition-check",
            method="POST",
            payload={"max_comments": 30},
        )[1]
        assert acquisition["task_id"] == 9

        detail_fetch = _request(
            f"{base}/api/local/contents/{content_id}/detail-fetch",
            method="POST",
            payload={},
        )[1]
        assert detail_fetch["task_id"] == 10

        material_status, material = _request(
            f"{base}/api/local/contents/{content_id}/material",
            method="POST",
            payload={"library_type": "lead", "material_tags": ["评论洞察"]},
        )
        assert material_status == 200
        assert material["status"] == "synced"

        retry = _request(
            f"{base}/api/local/materials/retry",
            method="POST",
            payload={},
        )[1]
        assert retry == {"synced": 1, "failed": 0}
    finally:
        server.stop()
        loop.call_soon_threadsafe(loop.stop)
        thread.join(timeout=2)
        loop.close()


def test_local_web_requires_bridge_token_and_rejects_untrusted_cors(tmp_path):
    repository = LocalIntelligenceRepository(tmp_path / "local.db")
    loop = asyncio.new_event_loop()
    thread = threading.Thread(target=loop.run_forever, daemon=True)
    thread.start()
    config = AgentRuntimeConfig(
        project_root=str(tmp_path),
        local_bridge_token="bridge-secret",
    )
    server = LocalBridgeServer(
        bridge_config=LocalBridgeConfig(host="127.0.0.1", port=0, token="bridge-secret"),
        service=LocalBridgeService(config=config, loop=loop, repository=repository),
    )
    try:
        server.start()
        port = server._server.server_address[1]
        base = f"http://127.0.0.1:{port}"
        assert _request(f"{base}/api/local/contents")[0] == 401
        session_request = Request(
            f"{base}/bridge/session",
            data=b"",
            method="POST",
            headers={"Authorization": "Bearer bridge-secret"},
        )
        with urlopen(session_request, timeout=3) as response:
            assert response.status == 204
            cookie = response.headers["Set-Cookie"].split(";", 1)[0]
            assert "HttpOnly" in response.headers["Set-Cookie"]
            assert "SameSite=Strict" in response.headers["Set-Cookie"]
        status, payload = _request(
            f"{base}/api/local/contents",
            headers={"Cookie": cookie},
        )
        assert status == 200
        assert payload["total"] == 0
        status, payload = _request(
            f"{base}/api/local/contents",
            headers={"Authorization": "Bearer bridge-secret"},
        )
        assert status == 200
        assert payload["total"] == 0
        status, _payload = _request(
            f"{base}/api/local/contents",
            method="OPTIONS",
            headers={
                "Origin": "https://attacker.example",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert status == 403
    finally:
        server.stop()
        loop.call_soon_threadsafe(loop.stop)
        thread.join(timeout=2)
        loop.close()


def test_local_workspace_assets_keep_token_in_memory_and_hide_nonempty_state():
    web_root = Path(__file__).resolve().parents[1] / "local_agent_runtime" / "web"
    app_js = (web_root / "app.js").read_text(encoding="utf-8")
    styles = (web_root / "styles.css").read_text(encoding="utf-8")

    assert 'fragment.get("token")' in app_js
    assert 'fetch("/bridge/session"' in app_js
    assert 'el("centralServerUrl").value' in app_js
    assert "window.history.replaceState" in app_js
    assert "localStorage" not in app_js
    assert "sessionStorage" not in app_js
    assert ".empty-state[hidden] { display: none; }" in styles
