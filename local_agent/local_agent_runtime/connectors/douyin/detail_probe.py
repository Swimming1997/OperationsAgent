"""Douyin video detail collection via response interception.

We never sign Douyin APIs ourselves. We open the logged-in video page and
intercept the ``/aweme/v1/web/aweme/detail/`` XHR the page itself issues, then
normalize into the platform-agnostic ``DetailSnapshotInput``.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from playwright.async_api import Page

from local_agent_runtime.connectors.douyin import field as dy_field
from local_agent_runtime.connectors.douyin.normalizer import normalize_douyin_detail, unwrap_aweme_detail
from local_agent_runtime.contracts import DetailSnapshotInput
from local_agent_runtime.engine.pacing import PacingController


class DouyinDetailProbe:
    def __init__(self, *, pacing: PacingController | None = None):
        self.pacing = pacing or PacingController()

    async def fetch_detail(
        self,
        page: Page,
        *,
        platform_content_id: str,
        canonical_url: str | None = None,
        platform_context: dict[str, Any] | None = None,
    ) -> DetailSnapshotInput:
        aweme_id = str(platform_content_id)
        captured: list[str] = []

        async def cap(response):
            if dy_field.DETAIL_RESPONSE_PATH in response.url:
                try:
                    captured.append(await response.text())
                except Exception:
                    return

        def on_resp(response):
            asyncio.create_task(cap(response))

        page.on("response", on_resp)
        resolved_url = canonical_url or dy_field.build_video_url(aweme_id)
        await page.goto(resolved_url, wait_until="domcontentloaded", timeout=45000)
        await self.pacing.human_pause("page_load")
        # The detail XHR fires shortly after load; poll briefly for it.
        for _ in range(10):
            if captured:
                break
            await page.wait_for_timeout(600)
        await self.pacing.human_pause("settle")
        try:
            page.remove_listener("response", on_resp)
        except Exception:
            pass

        chosen: dict[str, Any] | None = None
        fallback: dict[str, Any] | None = None
        for body in captured:
            try:
                data = json.loads(body)
            except Exception:
                continue
            aweme = unwrap_aweme_detail(data)
            if not aweme:
                continue
            if str(aweme.get("aweme_id") or aweme.get("awemeId") or "") == aweme_id:
                chosen = aweme
                break
            fallback = fallback or aweme

        aweme = chosen or fallback
        diagnostics: dict[str, Any] = {
            "fetch_source": "xhr_intercept",
            "detail_xhr_count": len(captured),
            "matched_aweme": bool(chosen),
            "resolved_url": resolved_url,
            "platform_context": platform_context or {},
        }
        if not aweme:
            diagnostics["status"] = "detail_unavailable"
            return DetailSnapshotInput(platform_content_id=aweme_id, raw_payload={}, diagnostics=diagnostics)
        return normalize_douyin_detail(aweme, platform_content_id=aweme_id, diagnostics=diagnostics)
