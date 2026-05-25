from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from local_agent_runtime.enums import LoginSessionStatus, SessionStatus
from local_agent_runtime.chrome_launcher import launch_managed_chrome
from local_agent_runtime.sessions.xhs_browser_session import XhsBrowserSessionProvider, evaluate_xhs_session_state


@dataclass(frozen=True)
class LoginSessionPayload:
    session_id: str
    platform_account_id: str
    profile_key: str
    cdp_port: int


class LoginCenterClient(Protocol):
    async def report_login_progress(self, agent_id: str, session_id: str, status: str, *, error_message: str | None = None) -> None: ...
    async def complete_login_session(
        self,
        agent_id: str,
        session_id: str,
        *,
        platform_nickname: str | None = None,
        platform_home_url: str | None = None,
    ) -> None: ...
    async def fail_login_session(self, agent_id: str, session_id: str, error_message: str) -> None: ...


class AccountLoginExecutor:
    def __init__(self, *, project_root: Path, client: LoginCenterClient, observe_timeout_seconds: float = 600.0, poll_seconds: float = 8.0):
        self.project_root = project_root
        self.client = client
        self.observe_timeout_seconds = observe_timeout_seconds
        self.poll_seconds = poll_seconds

    async def execute(self, *, agent_id: str, session: LoginSessionPayload) -> None:
        chrome_process = None
        login_succeeded = False
        ready_streak = 0
        try:
            await self.client.report_login_progress(agent_id, session.session_id, LoginSessionStatus.LAUNCHING_BROWSER.value)
            _, chrome_process = await asyncio.to_thread(
                launch_managed_chrome,
                project_root=self.project_root,
                profile_key=session.profile_key,
                cdp_port=session.cdp_port,
            )
            await asyncio.sleep(4.0)
            await self.client.report_login_progress(agent_id, session.session_id, LoginSessionStatus.WAITING_USER_LOGIN.value)

            cdp_url = f"http://127.0.0.1:{session.cdp_port}"
            deadline = asyncio.get_event_loop().time() + self.observe_timeout_seconds
            while asyncio.get_event_loop().time() < deadline:
                status, message, nickname, home_url = await self._probe_session(cdp_url)
                if status == SessionStatus.READY:
                    ready_streak += 1
                    if ready_streak >= 2:
                        await self.client.complete_login_session(
                            agent_id,
                            session.session_id,
                            platform_nickname=nickname,
                            platform_home_url=home_url,
                        )
                        login_succeeded = True
                        return
                else:
                    ready_streak = 0
                    if status == SessionStatus.MANUAL_VERIFY_REQUIRED:
                        await self.client.report_login_progress(
                            agent_id,
                            session.session_id,
                            LoginSessionStatus.WAITING_USER_LOGIN.value,
                            error_message=message,
                        )
                await asyncio.sleep(self.poll_seconds)

            await self.client.fail_login_session(agent_id, session.session_id, "login timed out waiting for user")
        except Exception as exc:
            await self.client.fail_login_session(agent_id, session.session_id, str(exc))
        finally:
            if chrome_process and chrome_process.poll() is None and not login_succeeded:
                try:
                    chrome_process.terminate()
                except Exception:
                    pass

    async def _probe_session(self, cdp_url: str) -> tuple[SessionStatus, str, str | None, str | None]:
        provider = XhsBrowserSessionProvider()
        acquired = await provider.acquire(session_meta={"cdp_url": cdp_url, "probe_only": True})
        try:
            if not acquired.page:
                return SessionStatus.UNAVAILABLE, acquired.message, None, None
            nickname = None
            home_url = acquired.page.url
            try:
                title = await acquired.page.title()
                if title and "小红书" in title:
                    nickname = title.split("-")[0].strip() or None
            except Exception:
                pass
            return acquired.status, acquired.message, nickname, home_url
        finally:
            await acquired.close()
