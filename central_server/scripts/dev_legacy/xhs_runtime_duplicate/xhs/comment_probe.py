import asyncio
from dataclasses import dataclass, field
from typing import Any

from playwright.async_api import Page

from intelligence_engine.connectors.xhs.api_client import XhsApiClient, browser_context_cookie_header
from intelligence_engine.connectors.xhs.comment_normalizer import normalize_xhs_comments
from intelligence_engine.connectors.xhs.detail_probe import parse_json_like_script
from intelligence_engine.connectors.xhs.context import build_xhs_note_url, context_from_url_and_raw, merge_xhs_context, url_has_xsec_context
from intelligence_engine.domain.schemas import CommentSnapshotInput

COMMENT_SURFACE_UNAVAILABLE_MARKERS = [
    "当前笔记暂时无法浏览",
    "请打开小红书App扫码查看",
    "无法浏览",
]

LOGIN_REQUIRED_MARKERS = ["手机号登录", "扫码登录", "登录后查看"]
MANUAL_VERIFY_MARKERS = ["安全验证", "验证码", "拖动滑块"]


COMMENT_JSON_SCRIPT = """
() => {
  const payload = { scripts: [], globals: {} };
  for (const script of Array.from(document.querySelectorAll('script'))) {
    const text = script.textContent || '';
    if (text.includes('comment') || text.includes('comments') || text.includes('评论') || text.includes('__INITIAL_STATE__')) {
      payload.scripts.push(text.slice(0, 800000));
    }
  }
  for (const key of Object.keys(window)) {
    if (key.includes('INITIAL') || key.includes('__REDUX') || key.includes('STATE')) {
      try {
        const raw = JSON.stringify(window[key]);
        payload.globals[key] = raw ? raw.slice(0, 800000) : null;
      } catch (e) {
        payload.globals[key] = null;
      }
    }
  }
  return payload;
}
"""

COMMENT_DOM_SCRIPT = """
(limit) => {
  const nodes = Array.from(document.querySelectorAll('[class*="comment"], .comment-item, [data-comment-id]'));
  const out = [];
  const seenText = new Set();
  for (const node of nodes) {
    const text = (node.innerText || node.textContent || '').trim();
    if (!text || text.length < 2 || seenText.has(text)) continue;
    seenText.add(text);
    const author = node.querySelector('[class*="author"], [class*="name"], a[href*="/user/profile"]');
    const like = node.querySelector('[class*="like"], [class*="count"]');
    out.push({
      platform_comment_id: node.getAttribute('data-comment-id') || node.id || null,
      author_name: author ? (author.innerText || author.textContent || '').trim() : null,
      author_platform_id: author ? (author.getAttribute('data-user-id') || author.getAttribute('href')) : null,
      body_text: text,
      like_count: like ? (like.innerText || like.textContent || '').trim() : null,
      raw_source: 'dom'
    });
    if (out.length >= limit) break;
  }
  return out;
}
"""


@dataclass
class XhsCommentFetchResult:
    comments: list[CommentSnapshotInput] = field(default_factory=list)
    surface_status: str = "ok"
    error_code: str | None = None
    message: str | None = None
    diagnostics: dict[str, Any] = field(default_factory=dict)


def detect_comment_surface_status(*, url: str, body_text: str, comment_node_count: int) -> tuple[str, str | None, str | None]:
    if any(marker in body_text for marker in COMMENT_SURFACE_UNAVAILABLE_MARKERS):
        return "comment_surface_unavailable", "comment_surface_unavailable", "xhs web detail/comment surface is unavailable"
    if any(marker in body_text for marker in MANUAL_VERIFY_MARKERS):
        return "manual_verify_required", "manual_verify_required", "xhs manual verification is required"
    if "login" in url.lower() or any(marker in body_text for marker in LOGIN_REQUIRED_MARKERS):
        return "login_required", "session_expired", "xhs login is required"
    return "ok", None, None


class XhsCommentProbe:
    async def fetch_comments_result(
        self,
        page: Page,
        *,
        canonical_url: str,
        platform_content_id: str,
        platform_context: dict[str, Any] | None = None,
        limit: int = 20,
    ) -> XhsCommentFetchResult:
        resolved_context = merge_xhs_context(
            context_from_url_and_raw(canonical_url),
            platform_context or {},
            {"note_id": platform_content_id},
        )
        if not resolved_context.get("has_xsec_context"):
            return XhsCommentFetchResult(
                surface_status="missing_xsec_context",
                error_code="missing_xsec_context",
                message="xhs comment fetch requires xsec_token and xsec_source from the full note URL/context",
                diagnostics={
                    "url": canonical_url,
                    "platform_content_id": platform_content_id,
                    "platform_context": resolved_context,
                },
            )
        try:
            cookie_str = await browser_context_cookie_header(page.context)
            raw_comments, api_diagnostics = await XhsApiClient(cookie_str=cookie_str).get_note_comments(
                note_id=resolved_context["note_id"],
                xsec_token=resolved_context["xsec_token"],
                limit=limit,
            )
            api_comments = normalize_xhs_comments({"comments": raw_comments}, limit=limit)
            if api_comments or raw_comments == []:
                return XhsCommentFetchResult(
                    comments=api_comments[:limit],
                    surface_status="true_empty_comments" if not api_comments else "ok",
                    diagnostics={**api_diagnostics, "platform_context": resolved_context},
                )
        except Exception as exc:
            api_error = str(exc)
        else:
            api_error = None
        resolved_url = canonical_url if url_has_xsec_context(canonical_url) else (build_xhs_note_url(resolved_context, fallback_url=canonical_url) or canonical_url)

        network_payloads: list[dict[str, Any]] = []

        async def capture_response(response):
            url = response.url.lower()
            if "comment" not in url:
                return
            try:
                network_payloads.append(await response.json())
            except Exception:
                return

        def on_response(response):
            asyncio.create_task(capture_response(response))

        page.on("response", on_response)
        await page.goto(resolved_url, wait_until="domcontentloaded", timeout=45000)
        await page.wait_for_timeout(2500)
        for _ in range(8):
            await page.mouse.wheel(0, 1200)
            await page.wait_for_timeout(900)
        await page.wait_for_timeout(1500)
        try:
            page.remove_listener("response", on_response)
        except Exception:
            pass

        body_state = await page.evaluate(
            """
            () => {
              const bodyText = document.body ? document.body.innerText : '';
              const commentNodeCount = document.querySelectorAll('[class*="comment"], .comment-item, [data-comment-id]').length;
              return {url: location.href, bodyText: bodyText.slice(0, 5000), commentNodeCount};
            }
            """
        )
        surface_status, error_code, message = detect_comment_surface_status(
            url=body_state.get("url") or page.url,
            body_text=body_state.get("bodyText") or "",
            comment_node_count=int(body_state.get("commentNodeCount") or 0),
        )
        if surface_status != "ok":
            return XhsCommentFetchResult(
                surface_status=surface_status,
                error_code=error_code,
                message=message,
                diagnostics={"url": body_state.get("url"), "resolved_url": resolved_url, "comment_node_count": body_state.get("commentNodeCount"), "platform_context": resolved_context},
            )

        network_comments = normalize_xhs_comments({"network": network_payloads}, limit=limit)
        if len(network_comments) >= limit:
            return XhsCommentFetchResult(
                comments=network_comments[:limit],
                diagnostics={"source": "network", "network_payload_count": len(network_payloads)},
            )

        raw_state = await page.evaluate(COMMENT_JSON_SCRIPT)
        merged: dict[str, Any] = {"globals": {}, "scripts": []}
        for raw_global in (raw_state.get("globals") or {}).values():
            if isinstance(raw_global, str):
                parsed = parse_json_like_script(raw_global)
                if parsed:
                    merged["scripts"].append(parsed)
        for script in raw_state.get("scripts") or []:
            parsed = parse_json_like_script(script)
            if parsed:
                merged["scripts"].append(parsed)
        comments = network_comments + [
            comment
            for comment in normalize_xhs_comments(merged, limit=limit)
            if comment.platform_comment_id not in {existing.platform_comment_id for existing in network_comments}
        ]
        if len(comments) >= limit:
            return XhsCommentFetchResult(
                comments=comments[:limit],
                diagnostics={"source": "network+state", "network_payload_count": len(network_payloads)},
            )
        dom_comments = await page.evaluate(COMMENT_DOM_SCRIPT, limit)
        dom_normalized = normalize_xhs_comments({"dom": dom_comments}, limit=limit)
        seen = {comment.platform_comment_id for comment in comments}
        for comment in dom_normalized:
            if comment.platform_comment_id not in seen:
                comments.append(comment)
                seen.add(comment.platform_comment_id)
            if len(comments) >= limit:
                break
        return XhsCommentFetchResult(
            comments=comments[:limit],
            surface_status="true_empty_comments" if not comments else "ok",
            diagnostics={
                "source": "mixed",
                "api_error": api_error,
                "network_payload_count": len(network_payloads),
                "dom_comment_count": len(dom_normalized),
                "comment_node_count": body_state.get("commentNodeCount"),
                "resolved_url": resolved_url,
                "platform_context": resolved_context,
            },
        )

    async def fetch_comments(
        self,
        page: Page,
        *,
        canonical_url: str,
        platform_content_id: str,
        platform_context: dict[str, Any] | None = None,
        limit: int = 20,
    ) -> list[CommentSnapshotInput]:
        return (
            await self.fetch_comments_result(
                page,
                canonical_url=canonical_url,
                platform_content_id=platform_content_id,
                platform_context=platform_context,
                limit=limit,
            )
        ).comments
