"""Douyin long-tail keyword (search autocomplete) probe.

Types a seed keyword into the search box like a human and intercepts the
``/search/sug/`` response the page fetches, then normalizes it to the unified
suggestion item shape. This is the Douyin counterpart to the XHS search-suggest
probe so the central server / operator UI consume long-tail words uniformly.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

from playwright.async_api import Page

from local_agent_runtime.connectors.douyin import field as dy_field
from local_agent_runtime.connectors.douyin.normalizer import normalize_douyin_suggestions


class _SugCollector:
    def __init__(self):
        self.responses: list[dict[str, Any]] = []
        self.response_count = 0
        self.error_count = 0

    async def on_response(self, response) -> None:
        url = response.url or ""
        if dy_field.SUG_RESPONSE_PATH not in url:
            return
        self.response_count += 1
        try:
            data = await response.json()
        except Exception:
            self.error_count += 1
            return
        if isinstance(data, dict) and isinstance(data.get("sug_list"), list):
            self.responses.append(data)


class DouyinSearchSuggestProbe:
    def __init__(self, *, core_keyword: str, type_delay_ms: int = 160):
        self.core_keyword = (core_keyword or "").strip()
        self.type_delay_ms = type_delay_ms

    async def collect(self, page: Page) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        started = time.perf_counter()
        collector = _SugCollector()
        page.on("response", collector.on_response)
        typed_selector: str | None = None
        try:
            if "douyin.com" not in (page.url or ""):
                await page.goto(dy_field.HOME_URL, wait_until="domcontentloaded", timeout=60000)
                await page.wait_for_timeout(1500)
            for selector in dy_field.SEARCHBAR_INPUT_SELECTORS:
                try:
                    locator = page.locator(selector).first
                    if await locator.count() == 0:
                        continue
                    await locator.click(timeout=2500)
                    await locator.fill("")
                    await locator.type(self.core_keyword, delay=self.type_delay_ms)
                    typed_selector = selector
                    break
                except Exception:
                    continue
            # Let the autocomplete request fire and arrive.
            await page.wait_for_timeout(1800)
        finally:
            page.remove_listener("response", collector.on_response)

        fetched_at = datetime.now(timezone.utc).isoformat()
        items: list[dict[str, Any]] = []
        seen: set[str] = set()
        # Prefer the latest response (most complete as the user finished typing).
        for data in reversed(collector.responses):
            for item in normalize_douyin_suggestions(data, core_keyword=self.core_keyword, fetched_at_iso=fetched_at):
                if item["suggested_keyword"] in seen:
                    continue
                seen.add(item["suggested_keyword"])
                items.append(item)
            if items:
                break

        elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
        report = {
            "core_keyword": self.core_keyword,
            "suggestion_count": len(items),
            "intercepted_responses": collector.response_count,
            "intercept_parse_errors": collector.error_count,
            "typed_selector": typed_selector,
            "source_path": "search_sug_intercept",
            "total_ms": elapsed_ms,
            "perf": {"total_ms": elapsed_ms, "items_per_second": round(len(items) / max(elapsed_ms / 1000, 0.001), 3)},
            "fragile_points": [
                "search box input selector may change",
                "/search/sug/ path fragment may change",
            ],
        }
        return items, report
