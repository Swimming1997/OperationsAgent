from typing import Any

from playwright.async_api import Page

from intelligence_engine.connectors.xhs.api_client import XhsApiClient, browser_context_cookie_header
from intelligence_engine.connectors.xhs.detail_normalizer import normalize_xhs_detail_payload
from intelligence_engine.connectors.xhs.context import build_xhs_note_url, context_from_url_and_raw, merge_xhs_context, url_has_xsec_context
from intelligence_engine.domain.schemas import DetailSnapshotInput


DETAIL_JSON_SCRIPT = """
() => {
  const payload = { scripts: [], globals: {} };
  for (const script of Array.from(document.querySelectorAll('script'))) {
    const text = script.textContent || '';
    if (text.includes('window.__INITIAL_STATE__') || text.includes('__INITIAL_STATE__') || text.includes('note')) {
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

DETAIL_DOM_SCRIPT = """
() => {
  const title = document.querySelector('#detail-title, .title, [class*="title"]');
  const desc = document.querySelector('#detail-desc, .desc, [class*="desc"], [class*="content"]');
  const author = document.querySelector('.author, [class*="author"], .username, [class*="user"]');
  const avatar = document.querySelector('.author img, [class*="author"] img, [class*="user"] img');
  const imgs = Array.from(document.querySelectorAll('img')).map(img => img.currentSrc || img.src).filter(Boolean);
  const video = document.querySelector('video');
  const text = document.body ? document.body.innerText : '';
  return {
    title: title ? (title.innerText || title.textContent || '').trim() : null,
    body_text: desc ? (desc.innerText || desc.textContent || '').trim() : null,
    author_name: author ? (author.innerText || author.textContent || '').trim() : null,
    author_platform_id: author ? (author.getAttribute('data-user-id') || author.getAttribute('href')) : null,
    author_avatar_url: avatar ? (avatar.currentSrc || avatar.src) : null,
    cover_url: imgs[0] || null,
    image_urls: imgs,
    video_url: video ? (video.currentSrc || video.src) : null,
    body_text_all: text.slice(0, 3000)
  };
}
"""


def parse_json_like_script(script_text: str) -> dict[str, Any]:
    candidates = []
    for marker in ["window.__INITIAL_STATE__=", "window.__INITIAL_STATE__ ="]:
        if marker in script_text:
            candidates.append(script_text.split(marker, 1)[1])
    if not candidates:
        candidates.append(script_text)
    for candidate in candidates:
        candidate = candidate.strip().rstrip(";")
        try:
            import json

            return json.loads(candidate)
        except Exception:
            continue
    return {}


class XhsDetailProbe:
    async def fetch_detail(
        self,
        page: Page,
        *,
        canonical_url: str,
        platform_content_id: str,
        platform_context: dict[str, Any] | None = None,
    ) -> DetailSnapshotInput:
        resolved_context = merge_xhs_context(
            context_from_url_and_raw(canonical_url),
            platform_context or {},
            {"note_id": platform_content_id},
        )
        if resolved_context.get("has_xsec_context"):
            try:
                cookie_str = await browser_context_cookie_header(page.context)
                api_note = await XhsApiClient(cookie_str=cookie_str).get_note_by_id(
                    note_id=resolved_context["note_id"],
                    xsec_source=resolved_context.get("xsec_source") or "pc_search",
                    xsec_token=resolved_context["xsec_token"],
                )
                if api_note:
                    return normalize_xhs_detail_payload(
                        {"api": api_note},
                        platform_content_id=platform_content_id,
                        dom_fallback={
                            "platform_context": resolved_context,
                            "resolved_url": build_xhs_note_url(resolved_context, fallback_url=canonical_url) or canonical_url,
                            "fetch_source": "api",
                        },
                    )
            except Exception:
                pass
        resolved_url = canonical_url if url_has_xsec_context(canonical_url) else (build_xhs_note_url(resolved_context, fallback_url=canonical_url) or canonical_url)
        await page.goto(resolved_url, wait_until="domcontentloaded", timeout=45000)
        await page.wait_for_timeout(2000)
        raw_state = await page.evaluate(DETAIL_JSON_SCRIPT)
        dom_fallback = await page.evaluate(DETAIL_DOM_SCRIPT)
        merged: dict[str, Any] = {"globals": raw_state.get("globals") or {}, "scripts": []}
        for raw_global in (raw_state.get("globals") or {}).values():
            if isinstance(raw_global, str):
                parsed = parse_json_like_script(raw_global)
                if parsed:
                    merged["scripts"].append(parsed)
        for script in raw_state.get("scripts") or []:
            parsed = parse_json_like_script(script)
            if parsed:
                merged["scripts"].append(parsed)
        dom_fallback["platform_context"] = resolved_context
        dom_fallback["resolved_url"] = resolved_url
        return normalize_xhs_detail_payload(merged, platform_content_id=platform_content_id, dom_fallback=dom_fallback)
