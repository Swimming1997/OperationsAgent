"""Douyin homefeed / search probes via response interception.

Strategy (per agreed plan): drive a logged-in browser like a human using the
shared ``PacingController``, and capture the JSON the page fetches itself — the
page signs ``a_bogus`` for us, so we never sign requests. DOM is only a last
resort. Output is normalized to the unified content model.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

from playwright.async_api import Page

from local_agent_runtime.connectors.douyin import field as dy_field
from local_agent_runtime.connectors.douyin.normalizer import (
    extract_aweme_list,
    iter_stream_json,
    normalize_douyin_aweme,
)
from local_agent_runtime.contracts import FeedCandidateInput
from local_agent_runtime.engine.pacing import PacingController
from local_agent_runtime.enums import FeedType, SourceSurface


class _ResponseCollector:
    """Captures aweme objects from intercepted JSON responses."""

    def __init__(self, match_paths: tuple[str, ...]):
        self._match_paths = match_paths
        self.awemes: list[dict[str, Any]] = []
        self.response_count = 0
        self.error_count = 0

    async def on_response(self, response) -> None:
        url = response.url or ""
        if not any(path in url for path in self._match_paths):
            return
        self.response_count += 1
        try:
            text = await response.text()
        except Exception:
            self.error_count += 1
            return
        found = False
        # Douyin search/feed responses are an app-framed JSON stream, not a
        # single JSON document, so parse every embedded object.
        for obj in iter_stream_json(text):
            for aweme in extract_aweme_list(obj):
                self.awemes.append(aweme)
                found = True
        if not found:
            self.error_count += 1


class DouyinFeedProbe:
    """Collect Douyin recommend-feed or search awemes via interception."""

    def __init__(
        self,
        *,
        keyword: str | None = None,
        target_count: int = 30,
        max_scrolls: int = 15,
        sort: str = "comprehensive",
        publish_time: str = "all",
        duration: str = "all",
        start_rank: int = 0,
        pacing: PacingController | None = None,
    ):
        self.keyword = (keyword or "").strip()
        self.target_count = target_count
        self.max_scrolls = max_scrolls
        self.sort = sort
        self.publish_time = publish_time
        self.duration = duration
        self.start_rank = max(0, start_rank)
        self.pacing = pacing or PacingController()

    @property
    def _is_search(self) -> bool:
        return bool(self.keyword)

    def _match_paths(self) -> tuple[str, ...]:
        if self._is_search:
            return (dy_field.SEARCH_RESPONSE_PATH,)
        return tuple(dy_field.FEED_RESPONSE_PATHS)

    def _surface(self) -> tuple[SourceSurface, FeedType | None]:
        if self._is_search:
            return SourceSurface.SEARCH, None
        return SourceSurface.DOUYIN_VIDEO_HOME_FEED, FeedType.DOUYIN_VIDEO_HOME_FEED

    async def collect(self, page: Page) -> tuple[list[FeedCandidateInput], dict[str, Any]]:
        started = time.perf_counter()
        collector = _ResponseCollector(self._match_paths())
        page.on("response", collector.on_response)

        # Pull enough to honor start_rank (skip the first N already-seen items).
        needed = self.start_rank + self.target_count
        page_goto_ms = 0.0
        initial_wait_ms = 0.0
        scroll_ms = 0.0
        actual_scroll_count = 0
        try:
            if self._is_search:
                target_url = dy_field.build_search_url(
                    self.keyword,
                    sort=self.sort,
                    publish_time=self.publish_time,
                    duration=self.duration,
                )
            else:
                target_url = dy_field.RECOMMEND_URL
            if self._is_search or "douyin.com" not in (page.url or ""):
                goto_started = time.perf_counter()
                await page.goto(target_url, wait_until="domcontentloaded", timeout=60000)
                page_goto_ms = (time.perf_counter() - goto_started) * 1000
            wait_started = time.perf_counter()
            await self.pacing.initial_dwell(page)
            initial_wait_ms = (time.perf_counter() - wait_started) * 1000

            no_growth = 0
            for _ in range(self.max_scrolls):
                before = len(self._dedupe(collector.awemes))
                if before >= needed:
                    break
                scroll_started = time.perf_counter()
                await self.pacing.human_scroll(page)
                actual_scroll_count += 1
                scroll_ms += (time.perf_counter() - scroll_started) * 1000
                after = len(self._dedupe(collector.awemes))
                no_growth = no_growth + 1 if after == before else 0
                if no_growth >= 3:
                    break
        finally:
            page.remove_listener("response", collector.on_response)

        unique = self._dedupe(collector.awemes)
        window = unique[self.start_rank : self.start_rank + self.target_count]
        discovered_at = datetime.now(timezone.utc)
        source_surface, feed_type = self._surface()
        candidates: list[FeedCandidateInput] = []
        for offset, aweme in enumerate(window):
            candidate = normalize_douyin_aweme(
                aweme,
                feed_position=self.start_rank + offset + 1,
                discovered_at=discovered_at,
                source_surface=source_surface,
                feed_type=feed_type,
                search_keyword=self.keyword or None,
            )
            if candidate:
                candidates.append(candidate)

        elapsed = max(time.perf_counter() - started, 0.001)
        applied_via_url = self._is_search and (
            self.sort != "comprehensive" or self.publish_time != "all" or self.duration != "all"
        )
        report = {
            "source_path": "search_response_intercept" if self._is_search else "feed_response_intercept",
            "keyword": self.keyword or None,
            "intercepted_responses": collector.response_count,
            "intercept_parse_errors": collector.error_count,
            "raw_awemes_seen": len(collector.awemes),
            "unique_awemes": len(unique),
            "start_rank": self.start_rank,
            "normalized_items": len(candidates),
            "actual_scroll_count": actual_scroll_count,
            "requested_filter_context": {
                "sort": self.sort,
                "publish_time": self.publish_time,
                "duration": self.duration,
            },
            "filter_apply_status": "url_params" if applied_via_url else ("default" if self._is_search else "not_applicable"),
            "field_coverage": self._coverage(candidates),
            "perf": {
                "page_goto_ms": round(page_goto_ms, 2),
                "initial_wait_ms": round(initial_wait_ms, 2),
                "scroll_ms": round(scroll_ms, 2),
                "total_ms": round(elapsed * 1000, 2),
                "items_per_second": round(len(candidates) / elapsed, 3) if candidates else 0.0,
            },
            "fragile_points": [
                "Douyin feed/search XHR path fragments may change",
                "response JSON shape (aweme_info vs aweme_list) may change",
                "captcha/slider can interrupt the page mid-scroll",
            ],
        }
        return candidates, report

    @staticmethod
    def _dedupe(awemes: list[dict[str, Any]]) -> list[dict[str, Any]]:
        seen: set[str] = set()
        out: list[dict[str, Any]] = []
        for aweme in awemes:
            aweme_id = str(aweme.get("aweme_id") or "")
            if aweme_id and aweme_id not in seen:
                seen.add(aweme_id)
                out.append(aweme)
        return out

    @staticmethod
    def _coverage(candidates: list[FeedCandidateInput]) -> dict[str, float]:
        if not candidates:
            return {}
        total = len(candidates)
        keys = {
            "platform_content_id": lambda c: bool(c.platform_content_id),
            "canonical_url": lambda c: bool(c.canonical_url),
            "title_or_summary": lambda c: bool(c.title_or_summary),
            "cover_url": lambda c: bool(c.cover_url),
            "author_name": lambda c: bool(c.author_name),
        }
        return {name: round(sum(1 for c in candidates if fn(c)) / total, 3) for name, fn in keys.items()}
