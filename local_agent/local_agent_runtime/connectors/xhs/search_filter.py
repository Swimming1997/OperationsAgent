"""XHS native search-filter application.

Leverages the platform's own filter UI: clicks the sort / note-type /
publish-time controls and reads back the active state to confirm. This lives in
the connector layer so both the smoke runner and the live ``search_collect``
job can apply filters through the same code path.
"""

from __future__ import annotations

import time
from typing import Any

from playwright.async_api import Page

from local_agent_runtime.connectors.xhs.normalizer import build_search_filter_context

SORT_LABELS = {
    "comprehensive": "综合",
    "latest": "最新",
    "most_liked": "最多点赞",
    "most_commented": "最多评论",
    "most_collected": "最多收藏",
}

NOTE_TYPE_LABELS = {
    "all": "不限",
    "video": "视频",
    "image_text": "图文",
}

# Top-of-results channel tabs (persistent, click-to-apply) for note type.
NOTE_TYPE_CHANNELS = {
    "all": "全部",
    "video": "视频",
    "image_text": "图文",
}

PUBLISH_TIME_LABELS = {
    "all": "不限",
    "one_day": "一天内",
    "one_week": "一周内",
    "half_year": "半年内",
}


def default_filter_context() -> dict[str, str]:
    return build_search_filter_context()


def filters_are_default(requested: dict[str, Any]) -> bool:
    defaults = default_filter_context()
    for key in ("search_sort", "note_type", "publish_time"):
        if requested.get(key) not in {None, defaults.get(key)}:
            return False
    return True


async def _hover_open_panel(page: Page, diagnostics: dict[str, Any]) -> bool:
    """Open the XHS 筛选 panel by hovering its entry (it is hover-triggered).

    Clicking 筛选 toggles it shut, so we move the mouse over the entry and keep
    it there; the panel stays open while hovered, which is enough to then click
    an option inside it.
    """
    box = await page.evaluate(
        """
        () => {
          for (const el of document.querySelectorAll('span,div,button')) {
            const t = (el.childElementCount === 0 ? (el.textContent || '') : '').trim();
            if (t === '筛选') {
              const r = el.getBoundingClientRect();
              if (r.width > 0 && r.height > 0) return {x: r.x + r.width / 2, y: r.y + r.height / 2};
            }
          }
          return null;
        }
        """
    )
    if not box:
        diagnostics["steps"].append({"action": "panel_entry_not_found"})
        return False
    await page.mouse.move(box["x"], box["y"])
    await page.wait_for_timeout(900)
    diagnostics["steps"].append({"action": "panel_hover_open"})
    return True


async def _click_panel_option(page: Page, label: str, diagnostics: dict[str, Any]) -> bool:
    """Click an option inside the hover-open 筛选 panel.

    The panel is hover-anchored to 筛选, so the mouse (left there by
    ``_hover_open_panel``) must travel *into* the panel without leaving it or it
    collapses mid-click. We resolve the option's coordinates, move there in small
    steps (keeping hover), then issue a real (trusted) click so XHS's handler
    fires. Synthetic ``element.click()`` does not trigger the sort.
    """
    box = await page.evaluate(
        """
        (label) => {
          for (const el of document.querySelectorAll('span,div,li,button')) {
            if (el.childElementCount !== 0) continue;
            if ((el.textContent || '').trim() !== label) continue;
            const r = el.getBoundingClientRect();
            if (r.width <= 0 || r.height <= 0) continue;
            return {x: r.x + r.width / 2, y: r.y + r.height / 2};
          }
          return null;
        }
        """,
        label,
    )
    if not box:
        diagnostics["steps"].append({"action": "not_found", "label": label})
        return False
    try:
        await page.mouse.move(box["x"], box["y"], steps=8)
        await page.wait_for_timeout(250)
        await page.mouse.click(box["x"], box["y"])
        await page.wait_for_timeout(700)
        diagnostics["steps"].append({"action": "clicked", "label": label})
        return True
    except Exception as exc:
        diagnostics["steps"].append({"action": "click_failed", "label": label, "error": str(exc)})
        return False


async def _click_channel_tab(page: Page, label: str, diagnostics: dict[str, Any]) -> bool:
    """Click a note-type channel tab (全部/图文/视频) at the top of results.

    XHS renders a hidden duplicate of each channel that intercepts pointer
    events, so we resolve the *visible* one's coordinates and issue a real click.
    """
    box = await page.evaluate(
        """
        (label) => {
          const tabs = Array.from(document.querySelectorAll('.channel'));
          for (const el of tabs) {
            if (el.getAttribute('aria-hidden') === 'true') continue;
            if ((el.textContent || '').trim() !== label) continue;
            const r = el.getBoundingClientRect();
            if (r.width <= 0 || r.height <= 0) continue;
            return {x: r.x + r.width / 2, y: r.y + r.height / 2};
          }
          return null;
        }
        """,
        label,
    )
    if not box:
        diagnostics["steps"].append({"action": "channel_not_found", "label": label})
        return False
    try:
        await page.mouse.click(box["x"], box["y"])
        await page.wait_for_timeout(700)
        diagnostics["steps"].append({"action": "channel_clicked", "label": label})
        return True
    except Exception as exc:
        diagnostics["steps"].append({"action": "channel_click_failed", "label": label, "error": str(exc)})
        return False


async def _read_active_filters(page: Page) -> dict[str, Any]:
    """Re-open the panel and read which option is active in each section."""
    return await page.evaluate(
        """
        () => {
          const result = {active: []};
          const nodes = Array.from(document.querySelectorAll('[class*="active"], [class*="selected"], [aria-selected="true"]'));
          result.active = [...new Set(nodes.map(n => (n.textContent || '').trim()).filter(t => t && t.length <= 8))].slice(0, 40);
          return result;
        }
        """
    )


async def apply_search_filters(
    page: Page,
    *,
    search_sort: str,
    note_type: str,
    publish_time: str,
) -> tuple[dict[str, Any] | None, str, dict[str, Any], float]:
    """Attempt to click XHS search filter controls and read back UI state."""
    started = time.perf_counter()
    requested = build_search_filter_context(
        search_sort=search_sort,
        note_type=note_type,
        publish_time=publish_time,
    )
    diagnostics: dict[str, Any] = {"requested": requested, "steps": []}

    if filters_are_default(requested):
        elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
        return None, "not_applicable", {"reason": "default filters only"}, elapsed_ms

    defaults = default_filter_context()
    applied: dict[str, str | None] = {"search_sort": None, "note_type": None, "publish_time": None}

    # note_type: top channel tabs (persistent, reliable, no panel needed).
    if note_type != defaults["note_type"]:
        label = NOTE_TYPE_CHANNELS.get(note_type, note_type)
        if await _click_channel_tab(page, label, diagnostics):
            pass  # confirmed below by reading active state

    # search_sort / publish_time: live inside the hover-triggered 筛选 panel.
    # The panel closes after each selection, so re-open before each option.
    panel_targets = [
        ("search_sort", SORT_LABELS.get(search_sort, search_sort), search_sort, defaults["search_sort"]),
        ("publish_time", PUBLISH_TIME_LABELS.get(publish_time, publish_time), publish_time, defaults["publish_time"]),
    ]
    for _field, label, value, default_value in panel_targets:
        if value == default_value:
            continue
        if await _hover_open_panel(page, diagnostics):
            await _click_panel_option(page, label, diagnostics)

    # Verify by reading which options are now marked active/selected. The active
    # markers live inside the (hover-only) panel, so re-open it before reading,
    # then move the mouse away to let results settle.
    await _hover_open_panel(page, diagnostics)
    ui_after = await _read_active_filters(page)
    await page.mouse.move(200, 420)
    await page.wait_for_timeout(300)
    diagnostics["ui_after"] = ui_after
    active_items = ui_after.get("active") or []

    label_for = {
        "search_sort": SORT_LABELS.get(search_sort, search_sort),
        "note_type": NOTE_TYPE_CHANNELS.get(note_type, note_type),
        "publish_time": PUBLISH_TIME_LABELS.get(publish_time, publish_time),
    }
    for field, value in (("search_sort", search_sort), ("note_type", note_type), ("publish_time", publish_time)):
        if value == defaults[field]:
            continue
        label = label_for[field]
        if any(label == item or label in item for item in active_items):
            applied[field] = value

    confirmed = [field for field, value in applied.items() if value == requested.get(field)]
    requested_non_default = [field for field in ("search_sort", "note_type", "publish_time") if requested.get(field) != defaults.get(field)]
    elapsed_ms = round((time.perf_counter() - started) * 1000, 2)

    if not requested_non_default:
        return None, "not_applicable", diagnostics, elapsed_ms

    if not confirmed:
        if not any(step.get("action") == "clicked" for step in diagnostics["steps"]):
            return None, "not_implemented", diagnostics, elapsed_ms
        return None, "failed", diagnostics, elapsed_ms

    if len(confirmed) == len(requested_non_default):
        return build_search_filter_context(**{k: requested[k] for k in ("search_sort", "note_type", "publish_time")}), "applied", diagnostics, elapsed_ms

    partial_context = build_search_filter_context(
        search_sort=applied.get("search_sort") or default_filter_context()["search_sort"],
        note_type=applied.get("note_type") or default_filter_context()["note_type"],
        publish_time=applied.get("publish_time") or default_filter_context()["publish_time"],
    )
    return partial_context, "partial", diagnostics, elapsed_ms
