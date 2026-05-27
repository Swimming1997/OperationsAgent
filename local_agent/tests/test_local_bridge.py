from __future__ import annotations

import asyncio
from pathlib import Path

from local_agent_runtime.local_bridge import LocalBridgeService
from local_agent_runtime.runtime import AgentRuntimeConfig


def test_local_bridge_probe_uses_account_specific_cdp_url(monkeypatch):
    async def fake_probe(_cdp_url: str):
        return {
            "status": "ready",
            "message": "ok",
            "platform_nickname": "nick",
            "platform_home_url": "https://www.xiaohongshu.com/explore",
            "cdp_url": "http://127.0.0.1:9222",
        }

    class FakeExecutor:
        async def probe_session(self, cdp_url: str):
            return await fake_probe(cdp_url)

    config = AgentRuntimeConfig(
        account_sessions={"account-1": {"cdp_url": "http://127.0.0.1:9222"}},
        project_root=str(Path.cwd()),
    )
    service = LocalBridgeService(config=config, loop=asyncio.new_event_loop())
    try:
        monkeypatch.setattr(service, "_probe_executor", FakeExecutor())
        monkeypatch.setattr(service, "_run_async", lambda coro: asyncio.run(coro))
        result = service.probe_account_session("account-1")
        assert result["status"] == "ready"
        assert result["account_id"] == "account-1"
    finally:
        service.loop.close()


def test_local_bridge_probe_prefers_runtime_cdp_over_default_config(monkeypatch):
    seen: list[str] = []

    class FakeExecutor:
        async def probe_session(self, cdp_url: str):
            seen.append(cdp_url)
            return {"status": "ready", "message": "ok", "platform_nickname": None, "platform_home_url": None, "cdp_url": cdp_url}

    config = AgentRuntimeConfig(cdp_url="http://127.0.0.1:9222", project_root=str(Path.cwd()))
    service = LocalBridgeService(config=config, loop=asyncio.new_event_loop())
    try:
        monkeypatch.setattr(service, "_probe_executor", FakeExecutor())
        monkeypatch.setattr(service, "_run_async", lambda coro: asyncio.run(coro))
        service.remember_account_cdp("account-1", "http://127.0.0.1:9301")
        service.probe_account_session("account-1")
        assert seen == ["http://127.0.0.1:9301"]
        service.probe_account_session("account-1", cdp_port=9400)
        assert seen[-1] == "http://127.0.0.1:9400"
    finally:
        service.loop.close()


def test_local_bridge_requires_token_when_configured():
    config = AgentRuntimeConfig(local_bridge_token="demo-token")
    service = LocalBridgeService(config=config, loop=asyncio.new_event_loop())
    try:
        assert service.require_token("demo-token") is True
        assert service.require_token(None) is False
        assert service.require_token("wrong") is False
    finally:
        service.loop.close()
