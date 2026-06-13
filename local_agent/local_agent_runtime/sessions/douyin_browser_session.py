"""Douyin browser session provider.

Acquires a logged-in Douyin browser session (CDP or persistent profile) and
reports session status. Login detection uses the same signals MediaCrawler's
``DouYinLogin.check_login_state`` relies on — ``localStorage.HasUserLogin`` and
cookie ``LOGIN_STATUS`` — neither of which needs request signing.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Sequence

from playwright.async_api import Browser, BrowserContext, async_playwright

from local_agent_runtime.connectors.douyin import field as dy_field
from local_agent_runtime.engine.session import BrowserSessionResult
from local_agent_runtime.enums import SessionStatus


def evaluate_douyin_login_state(
    *,
    url: str,
    visible_text: str,
    has_user_login: str | None,
    login_status_cookie: str | None,
    page_title: str = "",
) -> tuple[SessionStatus, str]:
    """Pure login-state decision, unit-testable without a browser."""

    haystack = f"{url}\n{page_title}\n{visible_text}".lower()
    if any(marker.lower() in haystack for marker in dy_field.CAPTCHA_PAGE_MARKERS):
        return SessionStatus.MANUAL_VERIFY_REQUIRED, "douyin requires manual verification"
    if str(has_user_login or "").strip() == "1":
        return SessionStatus.READY, "douyin session ready"
    if str(login_status_cookie or "").strip() == "1":
        return SessionStatus.READY, "douyin session ready"
    login_dialog = "登录" in visible_text and any(
        token in visible_text for token in ("验证码登录", "扫码登录", "手机号", "二维码")
    )
    if login_dialog or "login" in url.lower():
        return SessionStatus.EXPIRED, "douyin login is required"
    return SessionStatus.EXPIRED, "douyin logged-in state not detected; finish login in the browser window"


class DouyinBrowserSessionProvider:
    def __init__(self, *, home_url: str = dy_field.HOME_URL):
        self.home_url = home_url

    async def acquire(self, *, session_meta: dict[str, Any]) -> BrowserSessionResult:
        playwright = await async_playwright().start()
        browser: Browser | None = None
        context: BrowserContext | None = None
        try:
            cdp_url = session_meta.get("cdp_url")
            if cdp_url:
                browser = await playwright.chromium.connect_over_cdp(cdp_url)
                if not browser.contexts:
                    await browser.close()
                    await playwright.stop()
                    return BrowserSessionResult(
                        status=SessionStatus.UNAVAILABLE,
                        message="cdp connected but no browser context exists",
                        diagnostics={"cdp_url": cdp_url},
                    )
                context = browser.contexts[0]
            else:
                user_data_dir = session_meta.get("user_data_dir") or session_meta.get("profile_ref")
                if not user_data_dir:
                    await playwright.stop()
                    return BrowserSessionResult(
                        status=SessionStatus.UNAVAILABLE,
                        message="missing cdp_url or user_data_dir/profile_ref",
                    )
                profile_path = Path(user_data_dir)
                if not profile_path.exists():
                    await playwright.stop()
                    return BrowserSessionResult(
                        status=SessionStatus.UNAVAILABLE,
                        message=f"profile path does not exist: {profile_path}",
                    )
                context = await playwright.chromium.launch_persistent_context(
                    user_data_dir=str(profile_path),
                    executable_path=session_meta.get("chrome_executable_path"),
                    headless=bool(session_meta.get("headless", False)),
                    args=["--disable-blink-features=AutomationControlled"],
                )

            page = None
            if context.pages:
                for candidate in context.pages:
                    if "douyin.com" in (candidate.url or ""):
                        page = candidate
                        break
                page = page or context.pages[0]
            else:
                page = await context.new_page()

            if "douyin.com" not in (page.url or ""):
                await page.goto(
                    self.home_url,
                    wait_until="domcontentloaded",
                    timeout=int(session_meta.get("navigation_timeout_ms", 45000)),
                )
                await page.wait_for_timeout(1500)

            has_user_login = await self._read_local_storage_login(page)
            cookie_names_to_value = await self._read_login_cookie(context)
            visible_text = await self._safe_inner_text(page)
            page_title = await self._safe_title(page)
            status, message = evaluate_douyin_login_state(
                url=page.url,
                visible_text=visible_text,
                has_user_login=has_user_login,
                login_status_cookie=cookie_names_to_value,
                page_title=page_title,
            )
            return BrowserSessionResult(
                status=status,
                message=message,
                playwright=playwright,
                browser=browser,
                context=context,
                page=page,
                diagnostics={"url": page.url},
                detached_cdp=bool(cdp_url),
            )
        except Exception as exc:
            if context:
                await context.close()
            if browser:
                await browser.close()
            await playwright.stop()
            return BrowserSessionResult(
                status=SessionStatus.UNAVAILABLE,
                message=f"session_connect_failed: {exc}",
            )

    @staticmethod
    async def _read_local_storage_login(page) -> str | None:
        try:
            value = await page.evaluate(
                f"() => window.localStorage.getItem('{dy_field.LOCAL_STORAGE_LOGIN_KEY}')"
            )
            return str(value) if value is not None else None
        except Exception:
            return None

    @staticmethod
    async def _read_login_cookie(context: BrowserContext) -> str | None:
        try:
            cookies = await context.cookies([dy_field.DOUYIN_HOST])
        except Exception:
            return None
        for cookie in cookies or []:
            if str(cookie.get("name", "")) == dy_field.LOGIN_STATUS_COOKIE:
                return str(cookie.get("value", ""))
        return None

    @staticmethod
    async def _safe_inner_text(page) -> str:
        try:
            return await page.locator("body").inner_text(timeout=5000)
        except Exception:
            return ""

    @staticmethod
    async def _safe_title(page) -> str:
        try:
            return await page.title()
        except Exception:
            return ""


def cookie_names(cookies: Sequence[dict[str, Any]]) -> list[str]:
    return [str(cookie.get("name", "")) for cookie in cookies]
