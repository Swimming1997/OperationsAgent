from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

from playwright.async_api import Page

from local_agent_runtime.connectors.douyin import field as dy_field
from local_agent_runtime.connectors.douyin.normalizer import (
    extract_aweme_list,
    normalize_douyin_aweme,
    normalize_douyin_creator_profile,
)
from local_agent_runtime.contracts import FeedCandidateInput
from local_agent_runtime.engine.pacing import PacingController
from local_agent_runtime.enums import SourceSurface


@dataclass
class DouyinCreatorFetchResult:
    creator_platform_id: str
    creator_display_name: str | None
    items: list[FeedCandidateInput] = field(default_factory=list)
    profile: dict[str, Any] = field(default_factory=dict)
    raw_payload: dict[str, Any] = field(default_factory=dict)


def parse_douyin_creator_id(value: str | None) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError("douyin creator id or profile URL is required")
    if "://" not in text:
        return text
    parsed = urlparse(text)
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) >= 2 and parts[-2] == "user":
        return parts[-1]
    raise ValueError(f"unable to parse douyin creator URL: {text}")


class DouyinCreatorProbe:
    def __init__(self, *, pacing: PacingController | None = None, max_scrolls: int = 8):
        self.pacing = pacing or PacingController()
        self.max_scrolls = max_scrolls

    async def fetch_latest(
        self,
        page: Page,
        *,
        creator_profile_url: str | None = None,
        creator_platform_id: str | None = None,
        limit: int = 20,
    ) -> DouyinCreatorFetchResult:
        creator_id = parse_douyin_creator_id(creator_profile_url or creator_platform_id)
        responses: list[dict[str, Any]] = []
        pending: set[asyncio.Task[Any]] = set()

        async def capture(response: Any) -> None:
            if dy_field.USER_POSTS_RESPONSE_PATH not in str(response.url or ""):
                return
            try:
                responses.append(json.loads(await response.text()))
            except Exception:
                return

        def on_response(response: Any) -> None:
            task = asyncio.create_task(capture(response))
            pending.add(task)
            task.add_done_callback(pending.discard)

        page.on("response", on_response)
        resolved_url = creator_profile_url or dy_field.build_user_url(creator_id)
        await page.goto(resolved_url, wait_until="domcontentloaded", timeout=45000)
        await self.pacing.initial_dwell(page)
        for _ in range(self.max_scrolls):
            if sum(len(extract_aweme_list(item)) for item in responses) >= limit:
                break
            await self.pacing.human_scroll(page)
        if pending:
            await asyncio.gather(*tuple(pending), return_exceptions=True)
        try:
            page.remove_listener("response", on_response)
        except Exception:
            pass

        awemes: list[dict[str, Any]] = []
        seen: set[str] = set()
        for payload in responses:
            for aweme in extract_aweme_list(payload):
                aweme_id = str(aweme.get("aweme_id") or "")
                if aweme_id and aweme_id not in seen:
                    awemes.append(aweme)
                    seen.add(aweme_id)
                if len(awemes) >= limit:
                    break
        profile_source = next(
            (
                aweme.get("author")
                for aweme in awemes
                if isinstance(aweme.get("author"), dict)
            ),
            {},
        )
        profile = normalize_douyin_creator_profile(profile_source)
        effective_creator_id = str(profile.get("creator_platform_id") or creator_id)
        items = [
            candidate
            for index, aweme in enumerate(awemes, start=1)
            if (
                candidate := normalize_douyin_aweme(
                    aweme,
                    feed_position=index,
                    source_surface=SourceSurface.CREATOR_MONITOR,
                    feed_type=None,
                )
            )
        ]
        return DouyinCreatorFetchResult(
            creator_platform_id=effective_creator_id,
            creator_display_name=profile.get("creator_display_name"),
            items=items,
            profile=profile,
            raw_payload={
                "source_path": "user_posts_response_intercept",
                "resolved_url": resolved_url,
                "response_count": len(responses),
                "items_seen": len(items),
                "profile": profile,
            },
        )
