"""Douyin comment collection via response interception.

Opens the logged-in video page, opens the comment panel, and human-paces
scrolling to paginate the ``/aweme/v1/web/comment/list/`` XHR. Sub-comment
(``/reply/``) responses are ignored. Normalizes into ``CommentSnapshotInput``.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from typing import Any

from playwright.async_api import Page

from local_agent_runtime.connectors.douyin import field as dy_field
from local_agent_runtime.connectors.douyin.normalizer import normalize_douyin_comments
from local_agent_runtime.contracts import CommentSnapshotInput
from local_agent_runtime.engine.pacing import PacingController

COMMENT_ICON_SELECTORS = (
    "[data-e2e='comment-icon']",
    "[data-e2e='feed-comment-icon']",
    "span[data-e2e='comment-count']",
)


@dataclass
class DouyinCommentFetchResult:
    comments: list[CommentSnapshotInput] = field(default_factory=list)
    surface_status: str = "ok"
    error_code: str | None = None
    message: str | None = None
    diagnostics: dict[str, Any] = field(default_factory=dict)


class DouyinCommentProbe:
    def __init__(self, *, max_scrolls: int = 10, pacing: PacingController | None = None):
        self.max_scrolls = max_scrolls
        self.pacing = pacing or PacingController()

    async def fetch_comments_result(
        self,
        page: Page,
        *,
        platform_content_id: str,
        canonical_url: str | None = None,
        limit: int = 20,
    ) -> DouyinCommentFetchResult:
        aweme_id = str(platform_content_id)
        responses: list[dict[str, Any]] = []

        async def cap(response):
            url = response.url
            if dy_field.COMMENT_RESPONSE_PATH in url and dy_field.SUB_COMMENT_RESPONSE_PATH not in url:
                try:
                    responses.append(json.loads(await response.text()))
                except Exception:
                    return

        def on_resp(response):
            asyncio.create_task(cap(response))

        page.on("response", on_resp)
        resolved_url = canonical_url or dy_field.build_video_url(aweme_id)
        await page.goto(resolved_url, wait_until="domcontentloaded", timeout=45000)
        await self.pacing.human_pause("page_load")

        opened = await self._open_comment_panel(page)
        await self.pacing.human_pause("settle")

        # Park the cursor over the (right-hand) comment column and paginate.
        vp = await page.evaluate("() => ({w: window.innerWidth, h: window.innerHeight})")
        await page.mouse.move(vp["w"] * 0.78, vp["h"] * 0.5)
        last_count = 0
        no_growth = 0
        actual_scrolls = 0
        for _ in range(self.max_scrolls):
            await self.pacing.human_scroll(page, distance=1000)
            actual_scrolls += 1
            current = sum(len(r.get("comments") or []) for r in responses)
            if current == last_count:
                no_growth += 1
                if no_growth >= 3:
                    break
            else:
                no_growth = 0
                last_count = current
            if current >= limit:
                break
        await self.pacing.human_pause("settle")
        try:
            page.remove_listener("response", on_resp)
        except Exception:
            pass

        comments = normalize_douyin_comments(responses, limit=limit)
        diagnostics = {
            "fetch_source": "xhr_intercept",
            "comment_response_count": len(responses),
            "comment_panel_opened": opened,
            "actual_scroll_count": actual_scrolls,
            "resolved_url": resolved_url,
        }
        if not responses and not opened:
            return DouyinCommentFetchResult(
                comments=[],
                surface_status="comment_surface_unavailable",
                error_code="comment_panel_not_found",
                message="could not open Douyin comment panel and no comment XHR observed",
                diagnostics=diagnostics,
            )
        return DouyinCommentFetchResult(
            comments=comments,
            surface_status="ok" if comments else "true_empty_comments",
            diagnostics=diagnostics,
        )

    async def _open_comment_panel(self, page: Page) -> bool:
        for sel in COMMENT_ICON_SELECTORS:
            try:
                el = await page.query_selector(sel)
                if not el:
                    continue
                box = await el.bounding_box()
                if not box:
                    continue
                await page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
                return True
            except Exception:
                continue
        return False

    async def fetch_comments(
        self,
        page: Page,
        *,
        platform_content_id: str,
        canonical_url: str | None = None,
        limit: int = 20,
    ) -> list[CommentSnapshotInput]:
        result = await self.fetch_comments_result(
            page, platform_content_id=platform_content_id, canonical_url=canonical_url, limit=limit
        )
        return result.comments
