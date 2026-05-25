from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse

from playwright.async_api import Page

from intelligence_engine.connectors.xhs.context import XHS_BASE_URL, merge_xhs_context, normalize_xhs_url
from intelligence_engine.domain.enums import ContentType, FeedType, Platform, SourceSurface
from intelligence_engine.domain.schemas import FeedCandidateInput


@dataclass(frozen=True)
class XhsCreatorContext:
    creator_platform_id: str
    xsec_token: str = ""
    xsec_source: str = "pc_feed"

    @property
    def has_xsec_context(self) -> bool:
        return bool(self.xsec_token and self.xsec_source)

    def to_payload(self) -> dict[str, Any]:
        return {
            "creator_platform_id": self.creator_platform_id,
            "xsec_token": self.xsec_token,
            "xsec_source": self.xsec_source,
            "has_xsec_context": self.has_xsec_context,
        }


@dataclass(frozen=True)
class XhsCreatorItem:
    platform_content_id: str
    canonical_url: str
    title_or_summary: str | None
    cover_url: str | None
    publish_time: datetime | None
    xsec_token: str
    xsec_source: str
    raw_payload: dict[str, Any]

    @property
    def platform_context(self) -> dict[str, Any]:
        return merge_xhs_context(
            {
                "note_id": self.platform_content_id,
                "xsec_token": self.xsec_token,
                "xsec_source": self.xsec_source,
            }
        )

    def to_candidate(self, *, feed_position: int) -> FeedCandidateInput:
        return FeedCandidateInput(
            platform=Platform.XHS,
            platform_content_id=self.platform_content_id,
            canonical_url=self.canonical_url,
            content_type=ContentType.VIDEO if _looks_video(self.raw_payload) else ContentType.IMAGE_TEXT,
            title_or_summary=self.title_or_summary,
            cover_url=self.cover_url,
            source_surface=SourceSurface.CREATOR_MONITOR,
            feed_type=FeedType.XHS_HOME_FEED,
            feed_position=feed_position,
            discovered_at=datetime.now(timezone.utc),
            raw_payload=self.raw_payload,
            platform_context=self.platform_context,
        )


@dataclass(frozen=True)
class XhsCreatorFetchResult:
    creator_platform_id: str
    creator_display_name: str | None
    items: list[XhsCreatorItem]
    raw_payload: dict[str, Any]


class XhsCreatorFetchError(RuntimeError):
    pass


def parse_xhs_creator_context(value: str, context: dict[str, Any] | None = None) -> XhsCreatorContext:
    context = context or {}
    if _looks_creator_id(value):
        return XhsCreatorContext(
            creator_platform_id=value,
            xsec_token=str(context.get("xsec_token") or ""),
            xsec_source=str(context.get("xsec_source") or "pc_feed"),
        )
    normalized = normalize_xhs_url(value) or value
    parsed = urlparse(normalized)
    parts = [part for part in parsed.path.split("/") if part]
    user_id = ""
    for idx, part in enumerate(parts):
        if part == "profile" and idx > 0 and parts[idx - 1] == "user" and idx + 1 < len(parts):
            user_id = parts[idx + 1]
            break
    if not user_id:
        raise ValueError(f"unable to parse xhs creator URL: {value}")
    params = parse_qs(parsed.query, keep_blank_values=True)
    xsec_token = (params.get("xsec_token") or [context.get("xsec_token") or ""])[0]
    xsec_source = (params.get("xsec_source") or [context.get("xsec_source") or "pc_feed"])[0] or "pc_feed"
    return XhsCreatorContext(creator_platform_id=user_id, xsec_token=xsec_token, xsec_source=xsec_source)


def normalize_xhs_creator_item(raw: dict[str, Any], *, fallback_xsec_source: str = "pc_feed") -> XhsCreatorItem | None:
    note_id = str(raw.get("note_id") or raw.get("id") or raw.get("noteId") or "")
    if not note_id:
        return None
    xsec_token = str(raw.get("xsec_token") or raw.get("xsecToken") or "")
    xsec_source = str(raw.get("xsec_source") or raw.get("xsecSource") or fallback_xsec_source or "pc_feed")
    title = raw.get("display_title") or raw.get("title") or raw.get("desc")
    cover_url = _first_cover_url(raw)
    publish_time = _parse_publish_time(raw.get("time") or raw.get("last_update_time") or raw.get("publish_time"))
    query = {"xsec_source": xsec_source}
    if xsec_token:
        query["xsec_token"] = xsec_token
    canonical_url = f"{XHS_BASE_URL}/explore/{note_id}?{urlencode(query)}"
    return XhsCreatorItem(
        platform_content_id=note_id,
        canonical_url=canonical_url,
        title_or_summary=str(title) if title else None,
        cover_url=cover_url,
        publish_time=publish_time,
        xsec_token=xsec_token,
        xsec_source=xsec_source,
        raw_payload=raw,
    )


def parse_user_posted_response(payload: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    notes = data.get("notes") if isinstance(data, dict) else None
    meta = {
        "http_status": payload.get("http_status"),
        "code": payload.get("code"),
        "success": payload.get("success"),
        "msg": payload.get("msg") or payload.get("message"),
        "has_notes": isinstance(notes, list),
        "has_more": data.get("has_more") if isinstance(data, dict) else None,
        "cursor": data.get("cursor") if isinstance(data, dict) else None,
    }
    if not isinstance(notes, list):
        return [], meta
    return notes, meta


class XhsCreatorConnector:
    async def fetch_latest(
        self,
        page: Page,
        *,
        creator_profile_url: str | None = None,
        creator_platform_id: str | None = None,
        context: dict[str, Any] | None = None,
        limit: int = 20,
    ) -> XhsCreatorFetchResult:
        creator_context = parse_xhs_creator_context(creator_profile_url or creator_platform_id or "", context=context)
        profile_url = _build_creator_profile_url(creator_context)
        captured_payloads: list[dict[str, Any]] = []

        async def capture_user_posted(response):
            if "/api/sns/web/v1/user_posted" not in response.url:
                return
            try:
                payload = await response.json()
                if isinstance(payload, dict):
                    captured_payloads.append({"http_status": response.status, "url": response.url, **payload})
            except Exception:
                try:
                    captured_payloads.append({"http_status": response.status, "url": response.url, "raw_text": (await response.text())[:2000]})
                except Exception:
                    pass

        def on_response(response):
            import asyncio

            asyncio.create_task(capture_user_posted(response))

        page.on("response", on_response)
        await page.goto(profile_url, wait_until="domcontentloaded", timeout=45000)
        await page.wait_for_timeout(2500)
        for _ in range(3):
            await page.mouse.wheel(0, 1800)
            await page.wait_for_timeout(1500)
        try:
            page.remove_listener("response", on_response)
        except Exception:
            pass
        creator_display_name = await _extract_creator_display_name(page)
        payload = _first_payload_with_notes(captured_payloads)
        if payload is None:
            payload = await _fetch_creator_notes(page, creator_context=creator_context, limit=limit)
        raw_notes, response_meta = parse_user_posted_response(payload)
        if not raw_notes:
            raise XhsCreatorFetchError(f"user_posted returned no notes: {response_meta}; payload_prefix={str(payload)[:1000]}")
        items = [
            item
            for raw in raw_notes[:limit]
            if (item := normalize_xhs_creator_item(raw, fallback_xsec_source=creator_context.xsec_source))
        ]
        return XhsCreatorFetchResult(
            creator_platform_id=creator_context.creator_platform_id,
            creator_display_name=creator_display_name,
            items=items,
            raw_payload={
                "profile_url": profile_url,
                "notes_response": payload,
                "response_meta": response_meta,
                "captured_user_posted_count": len(captured_payloads),
                "creator_context": creator_context.to_payload(),
            },
        )


def _build_creator_profile_url(context: XhsCreatorContext) -> str:
    query: dict[str, str] = {}
    if context.xsec_token:
        query["xsec_token"] = context.xsec_token
    if context.xsec_source:
        query["xsec_source"] = context.xsec_source
    suffix = f"?{urlencode(query)}" if query else ""
    return f"{XHS_BASE_URL}/user/profile/{context.creator_platform_id}{suffix}"


async def _fetch_creator_notes(page: Page, *, creator_context: XhsCreatorContext, limit: int) -> dict[str, Any]:
    return await page.evaluate(
        """
        async ({userId, xsecToken, xsecSource, limit}) => {
          const params = new URLSearchParams({
            num: String(limit),
            cursor: "",
            user_id: userId,
            image_formats: "jpg,webp,avif",
            xsec_token: xsecToken || "",
            xsec_source: xsecSource || "pc_feed"
          });
          const response = await fetch(`/api/sns/web/v1/user_posted?${params.toString()}`, {
            method: "GET",
            credentials: "include",
            headers: {"accept": "application/json, text/plain, */*"}
          });
          const text = await response.text();
          try {
            const json = JSON.parse(text);
            return {http_status: response.status, ...json};
          } catch (e) {
            return {http_status: response.status, parse_error: String(e), raw_text: text.slice(0, 2000)};
          }
        }
        """,
        {
            "userId": creator_context.creator_platform_id,
            "xsecToken": creator_context.xsec_token,
            "xsecSource": creator_context.xsec_source,
            "limit": limit,
        },
    )


def _first_payload_with_notes(payloads: list[dict[str, Any]]) -> dict[str, Any] | None:
    for payload in payloads:
        notes, _meta = parse_user_posted_response(payload)
        if notes:
            return payload
    return None


async def _extract_creator_display_name(page: Page) -> str | None:
    try:
        return await page.evaluate(
            """
            () => {
              const selectors = ['.user-name', '.username', '[class*="user-name"]', '[class*="name"]'];
              for (const selector of selectors) {
                const node = document.querySelector(selector);
                const text = node ? (node.innerText || node.textContent || '').trim() : '';
                if (text) return text.slice(0, 100);
              }
              const title = document.title || '';
              return title ? title.replace('- 小红书', '').trim().slice(0, 100) : null;
            }
            """
        )
    except Exception:
        return None


def _looks_creator_id(value: str) -> bool:
    return len(value) == 24 and all(ch in "0123456789abcdef" for ch in value.lower())


def _looks_video(raw: dict[str, Any]) -> bool:
    return str(raw.get("type") or raw.get("note_type") or raw.get("media_type") or "").lower() in {"video", "2"}


def _first_cover_url(raw: dict[str, Any]) -> str | None:
    for key in ("cover", "cover_url", "image", "image_url"):
        value = raw.get(key)
        if isinstance(value, str) and value:
            return value
        if isinstance(value, dict):
            for nested_key in ("url", "url_default", "file_id"):
                nested = value.get(nested_key)
                if isinstance(nested, str) and nested.startswith("http"):
                    return nested
        if isinstance(value, list):
            for item in value:
                if isinstance(item, str) and item.startswith("http"):
                    return item
                if isinstance(item, dict):
                    nested = item.get("url") or item.get("url_default")
                    if isinstance(nested, str) and nested.startswith("http"):
                        return nested
    return None


def _parse_publish_time(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    try:
        timestamp = int(value)
        if timestamp > 10_000_000_000:
            timestamp = timestamp // 1000
        return datetime.fromtimestamp(timestamp, tz=timezone.utc)
    except Exception:
        return None
