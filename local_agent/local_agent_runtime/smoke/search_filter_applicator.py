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

    applied: dict[str, str | None] = {
        "search_sort": None,
        "note_type": None,
        "publish_time": None,
    }
    targets = [
        ("search_sort", SORT_LABELS.get(search_sort, search_sort)),
        ("note_type", NOTE_TYPE_LABELS.get(note_type, note_type)),
        ("publish_time", PUBLISH_TIME_LABELS.get(publish_time, publish_time)),
    ]

    ui_state = await page.evaluate(
        """
        () => {
          const text = document.body ? document.body.innerText : '';
          const active = Array.from(document.querySelectorAll('[class*="active"], [aria-selected="true"], .selected'))
            .map((node) => (node.textContent || '').trim())
            .filter(Boolean);
          const filterButtons = Array.from(document.querySelectorAll('button, [role="button"], span, div'))
            .map((node) => (node.textContent || '').trim())
            .filter((value) => value && value.length <= 12);
          return { active, filterButtons: [...new Set(filterButtons)].slice(0, 80), bodySnippet: text.slice(0, 1200) };
        }
        """
    )
    diagnostics["ui_before"] = ui_state

    for field, label in targets:
        if requested.get(field) == default_filter_context().get(field):
            applied[field] = requested[field]
            diagnostics["steps"].append({"field": field, "action": "skipped_default"})
            continue
        clicked = False
        for selector in (
            f"text={label}",
            f"button:has-text('{label}')",
            f"[role='button']:has-text('{label}')",
        ):
            try:
                locator = page.locator(selector).first
                if await locator.count() == 0:
                    continue
                await locator.click(timeout=2500)
                clicked = True
                diagnostics["steps"].append({"field": field, "action": "clicked", "selector": selector, "label": label})
                await page.wait_for_timeout(400)
                break
            except Exception as exc:
                diagnostics["steps"].append({"field": field, "action": "click_failed", "selector": selector, "error": str(exc)})
        if not clicked:
            diagnostics["steps"].append({"field": field, "action": "not_found", "label": label})

    ui_after = await page.evaluate(
        """
        () => {
          const active = Array.from(document.querySelectorAll('[class*="active"], [aria-selected="true"], .selected'))
            .map((node) => (node.textContent || '').trim())
            .filter(Boolean);
          return { active: [...new Set(active)].slice(0, 30) };
        }
        """
    )
    diagnostics["ui_after"] = ui_after

    for field, label in targets:
        if requested.get(field) == default_filter_context().get(field):
            continue
        active_text = " ".join(ui_after.get("active") or [])
        if label in active_text:
            applied[field] = requested[field]
        elif any(label in item for item in ui_after.get("active") or []):
            applied[field] = requested[field]

    confirmed = [field for field, value in applied.items() if value == requested.get(field)]
    requested_non_default = [field for field in ("search_sort", "note_type", "publish_time") if requested.get(field) != default_filter_context().get(field)]
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
