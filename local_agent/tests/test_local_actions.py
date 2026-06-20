from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import local_agent_runtime.local_actions as actions_module

from local_agent_runtime.connectors.xhs.comment_probe import XhsCommentFetchResult
from local_agent_runtime.contracts import (
    CommentSnapshotInput,
    FeedCandidateIngestionRequest,
    FeedCandidateInput,
)
from local_agent_runtime.enums import ContentType, Platform, SessionStatus, SourceSurface
from local_agent_runtime.local_actions import CentralWorkspaceSession, LocalContentActionService
from local_agent_runtime.runtime import AgentRuntimeConfig
from local_agent_runtime.storage import LocalIntelligenceRepository


class FakeSession:
    status = SessionStatus.READY
    message = None
    page = object()

    async def close(self):
        return None


class FakeProvider:
    async def acquire(self, *, session_meta):
        return FakeSession()


class FakeRegistry:
    def create(self, platform):
        assert platform == "xhs"
        return FakeProvider()


class FakeCentralSession:
    def __init__(self, *, fail=False):
        self.fail = fail
        self.logged_in = True

    async def login(self, *, username, password):
        self.logged_in = True
        return self.status()

    def logout(self):
        self.logged_in = False

    def status(self):
        return {"authenticated": self.logged_in, "user": {"username": "operator"} if self.logged_in else None}

    async def create_reference_library_item(self, *, central_content_id, payload):
        if self.fail:
            raise RuntimeError("central unavailable")
        assert central_content_id == "central-1"
        assert payload["matched_keywords"] == ["多少钱", "怎么买"]
        return {"id": "reference-1", "content_id": central_content_id, **payload}


class FakeHttpResponse:
    def __init__(self, payload, *, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise actions_module.httpx.HTTPStatusError(
                "request failed",
                request=actions_module.httpx.Request("POST", "http://central.test"),
                response=actions_module.httpx.Response(self.status_code),
            )

    def json(self):
        return self._payload


class FakeAsyncClient:
    response = None

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    async def post(self, *args, **kwargs):
        return self.response


def _seed(repository: LocalIntelligenceRepository) -> int:
    repository.upsert_feed_candidates(
        FeedCandidateIngestionRequest(
            job_id="seed",
            candidates=[
                FeedCandidateInput(
                    platform=Platform.XHS,
                    platform_content_id="note-1",
                    canonical_url="https://www.xiaohongshu.com/explore/note-1",
                    content_type=ContentType.IMAGE_TEXT,
                    title_or_summary="获客内容",
                    source_surface=SourceSurface.SEARCH,
                    discovered_at=datetime.now(timezone.utc),
                    platform_context={
                        "note_id": "note-1",
                        "xsec_token": "token",
                        "xsec_source": "pc_search",
                        "api_comment_ready": True,
                    },
                )
            ],
        )
    )
    repository.apply_central_content_mappings(
        [{"platform": "xhs", "platform_content_id": "note-1", "content_id": "central-1"}]
    )
    return repository.get_content(platform="xhs", platform_content_id="note-1")["id"]


def test_acquisition_check_fetches_comments_and_persists_hits(tmp_path, monkeypatch):
    class FakeProbe:
        async def fetch_comments_result(self, page, **kwargs):
            return XhsCommentFetchResult(
                comments=[
                    CommentSnapshotInput(
                        platform_comment_id="c-1",
                        body_text="这个怎么买，多少钱？",
                        author_name="咨询者",
                    ),
                    CommentSnapshotInput(
                        platform_comment_id="c-2",
                        body_text="普通评价",
                    ),
                ],
                surface_status="ok",
            )

    monkeypatch.setattr(actions_module, "default_session_registry", FakeRegistry())
    monkeypatch.setattr(actions_module, "XhsCommentProbe", FakeProbe)
    repository = LocalIntelligenceRepository(tmp_path / "local.db")
    content_id = _seed(repository)
    service = LocalContentActionService(
        config=AgentRuntimeConfig(cdp_url="http://127.0.0.1:9222"),
        repository=repository,
        central_session=FakeCentralSession(),
    )
    task_id = repository.create_collect_task(
        task_type="acquisition_check",
        target=str(content_id),
        params={},
    )

    asyncio.run(
        service._check_acquisition(
            task_id=task_id,
            content=repository.get_content_detail(content_id),
            keywords=["怎么买", "多少钱"],
            max_comments=30,
        )
    )

    detail = repository.get_content_detail(content_id)
    assert detail["acquisition_hit_count"] == 1
    assert {item["matched_keyword"] for item in detail["comment_hits"]} == {"怎么买", "多少钱"}
    assert repository.get_collect_task(task_id)["status"] == "success"


def test_material_export_syncs_and_keeps_matched_keywords(tmp_path):
    repository = LocalIntelligenceRepository(tmp_path / "local.db")
    content_id = _seed(repository)
    repository.upsert_local_comment_hits(
        content_id=content_id,
        comments=[
            CommentSnapshotInput(
                platform_comment_id="c-1",
                body_text="怎么买，多少钱",
            )
        ],
        keywords=["怎么买", "多少钱"],
    )
    service = LocalContentActionService(
        config=AgentRuntimeConfig(),
        repository=repository,
        central_session=FakeCentralSession(),
    )

    result = asyncio.run(
        service.add_to_material_library(
            content_id=content_id,
            payload={
                "library_type": "lead",
                "rating": "good",
                "material_tags": ["评论洞察"],
                "note": "高转化信号",
            },
        )
    )

    assert result["status"] == "synced"
    export = repository.get_material_export(content_id)
    assert export["status"] == "synced"
    assert export["central_reference_item_id"] == "reference-1"


def test_material_export_failure_preserves_pending_intent(tmp_path):
    repository = LocalIntelligenceRepository(tmp_path / "local.db")
    content_id = _seed(repository)
    service = LocalContentActionService(
        config=AgentRuntimeConfig(),
        repository=repository,
        central_session=FakeCentralSession(fail=True),
    )

    result = asyncio.run(
        service.add_to_material_library(
            content_id=content_id,
            payload={"library_type": "uncategorized", "material_tags": []},
        )
    )

    assert result["status"] == "failed"
    export = repository.get_material_export(content_id)
    assert export["status"] == "failed"
    assert "central unavailable" in export["last_error"]


def test_central_login_saves_successful_server_url_locally(tmp_path):
    repository = LocalIntelligenceRepository(tmp_path / "local.db")
    session = FakeCentralSession()
    service = LocalContentActionService(
        config=AgentRuntimeConfig(center_base_url="http://127.0.0.1:8000"),
        repository=repository,
        central_session=session,
    )

    result = asyncio.run(
        service.login_central(
            {
                "center_url": "https://operations.example.com/",
                "username": "operator",
                "password": "secret",
            }
        )
    )

    assert result["center_url"] == "https://operations.example.com"
    assert repository.get_setting("central_server_url") == "https://operations.example.com"


def test_central_login_rejects_invalid_server_url_without_saving(tmp_path):
    repository = LocalIntelligenceRepository(tmp_path / "local.db")
    service = LocalContentActionService(
        config=AgentRuntimeConfig(center_base_url="http://127.0.0.1:8000"),
        repository=repository,
        central_session=FakeCentralSession(),
    )

    try:
        asyncio.run(
            service.login_central(
                {
                    "center_url": "javascript:alert(1)",
                    "username": "operator",
                    "password": "secret",
                }
            )
        )
    except ValueError as exc:
        assert "http:// or https://" in str(exc)
    else:
        raise AssertionError("expected invalid central URL to be rejected")

    assert repository.get_setting("central_server_url") is None


def test_central_workspace_session_accepts_operator_and_keeps_token_in_memory(monkeypatch):
    FakeAsyncClient.response = FakeHttpResponse(
        {
            "access_token": "token-1",
            "user": {
                "username": "operator",
                "display_name": "运营",
                "roles": ["operator"],
            },
        }
    )
    monkeypatch.setattr(actions_module.httpx, "AsyncClient", FakeAsyncClient)
    session = CentralWorkspaceSession(base_url="http://central.test")

    status = asyncio.run(session.login(username="operator", password="secret"))

    assert status["authenticated"] is True
    assert session.access_token == "token-1"
    session.logout()
    assert session.status()["authenticated"] is False


def test_central_workspace_session_rejects_sales_role(monkeypatch):
    FakeAsyncClient.response = FakeHttpResponse(
        {
            "access_token": "token-sales",
            "user": {"username": "sales", "roles": ["sales"]},
        }
    )
    monkeypatch.setattr(actions_module.httpx, "AsyncClient", FakeAsyncClient)
    session = CentralWorkspaceSession(base_url="http://central.test")

    try:
        asyncio.run(session.login(username="sales", password="secret"))
    except PermissionError as exc:
        assert "cannot write reference library" in str(exc)
    else:
        raise AssertionError("expected sales login to be rejected for material writes")
