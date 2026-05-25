"""XHS keyword search probe — browser discovery aligned with MediaCrawler search API fields.

MediaCrawler reference:
- POST /api/sns/web/v1/search/notes with keyword, page, page_size, search_id, sort, note_type
- Search results provide note id + xsec_token + xsec_source (typically pc_search)
- Detail/comment chains require preserving platform_context through ingestion
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote

from playwright.async_api import Page

from intelligence_engine.config import get_settings
from intelligence_engine.connectors.xhs.homefeed_probe import CARD_EXTRACTION_SCRIPT
from intelligence_engine.connectors.xhs.normalizer import candidate_field_report, normalize_xhs_search_card
from intelligence_engine.domain.schemas import FeedCandidateInput


class XhsSearchProbe:
    def __init__(
        self,
        *,
        keywords: list[str],
        max_items: int = 50,
        max_scrolls_per_keyword: int = 8,
        scroll_pause_ms: int | None = None,
    ):
        self.keywords = [item.strip() for item in keywords if item and item.strip()]
        self.max_items = max_items
        self.max_scrolls_per_keyword = max_scrolls_per_keyword
        self.scroll_pause_ms = scroll_pause_ms or get_settings().xhs_probe_scroll_pause_ms

    async def collect(self, page: Page) -> tuple[list[FeedCandidateInput], dict[str, Any]]:
        per_keyword_target = max(1, self.max_items // max(len(self.keywords), 1))
        candidates_by_id: dict[str, FeedCandidateInput] = {}
        per_keyword_summary: list[dict[str, Any]] = []
        failed_keywords: list[str] = []

        for keyword in self.keywords:
            keyword_seen = 0
            try:
                await page.goto(
                    f"https://www.xiaohongshu.com/search_result?keyword={quote(keyword)}",
                    wait_until="domcontentloaded",
                    timeout=60000,
                )
                await page.wait_for_timeout(1200)
                for _ in range(self.max_scrolls_per_keyword + 1):
                    raw_cards = await page.evaluate(CARD_EXTRACTION_SCRIPT)
                    discovered_at = datetime.now(timezone.utc)
                    for raw in raw_cards:
                        candidate = normalize_xhs_search_card(
                            raw,
                            search_keyword=keyword,
                            rank_position=keyword_seen + 1,
                            discovered_at=discovered_at,
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
                    await page.mouse.wheel(0, 1600)
                    await page.wait_for_timeout(self.scroll_pause_ms)
            except Exception as exc:
                failed_keywords.append(keyword)
                per_keyword_summary.append({"keyword": keyword, "items_seen": 0, "error": str(exc)})
                continue
            per_keyword_summary.append({"keyword": keyword, "items_seen": keyword_seen, "error": None})

        candidates = list(candidates_by_id.values())[: self.max_items]
        report = candidate_field_report(candidates, target_count=self.max_items)
        report.update(
            {
                "keywords": self.keywords,
                "searched_keyword_count": len(self.keywords),
                "failed_keyword_count": len(failed_keywords),
                "failed_keywords": failed_keywords,
                "per_keyword_summary": per_keyword_summary,
                "total_items_seen": sum(item.get("items_seen", 0) for item in per_keyword_summary),
                "normalized_items": len(candidates),
                "implementation_basis": "browser_search_result_page",
                "mediacrawler_api_reference": "/api/sns/web/v1/search/notes",
            }
        )
        return candidates, report
