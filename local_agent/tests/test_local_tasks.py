from __future__ import annotations

import asyncio
import threading
import time
from datetime import datetime, timezone

import local_agent_runtime.local_tasks as tasks_module

from local_agent_runtime.connectors.xhs.creator import (
    XhsCreatorFetchResult,
    XhsCreatorItem,
    normalize_xhs_creator_profile,
)
from local_agent_runtime.contracts import FeedCandidateInput
from local_agent_runtime.enums import ContentType, Platform, SessionStatus, SourceSurface
from local_agent_runtime.local_tasks import LocalCollectionService
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
        assert session_meta["cdp_url"] == "http://127.0.0.1:9222"
        return FakeSession()


class FakeRegistry:
    def create(self, platform):
        assert platform == "xhs"
        return FakeProvider()


def test_local_search_executes_and_updates_task(tmp_path, monkeypatch):
    class FakeProbe:
        def __init__(self, **kwargs):
            assert kwargs["keywords"] == ["考研"]

        async def collect(self, page):
            return [
                FeedCandidateInput(
                    platform=Platform.XHS,
                    platform_content_id="search-1",
                    content_type=ContentType.IMAGE_TEXT,
                    title_or_summary="考研复习计划",
                    source_surface=SourceSurface.SEARCH,
                    discovered_at=datetime.now(timezone.utc),
                    raw_payload={},
                )
            ], {"total_items_seen": 1}

    monkeypatch.setattr(tasks_module, "default_session_registry", FakeRegistry())
    monkeypatch.setattr(tasks_module, "XhsSearchProbe", FakeProbe)
    repository = LocalIntelligenceRepository(tmp_path / "local.db")
    service = LocalCollectionService(
        config=AgentRuntimeConfig(cdp_url="http://127.0.0.1:9222"),
        repository=repository,
    )
    task_id = repository.create_collect_task(
        task_type="search",
        target="考研",
        params={
            "account_id": None,
            "max_items": 20,
            "sort": "comprehensive",
            "content_form": "all",
            "publish_time": "all",
        },
    )

    asyncio.run(service._execute(repository.get_collect_task(task_id)))

    task = repository.get_collect_task(task_id)
    assert task["status"] == "success"
    assert task["latest_run"]["item_count"] == 1
    assert repository.list_contents(keyword="考研")["total"] == 1


def test_creator_monitor_tracks_new_content_and_mark_viewed(tmp_path, monkeypatch):
    async def fake_fetch(self, page, **kwargs):
        return XhsCreatorFetchResult(
            creator_platform_id="creator-1",
            creator_display_name="对标博主",
            items=[
                XhsCreatorItem(
                    platform_content_id="creator-note-1",
                    canonical_url="https://example.com/note",
                    title_or_summary="新内容",
                    cover_url=None,
                    publish_time=None,
                    xsec_token="token",
                    xsec_source="pc_feed",
                    raw_payload={},
                )
            ],
            raw_payload={},
            profile={
                "nickname": "对标博主",
                "avatar_url": "https://img.example/avatar.jpg",
                "fans_count": 12000,
                "total_liked_collected": 45000,
                "works_count": 88,
                "verify_type": "教育博主",
                "signature": "认真分享",
                "ip_location": "上海",
                "raw": {},
            },
        )

    monkeypatch.setattr(tasks_module, "default_session_registry", FakeRegistry())
    monkeypatch.setattr(tasks_module.XhsCreatorConnector, "fetch_latest", fake_fetch)
    repository = LocalIntelligenceRepository(tmp_path / "local.db")
    service = LocalCollectionService(
        config=AgentRuntimeConfig(cdp_url="http://127.0.0.1:9222"),
        repository=repository,
    )
    target = "https://www.xiaohongshu.com/user/profile/creator-1"
    task_id = repository.create_collect_task(
        task_type="creator_monitor",
        target=target,
        params={
            "account_id": None,
            "max_items": 20,
            "creator_profile_url": target,
            "creator_platform_id": None,
        },
        schedule_seconds=3600,
    )

    asyncio.run(service._execute(repository.get_collect_task(task_id)))

    task = repository.get_collect_task(task_id)
    assert task["status"] == "active"
    assert task["new_content_count"] == 1
    with repository.connection() as connection:
        creator = connection.execute(
            "SELECT * FROM creator WHERE platform_user_id = 'creator-1'"
        ).fetchone()
    assert creator["fans_count"] == 12000
    assert creator["total_liked_collected"] == 45000
    assert creator["works_count"] == 88
    assert creator["ip_location"] == "上海"
    assert repository.mark_collect_task_viewed(task_id) is True
    assert repository.get_collect_task(task_id)["new_content_count"] == 0


def test_recommend_task_uses_homefeed_probe(tmp_path, monkeypatch):
    class FakeFeedProbe:
        def __init__(self, *, target_count):
            assert target_count == 15

        async def collect(self, page):
            return [], {"items_seen": 0}

    monkeypatch.setattr(tasks_module, "default_session_registry", FakeRegistry())
    monkeypatch.setattr(tasks_module, "XhsHomeFeedProbe", FakeFeedProbe)
    repository = LocalIntelligenceRepository(tmp_path / "local.db")
    service = LocalCollectionService(
        config=AgentRuntimeConfig(cdp_url="http://127.0.0.1:9222"),
        repository=repository,
    )
    task_id = repository.create_collect_task(
        task_type="recommend",
        target="",
        params={"account_id": None, "max_items": 15},
    )

    asyncio.run(service._execute(repository.get_collect_task(task_id)))

    assert repository.get_collect_task(task_id)["status"] == "success"


def test_scheduled_task_due_pause_and_resume(tmp_path):
    repository = LocalIntelligenceRepository(tmp_path / "local.db")
    task_id = repository.create_collect_task(
        task_type="recommend",
        target="",
        params={"max_items": 10},
        schedule_seconds=60,
    )
    with repository.connection() as connection:
        connection.execute(
            "UPDATE collect_task SET created_at = ? WHERE id = ?",
            ("2020-01-01T00:00:00+00:00", task_id),
        )
        connection.commit()

    assert [item["id"] for item in repository.list_due_collect_tasks()] == [task_id]
    assert repository.pause_collect_task(task_id) is True
    assert repository.list_due_collect_tasks() == []
    assert repository.resume_collect_task(task_id) is True
    assert [item["id"] for item in repository.list_due_collect_tasks()] == [task_id]


def test_scheduled_task_stays_active_after_failure(tmp_path):
    repository = LocalIntelligenceRepository(tmp_path / "local.db")
    task_id = repository.create_collect_task(
        task_type="creator_monitor",
        target="creator-1",
        params={},
        schedule_seconds=60,
    )

    repository.mark_collect_task_running(task_id)
    repository.finish_collect_task(task_id, success=False)

    assert repository.get_collect_task(task_id)["status"] == "active"


def test_running_task_pause_cancels_execution_and_marks_run_paused(tmp_path, monkeypatch):
    started = threading.Event()

    class BlockingProbe:
        def __init__(self, **kwargs):
            pass

        async def collect(self, page):
            started.set()
            await asyncio.Event().wait()

    monkeypatch.setattr(tasks_module, "default_session_registry", FakeRegistry())
    monkeypatch.setattr(tasks_module, "XhsSearchProbe", BlockingProbe)
    repository = LocalIntelligenceRepository(tmp_path / "local.db")
    service = LocalCollectionService(
        config=AgentRuntimeConfig(cdp_url="http://127.0.0.1:9222"),
        repository=repository,
    )
    task_id = repository.create_collect_task(
        task_type="search",
        target="暂停测试",
        params={
            "account_id": None,
            "max_items": 20,
            "sort": "comprehensive",
            "content_form": "all",
            "publish_time": "all",
        },
    )
    loop = asyncio.new_event_loop()
    thread = threading.Thread(target=loop.run_forever, daemon=True)
    thread.start()
    try:
        assert service.run_task(loop=loop, task_id=task_id) is True
        assert started.wait(timeout=2)
        assert service.pause_task(task_id=task_id) is True
        deadline = time.time() + 2
        while task_id in service._running_task_ids and time.time() < deadline:
            time.sleep(0.02)
        asyncio.run_coroutine_threadsafe(asyncio.sleep(0.1), loop).result(timeout=1)
        task = repository.get_collect_task(task_id)
        assert task["status"] == "paused"
        assert task["latest_run"]["status"] == "paused"
    finally:
        loop.call_soon_threadsafe(loop.stop)
        thread.join(timeout=2)
        loop.close()


def test_cancelled_task_is_failed_and_can_be_restarted(tmp_path):
    repository = LocalIntelligenceRepository(tmp_path / "local.db")
    task_id = repository.create_collect_task(
        task_type="search",
        target="取消测试",
        params={},
    )
    repository.mark_collect_task_running(task_id)
    repository.start_local_collect_run(
        task_id=task_id,
        run_id="cancel-run",
        job_type="search",
    )

    assert repository.interrupt_collect_task(
        task_id,
        status="failed",
        reason="任务已取消",
    )
    task = repository.get_collect_task(task_id)
    assert task["status"] == "failed"
    assert task["latest_run"]["status"] == "failed"
    assert repository.resume_collect_task(task_id) is True
    assert repository.get_collect_task(task_id)["status"] == "queued"


def test_normalize_creator_profile_from_initial_state_shape():
    profile = normalize_xhs_creator_profile(
        {
            "basicInfo": {
                "nickname": "画像作者",
                "images": "https://img.example/avatar.jpg",
                "desc": "简介",
                "ipLocation": "广东",
                "noteCount": "128",
            },
            "interactions": [
                {"type": "fans", "count": "1.2万"},
                {"type": "interaction", "count": "5.6万"},
            ],
            "tags": [{"tagType": "profession", "name": "摄影博主"}],
        }
    )

    assert profile["nickname"] == "画像作者"
    assert profile["fans_count"] == 12000
    assert profile["total_liked_collected"] == 56000
    assert profile["works_count"] == 128
    assert profile["verify_type"] == "摄影博主"
