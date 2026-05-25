from typing import Any

from playwright.async_api import Page

from local_agent_runtime.connectors.xhs.api_client import XhsApiClient, browser_context_cookie_header
from local_agent_runtime.connectors.xhs.context import (
    build_xhs_note_url,
    context_from_url_and_raw,
    is_suspect_detail_author_name,
    merge_xhs_context,
)
from local_agent_runtime.connectors.xhs.detail_normalizer import normalize_xhs_detail_payload
from local_agent_runtime.contracts import DetailSnapshotInput


DETAIL_JSON_SCRIPT = """
() => {
  const payload = { scripts: [], globals: {} };
  for (const script of Array.from(document.querySelectorAll('script'))) {
    const text = script.textContent || '';
    if (text.includes('window.__INITIAL_STATE__') || text.includes('__INITIAL_STATE__') || text.includes('noteDetailMap')) {
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
  const authorLink = document.querySelector('a[href*="/user/profile/"]');
  const author = document.querySelector('.author-wrapper .name, .author .name, .username');
  const avatar = document.querySelector('.author-wrapper img, .author img, a[href*="/user/profile/"] img');
  const imgs = Array.from(document.querySelectorAll('img')).map(img => img.currentSrc || img.src).filter(Boolean);
  const video = document.querySelector('video');
  const text = document.body ? document.body.innerText : '';
  const authorHref = authorLink ? (authorLink.getAttribute('href') || authorLink.href || '') : '';
  const authorMatch = authorHref.match(/\\/user\\/profile\\/([^/?#]+)/);
  return {
    title: title ? (title.innerText || title.textContent || '').trim() : null,
    body_text: desc ? (desc.innerText || desc.textContent || '').trim() : null,
    author_name: author ? (author.innerText || author.textContent || '').trim() : null,
    author_platform_id: authorMatch ? authorMatch[1] : null,
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
        if candidate.endswith("</script>"):
            candidate = candidate[: candidate.rfind("</script>")]
        candidate = candidate.replace("undefined", '""')
        try:
            import json

            return json.loads(candidate)
        except Exception:
            continue
    return {}


def _deep_iter(value: Any):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _deep_iter(child)
    elif isinstance(value, list):
        for child in value:
            yield from _deep_iter(child)


def extract_note_detail_from_state(payload: dict[str, Any], note_id: str) -> dict[str, Any]:
    for item in _deep_iter(payload):
        for key in ("noteDetailMap", "note_detail_map"):
            note_map = item.get(key)
            if not isinstance(note_map, dict):
                continue
            if note_id in note_map:
                entry = note_map[note_id]
                if isinstance(entry, dict):
                    return entry.get("note") or entry.get("noteDetail") or entry
            for entry in note_map.values():
                if not isinstance(entry, dict):
                    continue
                note = entry.get("note") or entry.get("noteDetail") or entry
                if isinstance(note, dict) and str(note.get("noteId") or note.get("note_id") or "") == note_id:
                    return note
    return {}


class XhsDetailProbe:
    async def fetch_detail(
        self,
        page: Page,
        *,
        canonical_url: str,
        platform_content_id: str,
        platform_context: dict[str, Any] | None = None,
        source_surface: str | None = None,
        upstream_author_name: str | None = None,
    ) -> DetailSnapshotInput:
        source_surface = source_surface or (platform_context or {}).get("source_surface")
        resolved_context = merge_xhs_context(
            context_from_url_and_raw(canonical_url, source_surface=source_surface),
            platform_context or {},
            {"note_id": platform_content_id},
            source_surface=source_surface,
        )
        resolved_url = build_xhs_note_url(resolved_context, fallback_url=canonical_url, source_surface=source_surface) or canonical_url
        diagnostics = {
            "platform_context": resolved_context,
            "resolved_url": resolved_url,
            "canonical_url": resolved_url,
            "xsec_source_effective": resolved_context.get("xsec_source_effective"),
            "xsec_source_status": resolved_context.get("xsec_source_status"),
            "xsec_source_inferred": resolved_context.get("xsec_source_inferred"),
            "upstream_author_name": upstream_author_name,
            "api_attempted": False,
            "api_success": False,
        }
        api_error_code: str | None = None
        api_error_message: str | None = None

        if resolved_context.get("api_detail_ready"):
            diagnostics["api_attempted"] = True
            try:
                cookie_str = await browser_context_cookie_header(page.context)
                api_note = await XhsApiClient(cookie_str=cookie_str).get_note_by_id(
                    note_id=resolved_context["note_id"],
                    xsec_source=str(resolved_context.get("xsec_source_effective") or "pc_search"),
                    xsec_token=resolved_context["xsec_token"],
                )
                if api_note:
                    diagnostics["api_success"] = True
                    dom_fallback = {
                        **diagnostics,
                        "fetch_source": "api",
                        "source_path": "api",
                    }
                    return normalize_xhs_detail_payload(
                        {"api": api_note},
                        platform_content_id=platform_content_id,
                        dom_fallback=dom_fallback,
                        upstream_author_name=upstream_author_name,
                    )
                api_error_code = "api_empty_response"
                api_error_message = "detail API returned empty note payload"
            except Exception as exc:
                api_error_code = exc.__class__.__name__
                api_error_message = str(exc)[:300]
        else:
            api_error_code = "missing_xsec_token"
            api_error_message = "detail API requires note_id and xsec_token"

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
        structured_note = extract_note_detail_from_state(merged, platform_content_id)
        if structured_note:
            merged["noteDetailMap"] = {platform_content_id: {"note": structured_note}}

        suspect_author = is_suspect_detail_author_name(dom_fallback.get("author_name"), upstream_author_name=upstream_author_name)
        dom_fallback.update(
            {
                **diagnostics,
                "resolved_url": resolved_url,
                "canonical_url": resolved_url,
                "fetch_source": "dom",
                "source_path": "dom_detail_extract",
                "api_error_code": api_error_code,
                "api_error_message": api_error_message,
                "suspect_author": suspect_author,
                "structured_state_found": bool(structured_note),
            }
        )
        if suspect_author:
            dom_fallback["author_name"] = None
        return normalize_xhs_detail_payload(
            merged,
            platform_content_id=platform_content_id,
            dom_fallback=dom_fallback,
            upstream_author_name=upstream_author_name,
        )
