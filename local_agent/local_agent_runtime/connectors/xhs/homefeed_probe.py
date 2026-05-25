import time
from datetime import datetime, timezone
from typing import Any

from playwright.async_api import Page


from local_agent_runtime.contracts import FeedCandidateInput
from local_agent_runtime.connectors.xhs.normalizer import candidate_field_report, coverage_from_field_report, normalize_xhs_card


CARD_EXTRACTION_SCRIPT = """
() => {
  const anchors = Array.from(document.querySelectorAll('a[href*="/explore/"], a[href*="/discovery/item/"]'));
  const byNoteId = new Map();
  const noteIdOf = (href) => {
    const match = String(href || '').match(/\\/(explore|discovery\\/item)\\/([^?]+)/);
    return match ? match[2] : '';
  };
  const isVisible = (node) => !!(node.offsetWidth || node.offsetHeight || node.getClientRects().length);
  for (const anchor of anchors) {
    const href = anchor.getAttribute('href') || anchor.href;
    const noteId = noteIdOf(href);
    if (!href || !noteId) continue;
    const current = byNoteId.get(noteId);
    const score = (isVisible(anchor) ? 10 : 0) + (href.includes('xsec_token=') ? 5 : 0);
    if (!current || score > current.score) byNoteId.set(noteId, {anchor, score});
  }
  return Array.from(byNoteId.values()).map(({anchor}) => {
    const card = anchor.closest('section, div, article, li') || anchor;
    const href = anchor.getAttribute('href') || anchor.href;
    const img = card.querySelector('img');
    const titleEl = card.querySelector('.title, [class*="title"]');
    const authorLink = card.querySelector('a[href*="/user/profile/"]');
    const authorEl = authorLink || card.querySelector('.author-wrapper .name, .author .name, [class*="author"] .name');
    const likeEl = card.querySelector('.like-wrapper, [class*="like"], .count, [class*="count"]');
    const authorHref = authorLink ? (authorLink.getAttribute('href') || authorLink.href || '') : '';
    const authorMatch = authorHref.match(/\\/user\\/profile\\/([^/?#]+)/);
    return {
      href,
      card_class: card.className || '',
      card_text: (card.innerText || '').slice(0, 1000),
      title: titleEl ? (titleEl.innerText || titleEl.getAttribute('title') || '').trim() : null,
      cover_url: img ? (img.currentSrc || img.src || img.getAttribute('src')) : null,
      author_name: authorEl ? (authorEl.innerText || '').trim() : null,
      author_platform_id: authorMatch ? authorMatch[1] : (authorEl ? (authorEl.getAttribute('data-user-id') || null) : null),
      visible_like_count: likeEl ? (likeEl.innerText || '').trim() : null
    };
  }).filter(Boolean);
}
"""


class XhsHomeFeedProbe:
    def __init__(self, *, target_count: int = 50, max_scrolls: int = 30, scroll_pause_ms: int | None = None):
        self.target_count = target_count
        self.max_scrolls = max_scrolls
        self.scroll_pause_ms = scroll_pause_ms or 1200

    async def collect(self, page: Page) -> tuple[list[FeedCandidateInput], dict[str, Any]]:
        started = time.perf_counter()
        page_goto_ms = 0.0
        initial_wait_ms = 0.0
        scroll_ms = 0.0
        dom_extract_ms = 0.0
        if "xiaohongshu.com/explore" not in (page.url or ""):
            goto_started = time.perf_counter()
            await page.goto("https://www.xiaohongshu.com/explore", wait_until="domcontentloaded", timeout=45000)
            page_goto_ms = (time.perf_counter() - goto_started) * 1000
            wait_started = time.perf_counter()
            await page.wait_for_timeout(1500)
            initial_wait_ms = (time.perf_counter() - wait_started) * 1000
        candidates_by_id: dict[str, FeedCandidateInput] = {}
        raw_cards_seen = 0
        actual_scroll_count = 0
        no_growth_stop_count = 0
        extraction_paths = [
            'document.querySelectorAll(\'a[href*="/explore/"], a[href*="/discovery/item/"]\')',
            "anchor.closest('section, div, article, li')",
            "img.currentSrc/src for cover_url",
            "class contains title/author/like fallback selectors",
        ]
        for scroll_index in range(self.max_scrolls + 1):
            extract_started = time.perf_counter()
            raw_cards = await page.evaluate(CARD_EXTRACTION_SCRIPT)
            dom_extract_ms += (time.perf_counter() - extract_started) * 1000
            raw_cards_seen += len(raw_cards or [])
            before_count = len(candidates_by_id)
            discovered_at = datetime.now(timezone.utc)
            for raw in raw_cards:
                candidate = normalize_xhs_card(raw, feed_position=len(candidates_by_id) + 1, discovered_at=discovered_at)
                if candidate and candidate.platform_content_id not in candidates_by_id:
                    candidates_by_id[candidate.platform_content_id] = candidate
                    if len(candidates_by_id) >= self.target_count:
                        break
            if len(candidates_by_id) >= self.target_count:
                break
            if len(candidates_by_id) == before_count:
                no_growth_stop_count += 1
            else:
                no_growth_stop_count = 0
            if no_growth_stop_count >= 3:
                break
            scroll_started = time.perf_counter()
            await page.mouse.wheel(0, 1800)
            actual_scroll_count += 1
            await page.wait_for_timeout(self.scroll_pause_ms)
            scroll_ms += (time.perf_counter() - scroll_started) * 1000
        candidates = list(candidates_by_id.values())[: self.target_count]
        report = candidate_field_report(candidates, target_count=self.target_count)
        field_coverage = coverage_from_field_report(
            report,
            ["platform_content_id", "canonical_url", "title_or_summary", "cover_url"],
        )
        elapsed = max(time.perf_counter() - started, 0.001)
        report.update(
            {
                "page_url": page.url,
                "scroll_attempts": actual_scroll_count,
                "actual_scroll_count": actual_scroll_count,
                "raw_cards_seen": raw_cards_seen,
                "normalized_items": len(candidates),
                "dedupe_count": max(0, raw_cards_seen - len(candidates_by_id)),
                "no_growth_stop_count": no_growth_stop_count,
                "source_path": "dom_card_extract",
                "field_coverage": field_coverage,
                "perf": {
                    "page_goto_ms": round(page_goto_ms, 2),
                    "initial_wait_ms": round(initial_wait_ms, 2),
                    "scroll_ms": round(scroll_ms, 2),
                    "dom_extract_ms": round(dom_extract_ms, 2),
                    "total_ms": round(elapsed * 1000, 2),
                    "items_per_second": round(len(candidates) / elapsed, 3) if candidates else 0.0,
                },
                "extraction_paths": extraction_paths,
                "recommend_detail_fetch_fields": [
                    "full body_text",
                    "precise author_platform_id when card lacks stable user id",
                    "publish_time",
                    "precise interaction counters",
                    "comment fetch params",
                ],
                "fragile_points": [
                    "XHS card class names are not a stable API",
                    "author and like selectors depend on current DOM text/class naming",
                    "virtualized feed may unload cards while scrolling",
                    "login/manual verification overlays can hide feed cards",
                ],
            }
        )
        return candidates, report
