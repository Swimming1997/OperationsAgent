from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any, Callable

from local_agent_runtime.chrome_launcher import launch_managed_chrome
from local_agent_runtime.connectors.douyin import field as dy_field
from local_agent_runtime.enums import SessionStatus
from local_agent_runtime.sessions.douyin_browser_session import DouyinBrowserSessionProvider
from local_agent_runtime.sessions.xhs_browser_session import XhsBrowserSessionProvider
from local_agent_runtime.storage.account_repository import LocalAccountRepository


logger = logging.getLogger("local_agent")

SUPPORTED_PLATFORMS = {"xhs", "douyin"}
_LOGIN_LANDING = {
    "xhs": "https://www.xiaohongshu.com/explore",
    "douyin": dy_field.HOME_URL,
}


class LocalAccountService:
    """Local-first platform account management + login orchestration.

    The local machine owns the accounts. Adding an account, opening the
    browser to log in, probing the login state and persisting it all happen
    here, without the central server orchestrating a login session. Central is
    only fed read-only monitoring snapshots later (F5).
    """

    def __init__(
        self,
        *,
        project_root: Path,
        repository: LocalAccountRepository,
        loop: asyncio.AbstractEventLoop,
        on_cdp_resolved: Callable[[str, str], None] | None = None,
        observe_timeout_seconds: float = 600.0,
        poll_seconds: float = 8.0,
    ):
        self.project_root = Path(project_root)
        self.repository = repository
        self.loop = loop
        self.on_cdp_resolved = on_cdp_resolved
        self.observe_timeout_seconds = observe_timeout_seconds
        self.poll_seconds = poll_seconds
        self._login_tasks: dict[str, asyncio.Task] = {}

    # ---- CRUD --------------------------------------------------------------

    def list_accounts(self, query: dict[str, list[str]] | None = None) -> dict[str, Any]:
        platform = None
        if query:
            platform = (query.get("platform") or [None])[0]
        accounts = self.repository.list_accounts(platform=platform)
        return {"items": accounts, "total": len(accounts)}

    def get_account(self, account_id: str) -> dict[str, Any] | None:
        return self.repository.get_account(account_id)

    def create_account(self, payload: dict[str, Any]) -> dict[str, Any]:
        platform = str(payload.get("platform") or "").strip().lower()
        if platform not in SUPPORTED_PLATFORMS:
            raise ValueError(f"unsupported platform: {platform or '(empty)'}")
        return self.repository.create_account(
            platform=platform,
            display_name=str(payload.get("display_name") or "").strip(),
            account_role=str(payload.get("account_role") or "intelligence_collector"),
            metadata=payload.get("metadata") if isinstance(payload.get("metadata"), dict) else None,
        )

    def update_account(self, account_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self.repository.update_account(
            account_id,
            display_name=payload.get("display_name"),
            status=payload.get("status"),
            account_role=payload.get("account_role"),
        )

    def delete_account(self, account_id: str) -> dict[str, Any]:
        deleted = self.repository.delete_account(account_id)
        if not deleted:
            raise ValueError("account not found")
        return {"account_id": account_id, "deleted": True}

    # ---- login orchestration ----------------------------------------------

    def start_login(self, account_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        account = self.repository.get_account(account_id)
        if account is None:
            raise ValueError("account not found")
        platform = str(account["platform"])
        port = self.repository.allocate_cdp_port(account_id)
        landing = _LOGIN_LANDING.get(platform, _LOGIN_LANDING["xhs"])
        fresh_profile = bool((payload or {}).get("fresh_profile"))
        launch_managed_chrome(
            project_root=self.project_root,
            profile_key=account["profile_key"],
            cdp_port=port,
            url=landing,
            fresh_profile=fresh_profile,
        )
        cdp_url = f"http://127.0.0.1:{port}"
        if self.on_cdp_resolved is not None:
            try:
                self.on_cdp_resolved(account_id, cdp_url)
            except Exception:  # pragma: no cover - best effort cache
                pass
        updated = self.repository.mark_login_pending(account_id)
        self._schedule_watch(account_id, platform, cdp_url)
        return {**updated, "cdp_url": cdp_url, "login_landing_url": landing}

    def _schedule_watch(self, account_id: str, platform: str, cdp_url: str) -> None:
        existing = self._login_tasks.get(account_id)
        if existing is not None and not existing.done():
            existing.cancel()

        def _runner() -> None:
            task = self.loop.create_task(self._watch_login(account_id, platform, cdp_url))
            self._login_tasks[account_id] = task

        self.loop.call_soon_threadsafe(_runner)

    async def _watch_login(self, account_id: str, platform: str, cdp_url: str) -> None:
        ready_streak = 0
        deadline = self.loop.time() + self.observe_timeout_seconds
        try:
            while self.loop.time() < deadline:
                status, nickname, home_url = await self._probe(platform, cdp_url)
                if status == SessionStatus.READY:
                    ready_streak += 1
                    if ready_streak >= 2:
                        self.repository.mark_logged_in(
                            account_id,
                            platform_nickname=nickname,
                            platform_home_url=home_url,
                        )
                        logger.info("local account login success account_id=%s platform=%s", account_id, platform)
                        return
                else:
                    ready_streak = 0
                await asyncio.sleep(self.poll_seconds)
            self.repository.mark_login_failed(account_id, error="login timed out waiting for user")
            logger.info("local account login timeout account_id=%s", account_id)
        except asyncio.CancelledError:  # pragma: no cover - superseded by a newer attempt
            raise
        except Exception as exc:
            self.repository.mark_login_failed(account_id, error=str(exc))
            logger.warning("local account login watch failed account_id=%s error=%s", account_id, exc)

    async def _probe(self, platform: str, cdp_url: str) -> tuple[SessionStatus, str | None, str | None]:
        provider = (
            DouyinBrowserSessionProvider()
            if platform == "douyin"
            else XhsBrowserSessionProvider()
        )
        acquired = await provider.acquire(session_meta={"cdp_url": cdp_url, "probe_only": True})
        try:
            if not acquired.page:
                return SessionStatus.UNAVAILABLE, None, None
            home_url = acquired.page.url
            nickname = None
            try:
                title = await acquired.page.title()
                if title:
                    nickname = title.split("-")[0].strip() or None
            except Exception:
                pass
            return acquired.status, nickname, home_url
        finally:
            await acquired.close()
