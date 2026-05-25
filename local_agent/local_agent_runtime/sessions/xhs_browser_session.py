from dataclasses import dataclass
from pathlib import Path
from typing import Any

from playwright.async_api import Browser, BrowserContext, Page, Playwright, async_playwright

from local_agent_runtime.enums import SessionStatus


@dataclass
class XhsSessionAcquireResult:
    status: SessionStatus
    message: str
    playwright: Playwright | None = None
    browser: Browser | None = None
    context: BrowserContext | None = None
    page: Page | None = None
    diagnostics: dict[str, Any] | None = None

    detached_cdp: bool = False

    async def close(self) -> None:
        if self.detached_cdp:
            if self.browser:
                try:
                    await self.browser.close()
                except Exception:
                    pass
            if self.playwright:
                await self.playwright.stop()
            return
        if self.context:
            await self.context.close()
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()


def evaluate_xhs_session_state(*, url: str, visible_text: str) -> tuple[SessionStatus, str]:
    url_lower = url.lower()
    if "login" in url_lower or "signin" in url_lower:
        return SessionStatus.EXPIRED, "xhs redirected to login page"
    if "登录" in visible_text and any(token in visible_text for token in ("手机号", "验证码", "扫码", "密码", "注册")):
        return SessionStatus.EXPIRED, "xhs login is required"
    if "验证码" in visible_text or "安全验证" in visible_text or "滑块" in visible_text:
        return SessionStatus.MANUAL_VERIFY_REQUIRED, "xhs page requires manual verification"
    logged_in_markers = (
        "退出登录",
        "创作者中心",
        "创作中心",
        "个人主页",
        "我 的",
        "消息",
        "通知",
    )
    if any(marker in visible_text for marker in logged_in_markers):
        return SessionStatus.READY, "xhs session ready"
    if "发布" in visible_text and ("发现" in visible_text or "explore" in url_lower):
        return SessionStatus.READY, "xhs session ready"
    return SessionStatus.EXPIRED, "xhs logged-in state not detected; finish login in the browser window"


class XhsBrowserSessionProvider:
    """First-pass XHS browser session provider for a single local account session."""

    def __init__(self, *, home_url: str = "https://www.xiaohongshu.com/explore"):
        self.home_url = home_url

    async def acquire(self, *, session_meta: dict[str, Any]) -> XhsSessionAcquireResult:
        playwright = await async_playwright().start()
        browser: Browser | None = None
        context: BrowserContext | None = None
        page: Page | None = None
        diagnostics: dict[str, Any] = {}
        try:
            cdp_url = session_meta.get("cdp_url")
            if cdp_url:
                browser = await playwright.chromium.connect_over_cdp(cdp_url)
                if not browser.contexts:
                    await browser.close()
                    await playwright.stop()
                    return XhsSessionAcquireResult(
                        status=SessionStatus.UNAVAILABLE,
                        message="cdp connected but no browser context exists",
                        diagnostics={"cdp_url": cdp_url},
                    )
                context = browser.contexts[0]
            else:
                user_data_dir = session_meta.get("user_data_dir") or session_meta.get("profile_ref")
                if not user_data_dir:
                    await playwright.stop()
                    return XhsSessionAcquireResult(
                        status=SessionStatus.UNAVAILABLE,
                        message="missing cdp_url or user_data_dir/profile_ref",
                    )
                profile_path = Path(user_data_dir)
                if not profile_path.exists():
                    await playwright.stop()
                    return XhsSessionAcquireResult(
                        status=SessionStatus.UNAVAILABLE,
                        message=f"profile path does not exist: {profile_path}",
                    )
                context = await playwright.chromium.launch_persistent_context(
                    user_data_dir=str(profile_path),
                    executable_path=session_meta.get("chrome_executable_path"),
                    headless=bool(session_meta.get("headless", False)),
                    args=["--disable-blink-features=AutomationControlled"],
                )
            probe_only = bool(session_meta.get("probe_only"))
            page = None
            if context.pages:
                for candidate in context.pages:
                    if "xiaohongshu.com" in (candidate.url or ""):
                        page = candidate
                        break
                page = page or context.pages[0]
            else:
                page = await context.new_page()
            if probe_only and cdp_url:
                await page.wait_for_timeout(300)
            else:
                await page.goto(self.home_url, wait_until="domcontentloaded", timeout=int(session_meta.get("navigation_timeout_ms", 45000)))
                await page.wait_for_timeout(1500)
            visible_text = await page.locator("body").inner_text(timeout=5000)
            status, message = evaluate_xhs_session_state(url=page.url, visible_text=visible_text)
            return XhsSessionAcquireResult(
                status=status,
                message=message,
                playwright=playwright,
                browser=browser,
                context=context,
                page=page,
                diagnostics={**diagnostics, "url": page.url},
                detached_cdp=bool(cdp_url and probe_only),
            )
        except Exception as exc:
            if context:
                await context.close()
            if browser:
                await browser.close()
            await playwright.stop()
            return XhsSessionAcquireResult(
                status=SessionStatus.UNAVAILABLE,
                message=f"session_connect_failed: {exc}",
                diagnostics=diagnostics,
            )
