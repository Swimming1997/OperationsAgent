from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.parse import parse_qs, quote, urlencode, urlparse

import httpx
from playwright.async_api import Page

from local_agent_runtime.connectors.xhs.api_client import XhsApiClient, XhsApiError, XhsApiUnavailable, browser_context_cookie_header
from local_agent_runtime.connectors.xhs.context import XHS_BASE_URL, merge_xhs_context, normalize_xhs_url
from local_agent_runtime.enums import ContentType, FeedType, Platform, SourceSurface
from local_agent_runtime.contracts import FeedCandidateInput


@dataclass(frozen=True)
class XhsCreatorContext:
    creator_platform_id: str
    xsec_token: str = ""
    xsec_source: str = "pc_feed"
    public_identifier: str = ""
    resolve_source: str = "direct"

    @property
    def has_xsec_context(self) -> bool:
        return bool(self.xsec_token and self.xsec_source)

    def to_payload(self) -> dict[str, Any]:
        return {
            "creator_platform_id": self.creator_platform_id,
            "xsec_token": self.xsec_token,
            "xsec_source": self.xsec_source,
            "public_identifier": self.public_identifier,
            "resolve_source": self.resolve_source,
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
    def __init__(
        self,
        message: str,
        *,
        error_code: str = "internal_engine_error",
        retryable: bool = False,
        raw_context: dict[str, Any] | None = None,
    ):
        super().__init__(message)
        self.error_code = error_code
        self.retryable = retryable
        self.raw_context = raw_context or {}


def parse_xhs_creator_context(value: str, context: dict[str, Any] | None = None) -> XhsCreatorContext:
    context = context or {}
    value = (value or "").strip()
    if _looks_creator_id(value):
        return XhsCreatorContext(
            creator_platform_id=value,
            xsec_token=str(context.get("xsec_token") or ""),
            xsec_source=str(context.get("xsec_source") or "pc_feed"),
        )
    if value and "://" not in value and "/" not in value:
        return XhsCreatorContext(
            creator_platform_id=value,
            xsec_token=str(context.get("xsec_token") or ""),
            xsec_source=str(context.get("xsec_source") or "pc_feed"),
            public_identifier=value,
            resolve_source="xhs_public_identifier",
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
    return XhsCreatorContext(creator_platform_id=user_id, xsec_token=xsec_token, xsec_source=xsec_source, resolve_source="profile_url")


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
        "source_path": payload.get("source_path"),
        "url": payload.get("url"),
        "code": payload.get("code"),
        "success": payload.get("success"),
        "msg": payload.get("msg") or payload.get("message"),
        "parse_error": payload.get("parse_error"),
        "raw_text_prefix": str(payload.get("raw_text") or "")[:200] or None,
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
        primary_value = creator_profile_url or creator_platform_id or ""
        try:
            creator_context = parse_xhs_creator_context(primary_value, context=context)
        except ValueError:
            if creator_profile_url and creator_platform_id:
                # Some historical monitor records may store plain creator IDs in profile_url.
                creator_context = parse_xhs_creator_context(creator_platform_id, context=context)
            else:
                raise
        creator_context = await _resolve_creator_context(page, creator_context)
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
            dom_notes = await _extract_creator_notes_from_dom(page, fallback_xsec_source=creator_context.xsec_source, limit=limit)
            if dom_notes:
                raw_notes = dom_notes
                payload = {
                    "http_status": response_meta.get("http_status"),
                    "source_path": "creator_profile_dom_fallback",
                    "api_response_meta": response_meta,
                    "notes": dom_notes,
                }
                response_meta = {
                    **response_meta,
                    "has_notes": True,
                    "dom_fallback_used": True,
                    "dom_note_count": len(dom_notes),
                }
            else:
                raise _build_user_posted_fetch_error(payload, response_meta)
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


async def _resolve_creator_context(page: Page, context: XhsCreatorContext) -> XhsCreatorContext:
    if _looks_creator_id(context.creator_platform_id):
        return context
    public_identifier = context.public_identifier or context.creator_platform_id
    resolved = await _resolve_creator_by_public_identifier(page, public_identifier)
    if not resolved:
        raise XhsCreatorFetchError(
            f"未能通过小红书号找到对标账号主页：{public_identifier}",
            error_code="creator_not_found",
            retryable=False,
            raw_context={
                "source_path": "creator_public_identifier_resolution",
                "public_identifier": public_identifier,
            },
        )
    return XhsCreatorContext(
        creator_platform_id=resolved["creator_platform_id"],
        xsec_token=resolved.get("xsec_token") or context.xsec_token,
        xsec_source=resolved.get("xsec_source") or context.xsec_source or "pc_feed",
        public_identifier=public_identifier,
        resolve_source=resolved.get("resolve_source") or "xhs_search_user",
    )


async def _resolve_creator_by_public_identifier(page: Page, public_identifier: str) -> dict[str, str] | None:
    query = public_identifier.strip()
    if not query:
        return None
    await page.goto(f"{XHS_BASE_URL}/search_result?keyword={quote(query)}", wait_until="domcontentloaded", timeout=45000)
    await page.wait_for_timeout(1500)
    await _click_user_search_tab(page)
    await page.wait_for_timeout(1500)
    candidates = await _extract_profile_link_candidates(page)
    if not candidates:
        return None
    preferred = _choose_profile_candidate(candidates, query)
    if not preferred:
        return None
    return _candidate_to_creator_context(preferred)


async def _click_user_search_tab(page: Page) -> None:
    try:
        await page.evaluate(
            """
            () => {
              const nodes = Array.from(document.querySelectorAll('button, a, div, span'));
              const tab = nodes.find((node) => {
                const text = (node.innerText || node.textContent || '').trim();
                return text === '用户' || text === 'User';
              });
              if (tab && typeof tab.click === 'function') tab.click();
            }
            """
        )
    except Exception:
        return


async def _extract_profile_link_candidates(page: Page) -> list[dict[str, str]]:
    try:
        result = await page.evaluate(
            """
            () => Array.from(document.querySelectorAll('a[href*="/user/profile/"]'))
              .map((node) => {
                const card = node.closest('[class*="user"], [class*="card"], section, li, div') || node;
                return {
                  href: node.href || node.getAttribute('href') || '',
                  text: (card.innerText || card.textContent || node.innerText || '').trim().slice(0, 1000)
                };
              })
              .filter((item) => item.href)
            """
        )
        return result if isinstance(result, list) else []
    except Exception:
        return []


def _choose_profile_candidate(candidates: list[dict[str, str]], public_identifier: str) -> dict[str, str] | None:
    normalized_query = _normalize_public_identifier(public_identifier)
    parsed_candidates = [item for item in candidates if _candidate_to_creator_context(item)]
    if not parsed_candidates:
        return None
    for candidate in parsed_candidates:
        text = _normalize_public_identifier(candidate.get("text") or "")
        if normalized_query and normalized_query in text:
            return candidate
    return parsed_candidates[0]


def _candidate_to_creator_context(candidate: dict[str, str]) -> dict[str, str] | None:
    href = candidate.get("href") or ""
    try:
        parsed = urlparse(normalize_xhs_url(href) or href)
    except Exception:
        return None
    parts = [part for part in parsed.path.split("/") if part]
    user_id = ""
    for idx, part in enumerate(parts):
        if part == "profile" and idx > 0 and parts[idx - 1] == "user" and idx + 1 < len(parts):
            user_id = parts[idx + 1]
            break
    if not _looks_creator_id(user_id):
        return None
    params = parse_qs(parsed.query, keep_blank_values=True)
    return {
        "creator_platform_id": user_id,
        "xsec_token": (params.get("xsec_token") or [""])[0],
        "xsec_source": (params.get("xsec_source") or ["pc_search"])[0] or "pc_search",
        "resolve_source": "xhs_search_user",
    }


def _normalize_public_identifier(value: str) -> str:
    return "".join(ch.lower() for ch in str(value or "") if not ch.isspace())


async def _extract_creator_notes_from_dom(page: Page, *, fallback_xsec_source: str, limit: int) -> list[dict[str, Any]]:
    try:
        raw_cards = await page.evaluate(
            """
            () => {
              const anchors = Array.from(document.querySelectorAll('a[href*="/explore/"], a[href*="/discovery/item/"]'));
              const byNoteId = new Map();
              const noteIdOf = (href) => {
                const match = String(href || '').match(/\\/(explore|discovery\\/item)\\/([^?/#]+)/);
                return match ? match[2] : '';
              };
              const isVisible = (node) => !!(node.offsetWidth || node.offsetHeight || node.getClientRects().length);
              for (const anchor of anchors) {
                const href = anchor.getAttribute('href') || anchor.href || '';
                const noteId = noteIdOf(href);
                if (!href || !noteId) continue;
                const current = byNoteId.get(noteId);
                const score = (isVisible(anchor) ? 10 : 0) + (href.includes('xsec_token=') ? 5 : 0);
                if (!current || score > current.score) byNoteId.set(noteId, {anchor, score});
              }
              return Array.from(byNoteId.values()).map(({anchor}) => {
                const card = anchor.closest('section, div, article, li') || anchor;
                const img = card.querySelector('img');
                const titleEl = card.querySelector('.title, [class*="title"]');
                return {
                  href: anchor.getAttribute('href') || anchor.href || '',
                  card_text: (card.innerText || card.textContent || '').trim().slice(0, 1000),
                  title: titleEl ? (titleEl.innerText || titleEl.getAttribute('title') || '').trim() : '',
                  cover_url: img ? (img.currentSrc || img.src || img.getAttribute('src') || '') : ''
                };
              }).filter(Boolean);
            }
            """
        )
    except Exception:
        return []
    notes: list[dict[str, Any]] = []
    for raw in raw_cards or []:
        if not isinstance(raw, dict):
            continue
        note = _dom_card_to_creator_note(raw, fallback_xsec_source=fallback_xsec_source)
        if note:
            notes.append(note)
            if len(notes) >= limit:
                break
    return notes


def _dom_card_to_creator_note(raw: dict[str, Any], *, fallback_xsec_source: str) -> dict[str, Any] | None:
    href = str(raw.get("href") or "")
    try:
        parsed = urlparse(normalize_xhs_url(href) or href)
    except Exception:
        return None
    parts = [part for part in parsed.path.split("/") if part]
    note_id = ""
    for idx, part in enumerate(parts):
        if part in {"explore", "item"} and idx + 1 < len(parts):
            note_id = parts[idx + 1]
            break
        if part == "discovery" and idx + 2 < len(parts) and parts[idx + 1] == "item":
            note_id = parts[idx + 2]
            break
    if not note_id:
        return None
    params = parse_qs(parsed.query, keep_blank_values=True)
    xsec_token = (params.get("xsec_token") or [""])[0]
    xsec_source = (params.get("xsec_source") or [fallback_xsec_source or "pc_feed"])[0] or fallback_xsec_source or "pc_feed"
    title = str(raw.get("title") or "").strip() or _first_nonempty_line(str(raw.get("card_text") or ""))
    note = {
        "note_id": note_id,
        "display_title": title or None,
        "xsec_token": xsec_token,
        "xsec_source": xsec_source,
        "source_path": "creator_profile_dom_fallback",
    }
    cover_url = str(raw.get("cover_url") or "").strip()
    if cover_url:
        note["cover_url"] = cover_url
    return note


def _first_nonempty_line(value: str) -> str | None:
    for line in value.splitlines():
        text = line.strip()
        if text:
            return text[:200]
    return None


async def _fetch_creator_notes(page: Page, *, creator_context: XhsCreatorContext, limit: int) -> dict[str, Any]:
    signed_payload = await _fetch_creator_notes_signed(page, creator_context=creator_context, limit=limit)
    if signed_payload:
        return signed_payload
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


def _build_user_posted_fetch_error(payload: dict[str, Any], response_meta: dict[str, Any]) -> XhsCreatorFetchError:
    raw_text = str(payload.get("raw_text") or "")
    http_status = response_meta.get("http_status")
    raw_context = {
        "source_path": "creator_user_posted",
        "response_meta": response_meta,
        "payload_prefix": str(payload)[:1000],
    }
    if isinstance(http_status, int) and http_status >= 500:
        service_hint = _user_posted_service_hint(raw_text)
        message = f"小红书 user_posted 接口暂时不可用（HTTP {http_status}"
        if service_hint:
            message += f"，{service_hint}"
        message += "），请稍后重试；这不是对标账号没有笔记。"
        return XhsCreatorFetchError(
            message,
            error_code="retryable_network_error",
            retryable=True,
            raw_context=raw_context,
        )
    if payload.get("parse_error"):
        return XhsCreatorFetchError(
            f"user_posted returned non-JSON response: {response_meta}",
            error_code="structure_changed",
            retryable=True,
            raw_context=raw_context,
        )
    return XhsCreatorFetchError(
        f"user_posted returned no notes: {response_meta}; payload_prefix={str(payload)[:1000]}",
        error_code="non_retryable_platform_error",
        retryable=False,
        raw_context=raw_context,
    )


async def _fetch_creator_notes_signed(page: Page, *, creator_context: XhsCreatorContext, limit: int) -> dict[str, Any] | None:
    uri = "/api/sns/web/v1/user_posted"
    params = {
        "num": limit,
        "cursor": "",
        "user_id": creator_context.creator_platform_id,
        "image_formats": "jpg,webp,avif",
        "xsec_token": creator_context.xsec_token or "",
        "xsec_source": creator_context.xsec_source or "pc_feed",
    }
    try:
        cookie_str = await browser_context_cookie_header(page.context)
        data = await XhsApiClient(cookie_str=cookie_str)._request("GET", uri, params=params)
        return {"http_status": 200, "source_path": "signed_xhs_api_user_posted", **(data if isinstance(data, dict) else {})}
    except XhsApiUnavailable:
        return None
    except httpx.HTTPStatusError as exc:
        text = exc.response.text[:2000]
        try:
            payload = exc.response.json()
            if isinstance(payload, dict):
                return {
                    "http_status": exc.response.status_code,
                    "source_path": "signed_xhs_api_user_posted",
                    **payload,
                }
        except Exception:
            pass
        return {
            "http_status": exc.response.status_code,
            "source_path": "signed_xhs_api_user_posted",
            "parse_error": "HTTPStatusError non-JSON response",
            "raw_text": text,
        }
    except XhsApiError as exc:
        return {
            "http_status": None,
            "source_path": "signed_xhs_api_user_posted",
            "msg": str(exc)[:500],
        }
    except Exception as exc:
        return {
            "http_status": None,
            "source_path": "signed_xhs_api_user_posted",
            "parse_error": type(exc).__name__,
            "raw_text": str(exc)[:500],
        }


def _user_posted_service_hint(raw_text: str) -> str:
    text = raw_text.strip()
    if "create invoker failed" in text and "jarvis-gateway" in text:
        return "jarvis-gateway 创建调用器失败"
    return text[:120]


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
    normalized = (value or "").strip()
    return len(normalized) == 24 and all(ch in "0123456789abcdef" for ch in normalized.lower())


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
