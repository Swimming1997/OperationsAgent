from __future__ import annotations

import time
import urllib.parse
from datetime import datetime, timezone
from typing import Any, Iterator

from playwright.async_api import Page


XHS_SEARCH_RESULT_URL = "https://www.xiaohongshu.com/search_result"

# XHS web autocomplete endpoint. Navigating to /search_result?keyword=<kw> makes
# the page fire this request automatically and the response carries the long-tail
# suggestions under data.sug_items[].text. This is far more reliable than trying
# to type into the explore header, which is now the "问点点" AI textarea and never
# triggers the classic recommend endpoint.
SUG_URL_MARKERS = (
    "/search/recommend",
    "/search/sug",
    "/search/query_recommend",
)

# Real search input on the search_result page header (the visible one carries the id).
SEARCH_INPUT_SELECTORS = (
    "input#search-input",
    "input.search-input",
    "input[placeholder*='搜索']",
)

# Global navigation / chrome that must never be treated as a suggestion.
_NAV_BLOCKLIST = {
    "首页",
    "发现",
    "发布",
    "通知",
    "消息",
    "我",
    "直播",
    "登录",
    "搜索",
    "相关搜索",
    "red",
    "点点ai",
    "创作中心",
    "薯条推广",
    "业务合作",
}

# Secondary source: the "相关搜索" chips rendered on the results page.
DROPDOWN_SCRIPT = """
() => {
  const out = [];
  const seen = new Set();
  const push = (t) => {
    const text = (t || '').trim();
    if (!text || text.length < 2 || text.length > 40) return;
    if (seen.has(text)) return;
    seen.add(text);
    out.push(text);
  };
  // 1) live autocomplete dropdown items
  document.querySelectorAll(
    '[class*="suggest" i] *, [class*="search-layer" i] *, [role="listbox"] *'
  ).forEach((n) => { if (!n.children.length) push(n.textContent); });
  // 2) "相关搜索" related-query chips on the results page
  document.querySelectorAll('.query-note-item, [class*="related" i] [class*="item" i]')
    .forEach((n) => push(n.textContent));
  return out;
}
"""


def _walk_strings(obj: Any) -> Iterator[str]:
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for value in obj.values():
            yield from _walk_strings(value)
    elif isinstance(obj, list):
        for value in obj:
            yield from _walk_strings(value)


def _extract_sug_texts(payload: Any) -> list[str]:
    """Prefer the well-known sug_items[].text shape; fall back to walking strings."""
    texts: list[str] = []
    if isinstance(payload, dict):
        data = payload.get("data")
        items = data.get("sug_items") if isinstance(data, dict) else None
        if isinstance(items, list):
            for item in items:
                if isinstance(item, dict):
                    text = item.get("text")
                    if isinstance(text, str) and text.strip():
                        texts.append(text.strip())
    return texts


class _SugCollector:
    def __init__(self):
        self.payloads: list[Any] = []
        self.response_count = 0
        self.error_count = 0

    async def on_response(self, response) -> None:
        url = (response.url or "").lower()
        if not any(marker in url for marker in SUG_URL_MARKERS):
            return
        self.response_count += 1
        try:
            self.payloads.append(await response.json())
        except Exception:
            self.error_count += 1


class XhsSearchSuggestProbe:
    def __init__(self, *, core_keyword: str, type_delay_ms: int = 140):
        self.core_keyword = (core_keyword or "").strip()
        self.type_delay_ms = type_delay_ms

    async def collect(self, page: Page) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        started = time.perf_counter()
        collector = _SugCollector()
        page.on("response", collector.on_response)
        typed_selector: str | None = None
        try:
            target = (
                f"{XHS_SEARCH_RESULT_URL}?keyword="
                + urllib.parse.quote(self.core_keyword)
            )
            await page.goto(target, wait_until="domcontentloaded", timeout=60000)
            # Wait for the auto-fired recommend response (best-effort).
            try:
                await page.wait_for_response(
                    lambda r: any(m in (r.url or "").lower() for m in SUG_URL_MARKERS),
                    timeout=8000,
                )
            except Exception:
                pass
            # Best-effort: focus the header input and retype to re-trigger recommend
            # in case the auto-fire was missed.
            if not collector.payloads:
                for selector in SEARCH_INPUT_SELECTORS:
                    try:
                        locator = page.locator(selector).first
                        if await locator.count() == 0:
                            continue
                        await locator.click(timeout=2000)
                        await locator.fill("")
                        await locator.type(self.core_keyword, delay=self.type_delay_ms)
                        typed_selector = selector
                        await page.wait_for_timeout(1800)
                        break
                    except Exception:
                        continue
            await page.wait_for_timeout(600)
            dropdown_texts: list[str] = []
            try:
                dropdown_texts = await page.evaluate(DROPDOWN_SCRIPT) or []
            except Exception:
                dropdown_texts = []
        finally:
            try:
                page.remove_listener("response", collector.on_response)
            except Exception:
                pass

        fetched_at = datetime.now(timezone.utc).isoformat()
        ordered = self._merge_candidates(dropdown_texts, collector.payloads)
        items: list[dict[str, Any]] = []
        for index, keyword in enumerate(ordered, start=1):
            items.append(
                {
                    "core_keyword": self.core_keyword,
                    "suggested_keyword": keyword,
                    "suggestion_rank": index,
                    "raw_payload": {"source": "search_recommend", "text": keyword},
                    "fetched_at": fetched_at,
                }
            )

        elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
        report = {
            "core_keyword": self.core_keyword,
            "suggestion_count": len(items),
            "intercepted_responses": collector.response_count,
            "intercept_parse_errors": collector.error_count,
            "dropdown_text_count": len(dropdown_texts),
            "typed_selector": typed_selector,
            "source_path": "search_result_recommend",
            "total_ms": elapsed_ms,
            "perf": {
                "total_ms": elapsed_ms,
                "items_per_second": round(len(items) / max(elapsed_ms / 1000, 0.001), 3),
            },
            "fragile_points": [
                "recommend endpoint path fragment may change",
                "sug_items json shape may change",
            ],
        }
        return items, report

    def _merge_candidates(self, dropdown_texts: list[str], payloads: list[Any]) -> list[str]:
        core = self.core_keyword
        core_lower = core.lower()
        ordered: list[str] = []
        seen: set[str] = set()

        def consider(raw: str) -> None:
            text = (raw or "").strip()
            if not text or len(text) > 40:
                return
            if text in seen or text == core:
                return
            if text.lower() in _NAV_BLOCKLIST:
                return
            # Real XHS long-tail suggestions extend the typed keyword.
            if core and core_lower not in text.lower():
                return
            seen.add(text)
            ordered.append(text)

        # 1) Authoritative: recommend endpoint sug_items, in server order.
        for payload in payloads:
            for text in _extract_sug_texts(payload):
                consider(text)
        # 2) Visible "相关搜索" chips / dropdown text.
        for text in dropdown_texts:
            consider(text)
        # 3) Last resort: walk any remaining strings from intercepted payloads.
        for payload in payloads:
            for text in _walk_strings(payload):
                consider(text)
        return ordered
