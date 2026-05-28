from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

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
    if "验证码" in visible_text or "安全验证" in visible_text or "滑块" in visible_text:
        return SessionStatus.MANUAL_VERIFY_REQUIRED, "xhs page requires manual verification"
    strong_ready_markers = (
        "退出登录",
        "创作者中心",
        "创作中心",
        "个人主页",
        "我的",
    )
    nav_markers = ("首页", "发现", "关注")
    action_markers = ("消息", "通知", "发布", "我的")
    # 部分登录后的页面仍可能出现“登录”字样（例如按钮文案），先用已登录特征兜底，避免误判。
    if any(marker in visible_text for marker in strong_ready_markers):
        return SessionStatus.READY, "xhs session ready"
    if "xiaohongshu.com/user/profile" in url_lower and any(marker in visible_text for marker in nav_markers) and any(
        marker in visible_text for marker in action_markers
    ):
        return SessionStatus.READY, "xhs session ready"
    if "登录" in visible_text and any(token in visible_text for token in ("手机号", "验证码", "扫码", "密码", "注册")):
        return SessionStatus.EXPIRED, "xhs login is required"
    return SessionStatus.EXPIRED, "xhs logged-in state not detected; finish login in the browser window"


def evaluate_xhs_selfinfo_payload(payload: Any) -> tuple[SessionStatus | None, str | None]:
    """优先用 selfinfo API 判定登录态；返回 None 表示无法判断，交给 UI 文案兜底。"""
    if not isinstance(payload, dict):
        return None, None
    text = " ".join(
        str(payload.get(key, ""))
        for key in ("msg", "message", "detail")
        if payload.get(key) is not None
    )
    lowered = text.lower()
    if any(token in lowered for token in ("verify",)) or any(token in text for token in ("验证", "滑块")):
        return SessionStatus.MANUAL_VERIFY_REQUIRED, "xhs page requires manual verification"
    if any(token in lowered for token in ("login", "not login", "unauthorized")) or any(
        token in text for token in ("未登录", "登录")
    ):
        return SessionStatus.EXPIRED, "xhs login is required"
    if payload.get("success") is True:
        data = payload.get("data")
        if isinstance(data, dict):
            profile = data.get("basic_info") if isinstance(data.get("basic_info"), dict) else data
            nickname = profile.get("nickname") if isinstance(profile, dict) else None
            user_id = profile.get("user_id") if isinstance(profile, dict) else None
            if nickname or user_id:
                return SessionStatus.READY, "xhs session ready"
        return SessionStatus.EXPIRED, "xhs login is required"
    return None, None


def evaluate_xhs_browser_markers(
    *,
    url: str,
    visible_text: str,
    cookie_names: Sequence[str],
    hrefs: Sequence[str],
) -> tuple[SessionStatus | None, str | None]:
    """Use current web UI markers when selfinfo is temporarily unavailable."""
    url_lower = url.lower()
    if "login" in url_lower or "signin" in url_lower:
        return SessionStatus.EXPIRED, "xhs redirected to login page"
    login_dialog_visible = "登录" in visible_text and any(
        token in visible_text for token in ("手机号", "验证码", "扫码", "密码", "注册")
    )
    if login_dialog_visible:
        return SessionStatus.EXPIRED, "xhs login is required"

    normalized_cookies = {name.lower() for name in cookie_names}
    has_session_cookie = bool({"web_session", "id_token"} & normalized_cookies)
    has_profile_link = any("/user/profile/" in href.lower() for href in hrefs)
    has_logged_in_nav = "消息" in visible_text and "发布" in visible_text
    if has_session_cookie and has_profile_link and has_logged_in_nav:
        return SessionStatus.READY, "xhs session ready"
    return None, None


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
                api_status, api_message = await self._probe_selfinfo_via_fetch(page)
                if api_status and api_message:
                    return XhsSessionAcquireResult(
                        status=api_status,
                        message=api_message,
                        playwright=playwright,
                        browser=browser,
                        context=context,
                        page=page,
                        diagnostics={**diagnostics, "url": page.url, "probe": "selfinfo"},
                        detached_cdp=bool(cdp_url and probe_only),
                    )
            else:
                await page.goto(self.home_url, wait_until="domcontentloaded", timeout=int(session_meta.get("navigation_timeout_ms", 45000)))
                await page.wait_for_timeout(1500)
            visible_text = await page.locator("body").inner_text(timeout=5000)
            status, message = evaluate_xhs_session_state(url=page.url, visible_text=visible_text)
            if status == SessionStatus.EXPIRED:
                marker_status, marker_message = await self._probe_browser_markers(page, context, visible_text)
                if marker_status and marker_message:
                    status, message = marker_status, marker_message
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

    async def _probe_selfinfo_via_fetch(self, page: Page) -> tuple[SessionStatus | None, str | None]:
        try:
            payload = await page.evaluate(
                """async () => {
                    try {
                        const resp = await fetch('/api/sns/web/v1/user/selfinfo', {
                            method: 'GET',
                            credentials: 'include',
                        });
                        const text = await resp.text();
                        let body = null;
                        try { body = JSON.parse(text); } catch (_) { body = { message: text }; }
                        return { ok: resp.ok, status: resp.status, body };
                    } catch (err) {
                        return { ok: false, status: 0, body: { message: String(err) } };
                    }
                }"""
            )
        except Exception:
            return None, None
        if not isinstance(payload, dict):
            return None, None
        status = payload.get("status")
        body = payload.get("body")
        if status in (401, 403):
            return SessionStatus.EXPIRED, "xhs login is required"
        return evaluate_xhs_selfinfo_payload(body)

    async def _probe_browser_markers(
        self,
        page: Page,
        context: BrowserContext,
        visible_text: str,
    ) -> tuple[SessionStatus | None, str | None]:
        try:
            cookies = await context.cookies(["https://www.xiaohongshu.com"])
            cookie_names = [str(cookie.get("name", "")) for cookie in cookies]
            hrefs = await page.evaluate(
                """() => Array.from(document.querySelectorAll('a[href]'))
                    .map((link) => link.href || link.getAttribute('href') || '')
                    .filter(Boolean)
                    .slice(0, 200)"""
            )
        except Exception:
            return None, None
        if not isinstance(hrefs, list):
            hrefs = []
        return evaluate_xhs_browser_markers(
            url=page.url,
            visible_text=visible_text,
            cookie_names=cookie_names,
            hrefs=[str(href) for href in hrefs],
        )
