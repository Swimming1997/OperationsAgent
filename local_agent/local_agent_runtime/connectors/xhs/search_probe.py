"""XHS keyword search probe — browser discovery aligned with MediaCrawler search API fields.

MediaCrawler reference:
- POST /api/sns/web/v1/search/notes with keyword, page, page_size, search_id, sort, note_type
- Search results provide note id + xsec_token + xsec_source (typically pc_search)
- Detail/comment chains require preserving platform_context through ingestion
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote

from playwright.async_api import Page


from local_agent_runtime.connectors.xhs.homefeed_probe import CARD_EXTRACTION_SCRIPT
from local_agent_runtime.connectors.xhs.normalizer import (
    build_search_filter_context,
    candidate_field_report,
    coverage_from_field_report,
    normalize_xhs_search_card,
)
from local_agent_runtime.contracts import FeedCandidateInput


class XhsSearchProbe:
    def __init__(
        self,
        *,
        keywords: list[str],
        max_items: int = 50,
        max_scrolls_per_keyword: int = 8,
        scroll_pause_ms: int | None = None,
        search_sort: str = "comprehensive",
        note_type: str = "all",
        publish_time: str = "all",
        search_scope: str = "all",
        location_filter: str = "all",
        skip_initial_goto: bool = False,
    ):
        self.keywords = [item.strip() for item in keywords if item and item.strip()]
        self.max_items = max_items
        self.max_scrolls_per_keyword = max_scrolls_per_keyword
        self.scroll_pause_ms = scroll_pause_ms or 1200
        self.search_sort = search_sort
        self.note_type = note_type
        self.publish_time = publish_time
        self.search_scope = search_scope
        self.location_filter = location_filter
        self.skip_initial_goto = skip_initial_goto

    async def collect(self, page: Page) -> tuple[list[FeedCandidateInput], dict[str, Any]]:
        started = time.perf_counter()
        per_keyword_target = max(1, self.max_items // max(len(self.keywords), 1))
        candidates_by_id: dict[str, FeedCandidateInput] = {}
        per_keyword_summary: list[dict[str, Any]] = []
        failed_keywords: list[str] = []
        raw_cards_seen = 0
        actual_scroll_count = 0
        page_goto_ms = 0.0
        initial_wait_ms = 0.0
        scroll_ms = 0.0
        dom_extract_ms = 0.0

        for keyword in self.keywords:
            keyword_seen = 0
            try:
                if not self.skip_initial_goto or keyword != self.keywords[0]:
                    goto_started = time.perf_counter()
                    await page.goto(
                        f"https://www.xiaohongshu.com/search_result?keyword={quote(keyword)}",
                        wait_until="domcontentloaded",
                        timeout=60000,
                    )
                    page_goto_ms += (time.perf_counter() - goto_started) * 1000
                    wait_started = time.perf_counter()
                    await page.wait_for_timeout(1200)
                    initial_wait_ms += (time.perf_counter() - wait_started) * 1000
                no_growth_count = 0
                for _ in range(self.max_scrolls_per_keyword + 1):
                    extract_started = time.perf_counter()
                    raw_cards = await page.evaluate(CARD_EXTRACTION_SCRIPT)
                    dom_extract_ms += (time.perf_counter() - extract_started) * 1000
                    raw_cards_seen += len(raw_cards or [])
                    before_count = len(candidates_by_id)
                    discovered_at = datetime.now(timezone.utc)
                    for raw in raw_cards:
                        candidate = normalize_xhs_search_card(
                            raw,
                            search_keyword=keyword,
                            rank_position=keyword_seen + 1,
                            discovered_at=discovered_at,
                            search_sort=self.search_sort,
                            note_type=self.note_type,
                            publish_time=self.publish_time,
                            search_scope=self.search_scope,
                            location_filter=self.location_filter,
                        )
                        if not candidate:
                            continue
                        keyword_seen += 1
                        existing = candidates_by_id.get(candidate.platform_content_id)
                        if existing:
                            old_payload = dict(existing.raw_payload or {})
                            keywords = set(old_payload.get("search_keywords") or [])
                            keywords.add(keyword)
                            old_payload["search_keywords"] = sorted(keywords)
                            candidates_by_id[candidate.platform_content_id] = existing.model_copy(update={"raw_payload": old_payload})
                        else:
                            candidates_by_id[candidate.platform_content_id] = candidate
                        if keyword_seen >= per_keyword_target or len(candidates_by_id) >= self.max_items:
                            break
                    if keyword_seen >= per_keyword_target or len(candidates_by_id) >= self.max_items:
                        break
                    if len(candidates_by_id) == before_count:
                        no_growth_count += 1
                    else:
                        no_growth_count = 0
                    if no_growth_count >= 3:
                        break
                    scroll_started = time.perf_counter()
                    await page.mouse.wheel(0, 1600)
                    actual_scroll_count += 1
                    await page.wait_for_timeout(self.scroll_pause_ms)
                    scroll_ms += (time.perf_counter() - scroll_started) * 1000
            except Exception as exc:
                failed_keywords.append(keyword)
                per_keyword_summary.append({"keyword": keyword, "items_seen": 0, "error": str(exc)})
                continue
            per_keyword_summary.append({"keyword": keyword, "items_seen": keyword_seen, "error": None})

        candidates = list(candidates_by_id.values())[: self.max_items]
        report = candidate_field_report(candidates, target_count=self.max_items)
        field_coverage = coverage_from_field_report(
            report,
            ["platform_content_id", "canonical_url", "title_or_summary", "cover_url"],
        )
        elapsed = max(time.perf_counter() - started, 0.001)
        report.update(
            {
                "keywords": self.keywords,
                "search_sort": self.search_sort,
                "note_type": self.note_type,
                "publish_time": self.publish_time,
                "search_scope": self.search_scope,
                "location_filter": self.location_filter,
                "requested_filter_context": build_search_filter_context(
                    search_sort=self.search_sort,
                    note_type=self.note_type,
                    publish_time=self.publish_time,
                    search_scope=self.search_scope,
                    location_filter=self.location_filter,
                ),
                "applied_filter_context": None,
                "filter_apply_status": "not_implemented",
                "searched_keyword_count": len(self.keywords),
                "failed_keyword_count": len(failed_keywords),
                "failed_keywords": failed_keywords,
                "per_keyword_summary": per_keyword_summary,
                "total_items_seen": sum(item.get("items_seen", 0) for item in per_keyword_summary),
                "normalized_items": len(candidates),
                "raw_cards_seen": raw_cards_seen,
                "actual_scroll_count": actual_scroll_count,
                "page_goto_ms": round(page_goto_ms, 2),
                "source_path": "browser_search_result_page",
                "field_coverage": field_coverage,
                "perf": {
                    "page_goto_ms": round(page_goto_ms, 2),
                    "initial_wait_ms": round(initial_wait_ms, 2),
                    "scroll_ms": round(scroll_ms, 2),
                    "dom_extract_ms": round(dom_extract_ms, 2),
                    "total_ms": round(elapsed * 1000, 2),
                    "items_per_second": round(len(candidates) / elapsed, 3) if candidates else 0.0,
                },
                "implementation_basis": "browser_search_result_page",
                "mediacrawler_api_reference": "/api/sns/web/v1/search/notes",
            }
        )
        return candidates, report
