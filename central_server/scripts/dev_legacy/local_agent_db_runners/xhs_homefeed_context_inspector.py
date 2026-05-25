# legacy DB-coupled smoke tool; not part of the formal Local Agent Runtime.
from __future__ import annotations

from typing import Any

from playwright.async_api import Page

from intelligence_engine.connectors.xhs.context import context_from_url_and_raw, parse_xhs_note_context
from intelligence_engine.connectors.xhs.normalizer import normalize_xhs_card
from intelligence_engine.domain.enums import SessionStatus
from intelligence_engine.sessions.xhs_browser_session import XhsBrowserSessionProvider


INSPECT_HOMEFEED_SCRIPT = """
(limit) => {
  const anchors = Array.from(document.querySelectorAll('a[href*="/explore/"], a[href*="/discovery/item/"]'));
  const seen = new Set();
  const out = [];
  for (const anchor of anchors) {
    const attrHref = anchor.getAttribute('href') || '';
    const fullHref = anchor.href || '';
    const key = fullHref || attrHref;
    if (!key || seen.has(key)) continue;
    seen.add(key);
    const index = out.length;
    anchor.setAttribute('data-amiracle-xhs-inspect-index', String(index));
    const card = anchor.closest('section, div, article, li') || anchor;
    const img = card.querySelector('img');
    const titleEl = card.querySelector('.title, [class*="title"], span, p');
    const authorEl = card.querySelector('.author, [class*="author"], .name, [class*="name"]');
    const likeEl = card.querySelector('.like-wrapper, [class*="like"], .count, [class*="count"]');
    const attrs = {};
    for (const attr of Array.from(card.attributes || [])) attrs[attr.name] = attr.value;
    const anchorAttrs = {};
    for (const attr of Array.from(anchor.attributes || [])) anchorAttrs[attr.name] = attr.value;
    const nearby = [];
    let node = card;
    for (let depth = 0; node && depth < 4; depth += 1) {
      const nodeAttrs = {};
      for (const attr of Array.from(node.attributes || [])) nodeAttrs[attr.name] = attr.value;
      nearby.push({
        tag: node.tagName,
        className: node.className || '',
        id: node.id || '',
        dataset: {...node.dataset},
        attributes: nodeAttrs,
        text: (node.innerText || node.textContent || '').trim().slice(0, 500)
      });
      node = node.parentElement;
    }
    const rawPayload = {
      href: attrHref || fullHref,
      anchor_href: fullHref,
      card_class: card.className || '',
      card_text: (card.innerText || '').slice(0, 1000),
      title: titleEl ? (titleEl.innerText || titleEl.getAttribute('title') || '').trim() : null,
      cover_url: img ? (img.currentSrc || img.src || img.getAttribute('src')) : null,
      author_name: authorEl ? (authorEl.innerText || '').trim() : null,
      author_platform_id: authorEl ? (authorEl.getAttribute('data-user-id') || authorEl.getAttribute('href') || null) : null,
      visible_like_count: likeEl ? (likeEl.innerText || '').trim() : null
    };
    out.push({
      inspect_index: index,
      anchor_get_attribute_href: attrHref,
      anchor_href: fullHref,
      outer_html_truncated: (card.outerHTML || anchor.outerHTML || '').slice(0, 3000),
      card_dataset: {...card.dataset},
      card_attributes: attrs,
      anchor_dataset: {...anchor.dataset},
      anchor_attributes: anchorAttrs,
      nearby_nodes: nearby,
      raw_payload: rawPayload
    });
    if (out.length >= limit) break;
  }
  return out;
}
"""


RUNTIME_CONTEXT_SCRIPT = """
() => {
  const textHits = [];
  for (const script of Array.from(document.querySelectorAll('script'))) {
    const text = script.textContent || '';
    if (text.includes('xsec_token') || text.includes('xsec_source')) {
      textHits.push(text.slice(0, 5000));
    }
  }
  const globalHits = [];
  for (const key of Object.keys(window)) {
    if (!(key.includes('INITIAL') || key.includes('STATE') || key.includes('REDUX'))) continue;
    try {
      const raw = JSON.stringify(window[key]);
      if (raw && (raw.includes('xsec_token') || raw.includes('xsec_source'))) {
        globalHits.push({key, value: raw.slice(0, 5000)});
      }
    } catch (e) {}
  }
  return {script_hit_count: textHits.length, script_hits: textHits.slice(0, 3), global_hit_count: globalHits.length, global_hits: globalHits.slice(0, 3)};
}
"""


def _context_payload(url: str | None, raw: dict[str, Any] | None = None) -> dict[str, Any]:
    context = context_from_url_and_raw(url, raw or {})
    return {
        "note_id": context.get("note_id") or "",
        "xsec_token_present": bool(context.get("xsec_token")),
        "xsec_source": context.get("xsec_source") or "",
        "has_xsec_context": bool(context.get("has_xsec_context")),
    }


class XhsHomeFeedContextInspector:
    def __init__(self, *, cdp_url: str = "http://127.0.0.1:9222"):
        self.cdp_url = cdp_url

    async def run(self, *, sample_count: int = 8, click_count: int = 5) -> dict[str, Any]:
        sample_count = max(1, min(sample_count, 10))
        click_count = max(0, min(click_count, sample_count))
        session = await XhsBrowserSessionProvider().acquire(session_meta={"cdp_url": self.cdp_url})
        if session.status != SessionStatus.READY:
            await session.close()
            return {
                "session_status": session.status.value,
                "session_message": session.message,
                "cards": [],
                "summary": {},
            }
        try:
            page = session.page
            assert page is not None
            cards = await self._inspect_cards(page, sample_count=sample_count)
            runtime_state = await page.evaluate(RUNTIME_CONTEXT_SCRIPT)
            click_diagnostics = []
            for index in range(min(click_count, len(cards))):
                click_diagnostics.append(await self._click_inspect_one(page, card=cards[index], sample_count=sample_count))
            click_by_index = {item["inspect_index"]: item for item in click_diagnostics}
            for card in cards:
                card["click_diagnostic"] = click_by_index.get(card["inspect_index"])
            summary = self._summarize(cards=cards, runtime_state=runtime_state)
            return {
                "session_status": session.status.value,
                "session_message": session.message,
                "page_url": page.url,
                "sample_count": len(cards),
                "click_attempt_count": len(click_diagnostics),
                "runtime_state": runtime_state,
                "summary": summary,
                "cards": cards,
            }
        finally:
            await session.close()

    async def _inspect_cards(self, page: Page, *, sample_count: int) -> list[dict[str, Any]]:
        raw_cards = await page.evaluate(INSPECT_HOMEFEED_SCRIPT, sample_count)
        cards: list[dict[str, Any]] = []
        for position, card in enumerate(raw_cards, start=1):
            raw_payload = card.get("raw_payload") or {}
            normalized = normalize_xhs_card(raw_payload, feed_position=position)
            attr_context = _context_payload(card.get("anchor_get_attribute_href"), raw_payload)
            href_context = _context_payload(card.get("anchor_href"), raw_payload)
            raw_context = _context_payload(raw_payload.get("href") or raw_payload.get("anchor_href"), raw_payload)
            card.update(
                {
                    "normalized_candidate": normalized.model_dump(mode="json") if normalized else None,
                    "context_from_anchor_get_attribute_href": attr_context,
                    "context_from_anchor_href": href_context,
                    "context_from_raw_payload": raw_context,
                    "has_xsec_token_or_source_text": self._has_xsec_text(card),
                }
            )
            cards.append(card)
        return cards

    async def _click_inspect_one(self, page: Page, *, card: dict[str, Any], sample_count: int) -> dict[str, Any]:
        index = int(card["inspect_index"])
        expected_href = card.get("anchor_get_attribute_href") or card.get("anchor_href")
        await page.evaluate(INSPECT_HOMEFEED_SCRIPT, sample_count)
        before_url = page.url
        selector = f'a[data-amiracle-xhs-inspect-index="{index}"]'
        try:
            href_before_click = await page.evaluate(
                """
                ({index, expectedHref}) => {
                  const noteMatch = String(expectedHref || '').match(/\\/(explore|discovery\\/item)\\/([^?]+)/);
                  const expectedNoteId = noteMatch ? noteMatch[2] : '';
                  const anchors = Array.from(document.querySelectorAll('a[href*="/explore/"], a[href*="/discovery/item/"]'));
                  const sameNoteAnchors = expectedNoteId
                    ? anchors.filter((node) => (node.getAttribute('href') || node.href || '').includes(expectedNoteId))
                    : [];
                  const isVisible = (node) => !!(node.offsetWidth || node.offsetHeight || node.getClientRects().length);
                  let anchor = sameNoteAnchors.find((node) => isVisible(node) && (node.getAttribute('href') || node.href || '').includes('xsec_token='));
                  if (!anchor) anchor = sameNoteAnchors.find((node) => isVisible(node));
                  if (!anchor) anchor = anchors.find((node) => (node.getAttribute('href') || node.href) === expectedHref || node.href === expectedHref);
                  if (!anchor && !expectedNoteId) anchor = document.querySelector(`a[data-amiracle-xhs-inspect-index="${index}"]`);
                  if (!anchor) return null;
                  anchor.setAttribute('data-amiracle-xhs-click-target', '1');
                  return anchor.getAttribute('href') || anchor.href;
                }
                """,
                {"index": index, "expectedHref": expected_href},
            )
            if not href_before_click:
                raise RuntimeError("click target anchor not found")
            locator = page.locator('a[data-amiracle-xhs-click-target="1"]').first
            try:
                await locator.click(timeout=5000)
            except Exception:
                await page.evaluate(
                    """
                    () => {
                      const anchor = document.querySelector('a[data-amiracle-xhs-click-target="1"]');
                      const target = anchor ? (anchor.closest('section, div, article, li') || anchor) : null;
                      if (target) target.click();
                    }
                    """
                )
            await page.wait_for_timeout(3000)
            after_url = page.url
            parsed = parse_xhs_note_context(after_url)
            return {
                "inspect_index": index,
                "click_ok": True,
                "expected_href": expected_href,
                "href_before_click": href_before_click,
                "before_url": before_url,
                "after_url": after_url,
                "after_url_context": parsed.to_payload() if parsed else None,
                "after_url_has_xsec_context": bool(parsed and parsed.has_xsec_context),
            }
        except Exception as exc:
            return {
                "inspect_index": index,
                "click_ok": False,
                "expected_href": expected_href,
                "before_url": before_url,
                "after_url": page.url,
                "error": str(exc),
                "after_url_has_xsec_context": False,
            }
        finally:
            if page.url != "https://www.xiaohongshu.com/explore":
                try:
                    await page.go_back(wait_until="domcontentloaded", timeout=15000)
                except Exception:
                    await page.goto("https://www.xiaohongshu.com/explore", wait_until="domcontentloaded", timeout=45000)
            await page.wait_for_timeout(1200)

    def _has_xsec_text(self, card: dict[str, Any]) -> bool:
        haystack = " ".join(
            str(value)
            for value in [
                card.get("anchor_get_attribute_href"),
                card.get("anchor_href"),
                card.get("outer_html_truncated"),
                card.get("card_dataset"),
                card.get("card_attributes"),
                card.get("anchor_dataset"),
                card.get("anchor_attributes"),
                card.get("raw_payload"),
            ]
        )
        return "xsec_token" in haystack or "xsec_source" in haystack

    def _summarize(self, *, cards: list[dict[str, Any]], runtime_state: dict[str, Any]) -> dict[str, Any]:
        attr_with_xsec = sum(1 for card in cards if card["context_from_anchor_get_attribute_href"]["has_xsec_context"])
        href_with_xsec = sum(1 for card in cards if card["context_from_anchor_href"]["has_xsec_context"])
        raw_with_xsec = sum(1 for card in cards if card["context_from_raw_payload"]["has_xsec_context"])
        attr_with_token = sum(1 for card in cards if card["context_from_anchor_get_attribute_href"]["xsec_token_present"])
        href_with_token = sum(1 for card in cards if card["context_from_anchor_href"]["xsec_token_present"])
        attr_with_source = sum(1 for card in cards if bool(card["context_from_anchor_get_attribute_href"]["xsec_source"]))
        href_with_source = sum(1 for card in cards if bool(card["context_from_anchor_href"]["xsec_source"]))
        click_attempts = [card.get("click_diagnostic") for card in cards if card.get("click_diagnostic")]
        click_with_xsec = sum(1 for item in click_attempts if item.get("after_url_has_xsec_context"))
        runtime_has_xsec = bool(runtime_state.get("script_hit_count") or runtime_state.get("global_hit_count"))
        return {
            "anchor_get_attribute_href_with_xsec_count": attr_with_xsec,
            "anchor_href_with_xsec_count": href_with_xsec,
            "raw_payload_with_xsec_count": raw_with_xsec,
            "anchor_get_attribute_href_with_xsec_token_count": attr_with_token,
            "anchor_href_with_xsec_token_count": href_with_token,
            "anchor_get_attribute_href_with_xsec_source_count": attr_with_source,
            "anchor_href_with_xsec_source_count": href_with_source,
            "runtime_state_has_xsec_text": runtime_has_xsec,
            "runtime_state_script_hit_count": runtime_state.get("script_hit_count", 0),
            "runtime_state_global_hit_count": runtime_state.get("global_hit_count", 0),
            "click_after_url_with_xsec_count": click_with_xsec,
            "click_attempt_count": len(click_attempts),
            "recommended_next_probe": self._recommend(
                attr_with_xsec=attr_with_xsec,
                href_with_xsec=href_with_xsec,
                runtime_has_xsec=runtime_has_xsec,
                click_with_xsec=click_with_xsec,
            ),
        }

    def _recommend(self, *, attr_with_xsec: int, href_with_xsec: int, runtime_has_xsec: bool, click_with_xsec: int) -> str:
        if attr_with_xsec or href_with_xsec:
            return "A_DOM_DIRECT_PARSE"
        if runtime_has_xsec:
            return "B_RUNTIME_STATE_PARSE"
        if click_with_xsec:
            return "C_LOW_FREQUENCY_CLICK_TO_RESOLVE_CONTEXT"
        return "D_OTHER_NEEDS_NETWORK_OR_API_TRACE"
