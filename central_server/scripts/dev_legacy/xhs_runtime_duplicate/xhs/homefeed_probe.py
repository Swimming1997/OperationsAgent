from datetime import datetime, timezone
from typing import Any

from playwright.async_api import Page

from intelligence_engine.config import get_settings
from intelligence_engine.domain.schemas import FeedCandidateInput
from intelligence_engine.connectors.xhs.normalizer import candidate_field_report, normalize_xhs_card


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
        self.scroll_pause_ms = scroll_pause_ms or get_settings().xhs_probe_scroll_pause_ms

    async def collect(self, page: Page) -> tuple[list[FeedCandidateInput], dict[str, Any]]:
        candidates_by_id: dict[str, FeedCandidateInput] = {}
        extraction_paths = [
            'document.querySelectorAll(\'a[href*="/explore/"], a[href*="/discovery/item/"]\')',
            "anchor.closest('section, div, article, li')",
            "img.currentSrc/src for cover_url",
            "class contains title/author/like fallback selectors",
        ]
        for scroll_index in range(self.max_scrolls + 1):
            raw_cards = await page.evaluate(CARD_EXTRACTION_SCRIPT)
            discovered_at = datetime.now(timezone.utc)
            for raw in raw_cards:
                candidate = normalize_xhs_card(raw, feed_position=len(candidates_by_id) + 1, discovered_at=discovered_at)
                if candidate and candidate.platform_content_id not in candidates_by_id:
                    candidates_by_id[candidate.platform_content_id] = candidate
                    if len(candidates_by_id) >= self.target_count:
                        break
            if len(candidates_by_id) >= self.target_count:
                break
            await page.mouse.wheel(0, 1800)
            await page.wait_for_timeout(self.scroll_pause_ms)
        candidates = list(candidates_by_id.values())[: self.target_count]
        report = candidate_field_report(candidates, target_count=self.target_count)
        report.update(
            {
                "page_url": page.url,
                "scroll_attempts": min(self.max_scrolls, max(0, len(candidates))),
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
