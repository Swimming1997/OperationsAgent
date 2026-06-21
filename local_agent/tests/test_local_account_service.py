import asyncio

import pytest

from local_agent_runtime import local_accounts as la_module
from local_agent_runtime.enums import SessionStatus
from local_agent_runtime.local_accounts import LocalAccountService
from local_agent_runtime.storage.account_repository import LocalAccountRepository


def _service(tmp_path, loop):
    repo = LocalAccountRepository(tmp_path / "local.db")
    service = LocalAccountService(
        project_root=tmp_path,
        repository=repo,
        loop=loop,
        observe_timeout_seconds=2.0,
        poll_seconds=0.01,
    )
    return repo, service


def test_create_account_rejects_unsupported_platform(tmp_path):
    loop = asyncio.new_event_loop()
    try:
        _, service = _service(tmp_path, loop)
        with pytest.raises(ValueError):
            service.create_account({"platform": "weibo"})
    finally:
        loop.close()


def test_create_account_accepts_xhs_and_douyin(tmp_path):
    loop = asyncio.new_event_loop()
    try:
        _, service = _service(tmp_path, loop)
        xhs = service.create_account({"platform": "xhs", "display_name": "小红书主号"})
        douyin = service.create_account({"platform": "douyin"})
        assert xhs["platform"] == "xhs"
        assert douyin["platform"] == "douyin"
        listing = service.list_accounts({})
        assert listing["total"] == 2
    finally:
        loop.close()


def test_start_login_launches_browser_and_marks_pending(tmp_path, monkeypatch):
    calls = {}

    def fake_launch(*, project_root, profile_key, cdp_port, url, fresh_profile):
        calls["profile_key"] = profile_key
        calls["cdp_port"] = cdp_port
        calls["url"] = url
        return (tmp_path / profile_key, object())

    monkeypatch.setattr(la_module, "launch_managed_chrome", fake_launch)

    async def scenario():
        loop = asyncio.get_running_loop()
        repo, service = _service(tmp_path, loop)
        account = service.create_account({"platform": "xhs"})
        result = service.start_login(account["id"], {})
        assert result["auth_status"] == "login_pending"
        assert result["cdp_url"].startswith("http://127.0.0.1:")
        assert calls["profile_key"] == account["profile_key"]
        assert "xiaohongshu" in calls["url"]
        # let the scheduled watch task spin up then stop it
        await asyncio.sleep(0.05)
        task = service._login_tasks.get(account["id"])
        if task is not None:
            task.cancel()

    asyncio.run(scenario())


def test_watch_login_marks_active_after_ready(tmp_path):
    async def scenario():
        loop = asyncio.get_running_loop()
        repo, service = _service(tmp_path, loop)
        account = service.create_account({"platform": "xhs"})
        account_id = account["id"]
        repo.mark_login_pending(account_id)

        async def fake_probe(platform, cdp_url):
            return SessionStatus.READY, "昵称", "https://www.xiaohongshu.com/user/x"

        service._probe = fake_probe  # type: ignore[assignment]
        await service._watch_login(account_id, "xhs", "http://127.0.0.1:9300")

        refreshed = repo.get_account(account_id)
        assert refreshed["auth_status"] == "active"
        assert refreshed["platform_nickname"] == "昵称"

    asyncio.run(scenario())


def test_watch_login_marks_failed_on_timeout(tmp_path):
    async def scenario():
        loop = asyncio.get_running_loop()
        repo, service = _service(tmp_path, loop)
        service.observe_timeout_seconds = 0.05
        account = service.create_account({"platform": "douyin"})
        account_id = account["id"]
        repo.mark_login_pending(account_id)

        async def fake_probe(platform, cdp_url):
            return SessionStatus.EXPIRED, None, None

        service._probe = fake_probe  # type: ignore[assignment]
        await service._watch_login(account_id, "douyin", "http://127.0.0.1:9300")

        refreshed = repo.get_account(account_id)
        assert refreshed["auth_status"] == "error"
        assert refreshed["consecutive_failures"] == 1

    asyncio.run(scenario())
