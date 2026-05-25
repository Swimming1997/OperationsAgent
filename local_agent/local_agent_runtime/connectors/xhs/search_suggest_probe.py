from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote

from playwright.async_api import Page


class XhsSearchSuggestProbe:
    def __init__(self, *, core_keyword: str):
        self.core_keyword = core_keyword.strip()

    async def collect(self, page: Page) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        started = time.perf_counter()
        await page.goto(
            f"https://www.xiaohongshu.com/search_result?keyword={quote(self.core_keyword)}",
            wait_until="domcontentloaded",
            timeout=60000,
        )
        await page.wait_for_timeout(800)
        suggestions = await page.evaluate(
            """
            () => {
              const nodes = Array.from(document.querySelectorAll('[class*="suggest"], [class*="Suggest"], .search-suggest-item, li'));
              const texts = nodes.map((node) => (node.textContent || '').trim()).filter(Boolean);
              return [...new Set(texts)].slice(0, 20);
            }
            """
        )
        fetched_at = datetime.now(timezone.utc)
        items: list[dict[str, Any]] = []
        for index, keyword in enumerate(suggestions or [], start=1):
            if keyword == self.core_keyword:
                continue
            items.append(
                {
                    "core_keyword": self.core_keyword,
                    "suggested_keyword": keyword,
                    "suggestion_rank": index,
                    "raw_payload": {"source": "search_box_suggest", "text": keyword},
                    "fetched_at": fetched_at.isoformat(),
                }
            )
        elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
        report = {
            "core_keyword": self.core_keyword,
            "suggestion_count": len(items),
            "total_ms": elapsed_ms,
            "perf": {"total_ms": elapsed_ms, "items_per_second": round(len(items) / max(elapsed_ms / 1000, 0.001), 3)},
        }
        return items, report
